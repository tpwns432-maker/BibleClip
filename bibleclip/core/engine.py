"""Bible reference parser: Korean/English styles -> book/chapter/verses."""
import re

from bibleclip.constants import KOREAN_BOOK_MAP, ENGLISH_BOOK_MAP
from bibleclip.text_utils import convert_qwerty_to_hangul


class Engine:
    VERSE_PATTERN = re.compile(
        # Book name: letters, with a digit allowed only when followed by more
        # letters (e.g. 요2서). A trailing digit must NOT be eaten as part of
        # the name, or "요15:4" would parse as book "요1", chapter 5.
        r'([가-힣a-zA-Z]+(?:\d[가-힣a-zA-Z]+)*)'
        r'\s*'
        r'(\d+)'
        r'\s*(?:장\s*)?'
        r'(?:'
        r'[:：]\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)'
        r'|'
        r'(?:편\s*)?(\d+)\s*절'
        r')?'
        r'(?:\s*절)?'
    )

    KOREAN_STYLE_PATTERN = re.compile(
        r'([가-힣]+(?:\d[가-힣]+)*)'
        r'\s*(\d+)\s*장'
        r'(?:\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)\s*절?)?'
    )

    ENGLISH_PATTERN = re.compile(
        r'(\d?\s*[a-zA-Z]+)'
        r'\s+'
        r'(\d+)'
        r'(?:'
        r'[:]\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,]\s*\d+(?:\s*[-~]\s*\d+)?)*)'
        r')?'
    )

    # Leading-NUMBER book aliases (1요, 1Jn, 2벧 …). The standard Korean/VERSE
    # patterns can't start a book name with a digit, so "1요 5:4" there drops the
    # "1" and reads "요 5:4". This dedicated pattern captures an OPTIONAL leading
    # number glued (or spaced) to the book token; parse_reference resolves the
    # whole token via the alias/English map ONLY, so it can NEVER override a
    # built-in parse — an UNregistered "1요" simply doesn't resolve here and falls
    # through to the old behavior (no 앞숫자 회귀). Mirrors VERSE_PATTERN's tail.
    LEADING_ALIAS_PATTERN = re.compile(
        r'(\d{1,3}\s*[가-힣a-zA-Z]+)'
        r'\s*'
        r'(\d+)'
        r'\s*(?:장\s*)?'
        r'(?:'
        r'[:：]\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)'
        r'|'
        r'(?:편\s*)?(\d+)\s*절'
        r')?'
        r'(?:\s*절)?'
    )

    @staticmethod
    def parse_verses(verse_str):
        if not verse_str:
            return []
        verses = []
        verse_str = verse_str.replace(' ', '')
        parts = re.split(r'[,，]', verse_str)
        for part in parts:
            if '-' in part or '~' in part:
                bounds = re.split(r'[-~]', part)
                if len(bounds) == 2:
                    start, end = int(bounds[0]), int(bounds[1])
                    verses.extend(range(start, end + 1))
            else:
                verses.append(int(part))
        return sorted(set(verses))

    @staticmethod
    def resolve_ambiguous_book(book_str, has_verse_separator):
        if book_str == '요일': return KOREAN_BOOK_MAP['요일']
        if book_str == '요이': return KOREAN_BOOK_MAP['요이']
        if book_str == '요삼': return KOREAN_BOOK_MAP['요삼']
        if book_str == '요':  return KOREAN_BOOK_MAP['요']
        return None

    @classmethod
    def parse_reference(cls, text, extra_books=None):
        """Parse a reference. ``extra_books`` is an optional
        ``{normalized_name: book_num}`` map of per-version book names (built by
        Library from loaded versions) so a version's OWN abbreviations are
        recognized (e.g. ESV '1Ths'). It is consulted only on the English path —
        where the leading book number is captured as part of the name — to avoid
        the Korean/VERSE path stripping a leading digit ("1 John" → "John")."""
        text = text.strip()
        if not text:
            return []
        results = []

        # Leading-number aliases (1요, 1Jn …) run FIRST so a registered token wins
        # over the standard patterns that would drop its leading digit. Gated on
        # the alias/English map: an unregistered token resolves to None here and
        # falls through unchanged.
        m = cls.LEADING_ALIAS_PATTERN.search(text)
        if m:
            canon = cls._lookup_alias_token(m.group(1), extra_books)
            if canon:
                chapter = int(m.group(2))
                verse_str = m.group(3) or m.group(4)
                verses = cls.parse_verses(verse_str) if verse_str else []
                return [(*canon, chapter, verses)]

        m = cls.KOREAN_STYLE_PATTERN.search(text)
        if m:
            book_str, chapter = m.group(1), int(m.group(2))
            verse_str = m.group(3)
            verses = cls.parse_verses(verse_str) if verse_str else []
            book_info = cls._lookup_book(book_str, bool(verse_str), extra_books)
            if book_info:
                results.append((*book_info, chapter, verses))
                return results

        m = cls.VERSE_PATTERN.search(text)
        if m:
            book_str, chapter = m.group(1), int(m.group(2))
            verse_str = m.group(3) or m.group(4)
            has_sep = m.group(3) is not None
            verses = cls.parse_verses(verse_str) if verse_str else []
            book_info = cls._lookup_book(book_str, has_sep, extra_books)
            if book_info:
                results.append((*book_info, chapter, verses))
                return results

        m = cls.ENGLISH_PATTERN.search(text)
        if m:
            book_str, chapter = m.group(1).strip(), int(m.group(2))
            verse_str = m.group(3)
            verses = cls.parse_verses(verse_str) if verse_str else []
            book_info = cls._lookup_english_book(book_str, extra_books)
            if book_info:
                results.append((*book_info, chapter, verses))
                return results
        return results

    @staticmethod
    def _norm_book(s):
        """Normalize a book name/abbrev for alias matching: lowercase, no spaces
        or dots. ('1 Ths.' / '1Ths' / '1ths' all collapse to '1ths'.)"""
        return (s or '').strip().lower().replace(' ', '').replace('.', '')

    _CANON_CACHE = None

    @classmethod
    def _canon(cls, book_num):
        """Canonical (book_num, short, long) tuple for a book number, or None.

        Memoized: the first call builds a {book_num: tuple} index from
        KOREAN_BOOK_MAP (which has many aliases → one tuple per book), turning the
        old O(66) linear scan per lookup into an O(1) dict hit."""
        if cls._CANON_CACHE is None:
            cls._CANON_CACHE = {v[0]: v for v in KOREAN_BOOK_MAP.values()}
        return cls._CANON_CACHE.get(book_num)

    @classmethod
    def _lookup_book(cls, book_str, has_verse_separator=True, extra_books=None):
        if book_str in KOREAN_BOOK_MAP:
            resolved = cls.resolve_ambiguous_book(book_str, has_verse_separator)
            return resolved if resolved else KOREAN_BOOK_MAP[book_str]
        converted = convert_qwerty_to_hangul(book_str)
        if converted and converted in KOREAN_BOOK_MAP:
            resolved = cls.resolve_ambiguous_book(converted, has_verse_separator)
            return resolved if resolved else KOREAN_BOOK_MAP[converted]
        # Custom alias fallback (aliases_override.json + each version's own book
        # names, gathered by Library.book_aliases). Lets a user-defined Korean
        # abbreviation — or any loaded version's native book name — resolve on the
        # Korean/VERSE path too, not just the English path. Built-in books above
        # always win, so this never shadows a standard parse.
        if extra_books:
            bn = extra_books.get(cls._norm_book(book_str))
            if bn is None and converted:
                bn = extra_books.get(cls._norm_book(converted))
            if bn is not None:
                return cls._canon(bn)
        return None

    @classmethod
    def _lookup_alias_token(cls, token, extra_books=None):
        """Resolve a (possibly leading-numbered) book token — '1요', '1Jn' — via
        the alias map and the static English map ONLY. The bare Korean map is
        deliberately skipped (the normal path owns built-in Korean books), so an
        UNregistered leading-number token returns None and the caller falls back
        to the standard patterns. Returns a canonical tuple or None."""
        key = cls._norm_book(token)
        if not key:
            return None
        bn = extra_books.get(key) if extra_books else None
        if bn is None:
            bn = ENGLISH_BOOK_MAP.get(key)
        return cls._canon(bn) if bn is not None else None
