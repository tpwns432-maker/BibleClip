"""BibleDB: one SQLite bible version + lazy whitespace/fuzzy search index."""
import os
import sqlite3

from bibleclip import morph
from bibleclip.constants import ENGLISH_VERSIONS
from bibleclip.text_utils import clean_text, despace, trigrams


class BibleDB:
    def __init__(self, db_path):
        self.db_path = db_path
        self.name = os.path.splitext(os.path.basename(db_path))[0]
        self.conn = sqlite3.connect(db_path, check_same_thread=False)
        self.is_english = self.name.upper() in ENGLISH_VERSIONS
        self._search_index = None   # built lazily on first search
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

    def search(self, keyword, limit=300, fuzzy_threshold=0.7):
        """Whitespace-insensitive verse search with morpheme + fuzzy fallbacks.

        1) Exact (spacing-ignored) substring matches, in canonical order.
        2) If none, Kiwi 형태소 다중 키워드: split the query into content
           morphemes (조사·어미 제거) and return verses containing ALL of them.
        3) If still none, rank verses by trigram overlap with the query
           (handles minor typos) and return those above a threshold.
        Steps 2–3 are skipped/fall through silently when their analyzer is
        unavailable. Returns a list of (book_number, chapter, verse, text).
        """
        keyword = (keyword or '').strip()
        if not keyword:
            return []
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
