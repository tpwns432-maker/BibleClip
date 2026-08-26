"""BibleDB: one SQLite bible version + lazy whitespace/fuzzy search index."""
import math
import os
import sqlite3

from bibleclip import korean, morph
from bibleclip.data import synonyms
from bibleclip.constants import ENGLISH_VERSIONS
from bibleclip.text_utils import clean_text, despace, trigrams


class BibleDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.name = os.path.splitext(os.path.basename(db_path))[0]
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.is_english = self.name.upper() in ENGLISH_VERSIONS
        self._search_index = None   # built lazily on first search
        self._inverted_index = None  # {원형토큰: set((b,c,v))}, lazy (v1.0.5 스마트 검색)
        self._verse_tokens = None    # {(b,c,v): [원형토큰...]}, 스코어링용 (역색인과 함께 빌드)
        self._bm25_stats = None      # (절 수 N, 평균 절 길이 avgdl) — BM25 정규화용, lazy
        self._load_info()
        self._load_books()

    def _load_info(self):
        cur = self.conn.cursor()
        cur.execute("SELECT name, value FROM info")
        self.info = dict(cur.fetchall())
        self.description = self.info.get('description', self.name)
        self.language = self.info.get('language', 'ko')
        if self.language == 'en':
            self.is_english = True
        # MyBible/MySword bibles flag inline Strong's numbers ('<S>NNNN</S>') with
        # info.strong_numbers='true' (e.g. KJV+). Drives the 원전 분해 breakdown so
        # an English translation can be analyzed just like 개역한글S.
        self.has_strongs = str(self.info.get('strong_numbers', '')).strip().lower() == 'true'

    def _load_books(self):
        cur = self.conn.cursor()
        cur.execute("SELECT book_number, short_name, long_name FROM books ORDER BY book_number")
        self.books = {}
        self.book_list = []
        for bn, short, long_ in cur.fetchall():
            self.books[bn] = (short, long_)
            self.book_list.append((bn, short, long_))

    def get_chapters(self, book_number):
        cur = self.conn.cursor()
        cur.execute("SELECT DISTINCT chapter FROM verses WHERE book_number=? ORDER BY chapter",
                     (book_number,))
        return [r[0] for r in cur.fetchall()]

    def get_verses(self, book_number, chapter):
        cur = self.conn.cursor()
        cur.execute("SELECT verse, text FROM verses WHERE book_number=? AND chapter=? ORDER BY verse",
                     (book_number, chapter))
        return [(v, clean_text(t)) for v, t in cur.fetchall()]

    def get_chapter_raw(self, book_number, chapter):
        """Raw verse text (markup intact) for one chapter — used to parse inline
        Strong's numbers for the 원전 분해 card. Display paths use get_verses."""
        cur = self.conn.cursor()
        cur.execute("SELECT verse, text FROM verses WHERE book_number=? AND chapter=? ORDER BY verse",
                     (book_number, chapter))
        return cur.fetchall()

    def get_verse_text(self, book_number, chapter, verse):
        cur = self.conn.cursor()
        cur.execute("SELECT text FROM verses WHERE book_number=? AND chapter=? AND verse=?",
                     (book_number, chapter, verse))
        row = cur.fetchone()
        return clean_text(row[0]) if row else ''

    def _build_search_index(self):
        """Cache (book, chap, verse, cleaned, despaced, trigrams) once."""
        if self._search_index is not None:
            return
        cur = self.conn.cursor()
        cur.execute("SELECT book_number, chapter, verse, text FROM verses "
                    "ORDER BY book_number, chapter, verse")
        idx = []
        for b, c, v, t in cur.fetchall():
            ct = clean_text(t)
            dt = despace(ct)
            idx.append((b, c, v, ct, dt, trigrams(dt)))
        self._search_index = idx

    def _build_inverted_index(self):
        """원형토큰 → set((book,chapter,verse)) 역색인을 1회 빌드(lazy, 캐시).

        v1.0.5 스마트 검색(띄어쓰기 AND/OR + 스코어링)의 메모리 인프라. 본문을
        ``korean.tokenize`` 로 정규화(조사 제거)해 키로 삼는다. 순수 ``dict``/``set``
        이라 프로즌 환경에서도 네이티브 크래시가 없다. (Korean 본문 전용 — 영어
        역본에 빌드해도 무해하나 Phase 2 가 한국어 역본에만 사용한다.)
        """
        if self._inverted_index is not None:
            return
        idx = {}
        vtoks = {}
        cur = self.conn.cursor()
        cur.execute("SELECT book_number, chapter, verse, text FROM verses "
                    "ORDER BY book_number, chapter, verse")
        for b, c, v, t in cur.fetchall():
            addr = (b, c, v)
            toks = korean.tokenize(clean_text(t))
            vtoks[addr] = toks
            for tok in toks:
                idx.setdefault(tok, set()).add(addr)
        self._inverted_index = idx
        self._verse_tokens = vtoks

    def inverted_index(self):
        """The {원형토큰 -> set((b,c,v))} index, building it on first access."""
        self._build_inverted_index()
        return self._inverted_index

    def _score(self, addr, query_tokens):
        """절 관련도 점수 — 걸러진 결과셋에만 적용(전수조사 아님). 3대 가중치:

        [1] 매칭 단어 수(×10, 지배적 — OR 분별력): 더 많은 질의어를 품을수록 고득점.
        [2] 밀집도(proximity, 0~6): 매칭 어절들이 한 절 안에서 가까이 모일수록 보너스
            (사용자가 찾던 '그 구절'을 상단 고정).
        [3] 길이(0~3): 절이 짧고 명확할수록 소폭 보너스.
        가중치2+3 최대(9) < 매칭 1개 차이(10)이므로 **매칭 수가 항상 우선**한다.
        어간 부분일치(`qt in vt`)로 '창조'가 '창조하시니라'에도 매칭된다."""
        vtokens = self._verse_tokens.get(addr, ()) if self._verse_tokens else ()
        if not vtokens:
            return 0.0
        firsts = []                       # 매칭된 각 질의어의 첫 등장 위치
        for qt in query_tokens:
            for i, vt in enumerate(vtokens):
                if qt in vt:
                    firsts.append(i)
                    break
        score = len(firsts) * 10.0        # [1] 매칭 단어 수
        if len(firsts) >= 2:              # [2] 밀집도: 위치 스팬이 좁을수록 +
            score += max(0.0, 6.0 - (max(firsts) - min(firsts)))
        score += max(0.0, 3.0 - len(vtokens) * 0.05)  # [3] 짧은 절 보너스
        return score

    # ---- BM25 랭킹 + 유의어 확장 검색 (v1.1.11) ----------------------------
    #
    # 기존 `_score` 는 '매칭 단어 수 ×10 + 밀집도 + 짧은 절'이었다. 잘 동작했지만
    # **IDF 가 없다** — 성경 전체에 수천 번 나오는 '하나님'과 수십 번 나오는 '연단'을
    # 같은 가치로 취급한다. BM25 는 정보검색의 표준 랭킹 함수로 그 빈 자리를 정확히 채운다:
    #
    #   score(D,Q) = Σ_t  IDF(t) · tf(t,D)·(k1+1) / ( tf(t,D) + k1·(1-b + b·|D|/avgdl) )
    #   IDF(t)     = ln( 1 + (N - df(t) + 0.5) / (df(t) + 0.5) )
    #
    #   · IDF          : 희귀한 질의어에 큰 가중치 → 분별력 있는 단어가 순위를 지배한다.
    #   · tf 포화(k1)  : 같은 단어가 반복돼도 점수가 무한히 오르지 않는다.
    #   · 길이 정규화(b): 긴 절이 '단어를 많이 품는다'는 이유만으로 이기지 못한다.
    #
    # **SQLite FTS5 를 쓰지 않는 이유**: BM25 에 필요한 통계(df / tf / 절 길이 / N)가 이미
    # 메모리 역색인에 전부 있다(`_inverted_index` + `_verse_tokens`, 부팅 시 백그라운드
    # 워밍). FTS5 는 별도 캐시 DB 파일 + 최신성 관리 + 한국어 토크나이저 우회가 딸려오는데,
    # 31,103절 규모에서 얻는 것은 속도뿐이고 그건 이미 충분하다. 목표는 'FTS5' 라는 수단이
    # 아니라 IDF 랭킹이라는 결과였다. 순수 dict/set/float 연산이라 프로즌 크래시도 0.
    #
    # **유의어 확장**: 다역본 앱 고유의 실패 모드를 없앤다 — 새번역으로 읽다가 '이집트'를
    # 기억하고 개역한글에서 검색하면 본문이 '애굽'이라 **0건**이 나온다(같은 단어가 새번역
    # 에서는 690건). 질의 토큰마다 유의어를 '대체 후보 그룹'으로 묶어, AND 는 그룹 단위로
    # 만족시키고 점수는 그룹 내 최고점만 취한다(중복 가산 방지). 유의어 항은
    # 감점해 **원어 그대로 맞은 절이 항상 위에 오도록** 한다.
    #
    # 감점은 **고정값이 아니라 사전의 추출 신뢰도(Dice)에 비례**한다. 이게 중요하다 —
    # 확장어를 모두 같은 무게로 두면, 오탐이 정답보다 희귀한 탓에 IDF 가 더 높아 **오탐이
    # 위로 올라온다**('이집트' 검색에서 애굽 0.91 보다 인도하여 0.22 가 상단을 차지했다).
    # w = SYN_W_MIN + (SYN_W_MAX - SYN_W_MIN)·신뢰도 → 확실한 대응은 거의 원어급, 애매한
    # 것은 '있으면 보여주되 아래로' 가 된다(recall 은 지키고 정밀도는 순위로 방어).

    BM25_K1 = 1.5        # tf 포화 계수 (표준 권장 1.2~2.0)
    BM25_B = 0.75        # 길이 정규화 강도 (표준 권장 0.75)
    SYN_W_MIN = 0.15     # 신뢰도 0 인 유의어의 가중치 (거의 안 보이게)
    SYN_W_MAX = 0.75     # 신뢰도 1 인 유의어의 가중치 (원문 1.0 보다는 항상 낮게)
    PROX_WEIGHT = 1.2    # 밀집도 보너스 상한 (BM25 는 위치를 안 보므로 tiebreaker 로)

    def _ensure_bm25_stats(self):
        """(N, avgdl) — 역색인과 같은 lazy 타이밍에 1회 계산."""
        self._build_inverted_index()
        if self._bm25_stats is None:
            vt = self._verse_tokens or {}
            n = len(vt) or 1
            total = sum(len(t) for t in vt.values())
            self._bm25_stats = (n, (float(total) / n) or 1.0)
        return self._bm25_stats

    def _term_addrs(self, term):
        """부분일치로 term 에 대응하는 절 주소 집합.

        색인은 조사만 제거된 원형 토큰이므로 어미가 붙은 형태가 그대로 키다('창조하시니라').
        `term in key` 부분일치가 어간 질의를 회수한다('창조' → '창조하시니라'). smart_search
        와 동일한 조회 규칙 — 두 경로가 같은 것을 찾도록 대칭을 유지한다."""
        idx = self._inverted_index or {}
        addrs = set()
        for key, a in idx.items():
            if term in key:
                addrs |= a
        return addrs

    def bm25_search(self, keyword, mode='and', limit=300, expand=True):
        """BM25 랭킹 검색. 결과 형식은 `search` 와 동일: [(book, chapter, verse, text)].

        `expand=True` 면 유의어 사전으로 질의를 확장한다(사전이 없으면 조용히 무확장).
        매칭이 없으면 `[]` → 호출부가 기존 검색 계단으로 폴백한다."""
        n, avgdl = self._ensure_bm25_stats()
        tokens = korean.tokenize(keyword)
        if not tokens:
            return []

        syn = synonyms.shared() if expand else None
        # 그룹 = 한 질의 토큰의 [(term, weight, addrs, idf), ...] 대체 후보들
        groups = []
        for t in tokens:
            members = [(t, 1.0)]
            if syn is not None:
                span = self.SYN_W_MAX - self.SYN_W_MIN
                for alt, conf in syn.expand(t):
                    conf = 0.0 if conf < 0.0 else (1.0 if conf > 1.0 else conf)
                    members.append((alt, self.SYN_W_MIN + span * conf))
            info = []
            for term, w in members:
                addrs = self._term_addrs(term)
                if not addrs:
                    continue
                df = len(addrs)
                idf = math.log(1.0 + (n - df + 0.5) / (df + 0.5))
                info.append((term, w, addrs, idf))
            if info:
                groups.append(info)
        if not groups:
            return []

        gsets = [set().union(*[i[2] for i in g]) for g in groups]
        if mode == 'or':
            cands = set()
            for gs in gsets:
                cands |= gs
        else:
            cands = set(gsets[0])
            for gs in gsets[1:]:
                cands &= gs
        if not cands:
            return []

        k1, b = self.BM25_K1, self.BM25_B
        scored = []
        for addr in cands:
            toks = self._verse_tokens.get(addr) or ()
            dl = len(toks) or 1
            norm = k1 * (1.0 - b + b * dl / avgdl)
            total = 0.0
            firsts = []
            for g in groups:
                best, best_pos = 0.0, None
                for term, w, addrs, idf in g:
                    if addr not in addrs:
                        continue
                    tf, pos = 0, None
                    for i, tk in enumerate(toks):
                        if term in tk:
                            tf += 1
                            if pos is None:
                                pos = i
                    if not tf:
                        continue
                    sc = w * idf * tf * (k1 + 1.0) / (tf + norm)
                    if sc > best:
                        best, best_pos = sc, pos
                if best:
                    total += best
                    if best_pos is not None:
                        firsts.append(best_pos)
            if total <= 0.0:
                continue
            # 밀집도: 질의어들이 한 절 안에서 가까이 모이면 소폭 가산. BM25 는 위치를 보지
            # 않으므로, '사용자가 찾던 그 구절'을 상단에 붙이던 기존 감각(Phase 3)을 유지한다.
            if len(firsts) >= 2:
                span = max(firsts) - min(firsts)
                total += self.PROX_WEIGHT * max(0.0, 1.0 - float(span) / dl)
            scored.append((total, addr))

        scored.sort(key=lambda r: (-r[0], r[1]))
        return [(bk, ch, vs, self.get_verse_text(bk, ch, vs))
                for _, (bk, ch, vs) in scored[:limit]]

    def smart_search(self, keyword, mode='and', limit=300):
        """v1.0.5 띄어쓰기 다중 키워드 검색 — 메모리 역색인 집합 연산.

        검색어를 ``korean.tokenize`` 로 정규화(색인과 동일 규칙)하고, 각 토큰을
        **부분일치**로 조회(어간 회수: '창조'→'창조하시니라')해 주소 집합을 만든 뒤
        ``mode`` 에 따라 AND(교집합 ``&``)/OR(합집합 ``|``)으로 결합한다. 매칭 단어 수
        (Phase 3: +밀집도·길이) 기준 내림차순 정렬 후 상위 ``limit`` 반환. 매칭 없으면
        ``[]`` → 호출부가 기존 검색으로 폴백. 순수 ``dict``/``set`` (프로즌 크래시 0).
        반환 형식은 ``search`` 와 동일: ``[(book, chapter, verse, text), ...]``."""
        self._build_inverted_index()
        idx = self._inverted_index
        tokens = korean.tokenize(keyword)
        if not tokens:
            return []
        sets = []
        for tok in tokens:
            hits = set()
            for key, addrs in idx.items():   # 부분일치 스캔(정확 매칭 포함)
                if tok in key:
                    hits |= addrs
            sets.append(hits)
        if mode == 'or':
            addrs = set()
            for s in sets:
                addrs |= s
        else:  # 'and'
            addrs = set(sets[0])
            for s in sets[1:]:
                addrs &= s
        if not addrs:
            return []
        ranked = sorted(addrs, key=lambda a: (-self._score(a, tokens), a))
        return [(b, c, v, self.get_verse_text(b, c, v))
                for (b, c, v) in ranked[:limit]]

    def search(self, keyword, limit=300, fuzzy_threshold=0.7, mode='and',
               expand_synonyms=True):
        """Whitespace-insensitive verse search.

        0) v1.1.11: **BM25 랭킹 + 유의어 확장**(`bm25_search`). 공백 유무·한/영 무관하게
           1차 경로다 — 단일 토큰도 IDF 랭킹의 이득이 있고, 유의어 확장은 오히려 단일
           토큰에서 가장 크게 작동한다('이집트' 0건 → '애굽' 742건). 결과가 비거나 어떤
           예외가 나도 아래 기존 계단으로 **100% 폴백**한다(fail-soft).
        0-1) v1.0.5: 검색어에 **띄어쓰기**가 있고 한국어 역본이면 → 메모리 역색인
           스마트 검색(``smart_search``, AND/OR 집합연산+스코어). 결과가 있으면 반환.
        1) (공백 없음·영어 역본·스마트 무결과 시) Exact (spacing-ignored) substring.
        2) If none, Kiwi 형태소 다중 키워드(프로즌 비활성, 소스 폴백).
        3) If still none, trigram overlap fuzzy.
        Returns a list of (book_number, chapter, verse, text).
        """
        keyword = (keyword or '').strip()
        if not keyword:
            return []
        # v1.1.11 BM25 + 유의어 확장을 먼저 시도. 전체를 try 로 감싼다 — 사전 파일이
        # 없거나 색인 빌드가 어떤 이유로 실패해도 검색이 죽지 않고 기존 경로로 내려간다.
        try:
            bm = self.bm25_search(keyword, mode=mode, limit=limit,
                                  expand=expand_synonyms)
            if bm:
                return bm
        except Exception:
            pass
        # v1.0.5 스마트 검색: 띄어쓰기 다중 키워드 → 역색인 집합연산. 결과 있으면 반환,
        # 없거나 공백 없으면 아래 기존 v1.0.4 라인으로 100% 폴백(호환 유지).
        if (' ' in keyword) and not self.is_english:
            smart = self.smart_search(keyword, mode=mode, limit=limit)
            if smart:
                return smart
        self._build_search_index()
        qd = despace(keyword)
        if not qd:
            return []
        exact = [(b, c, v, ct) for (b, c, v, ct, dt, tri) in self._search_index
                 if qd in dt]
        if exact:
            return exact[:limit]
        # 형태소 다중 키워드 AND (Korean only — Kiwi is a 한국어 분석기). A query
        # like "하나님의 사랑" → ["하나님","사랑"] matches verses carrying both,
        # ignoring 조사. Skipped when the lone token equals the despaced query
        # (the exact pass already covered that) or Kiwi yields nothing.
        #
        # 전체를 try/except 로 감싼다: Kiwi 형태소 분석/스캔에서 어떤 예외가 나도
        # 검색이 죽지 않고 아래 trigram 폴백으로 부드럽게 내려가도록(fail-soft).
        # 다중 키워드("태초 말씀 하나님")가 exact 를 빗나가 Kiwi 경로를 처음 타며
        # 깨지는 회귀를 방어. (단, kiwipiepy C확장의 네이티브 abort 는 Python 으로
        # 못 잡으므로 그 경우는 morph 단에서 Kiwi 자체를 비활성화해야 함.)
        if not self.is_english:
            try:
                tokens = morph.tokenize_keywords(keyword)
                if tokens and not (len(tokens) == 1 and tokens[0] == qd):
                    morph_hits = [(b, c, v, ct)
                                  for (b, c, v, ct, dt, tri) in self._search_index
                                  if all(tok in dt for tok in tokens)]
                    if morph_hits:
                        return morph_hits[:limit]
            except Exception:
                pass  # 형태소 검색 실패 → 조용히 trigram 폴백으로
        qtri = trigrams(qd)
        if not qtri:
            return []
        scored = []
        for (b, c, v, ct, dt, tri) in self._search_index:
            if not tri:
                continue
            inter = len(qtri & tri)
            if not inter:
                continue
            score = inter / len(qtri)
            if score >= fuzzy_threshold:
                scored.append((score, b, c, v, ct))
        scored.sort(key=lambda r: (-r[0], r[1], r[2], r[3]))
        return [(b, c, v, ct) for _, b, c, v, ct in scored[:limit]]

    def close(self):
        self.conn.close()

    @property
    def display_name(self):
        return f"{self.description} [{self.name}]"
