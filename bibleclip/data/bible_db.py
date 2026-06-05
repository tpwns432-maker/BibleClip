"""BibleDB: one SQLite bible version + lazy whitespace/fuzzy search index."""
import os
import sqlite3

from bibleclip import korean, morph
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

    def search(self, keyword, limit=300, fuzzy_threshold=0.7, mode='and'):
        """Whitespace-insensitive verse search.

        0) v1.0.5: 검색어에 **띄어쓰기**가 있고 한국어 역본이면 → 메모리 역색인
           스마트 검색(``smart_search``, AND/OR 집합연산+스코어). 결과가 있으면 반환.
        1) (공백 없음·영어 역본·스마트 무결과 시) Exact (spacing-ignored) substring.
        2) If none, Kiwi 형태소 다중 키워드(프로즌 비활성, 소스 폴백).
        3) If still none, trigram overlap fuzzy.
        Returns a list of (book_number, chapter, verse, text).
        """
        keyword = (keyword or '').strip()
        if not keyword:
            return []
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
