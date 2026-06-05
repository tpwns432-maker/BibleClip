"""Bible content bridge routes: navigation data, keyword/reference/Strong's
search, and the lexicon (사전) surface.

Mixed into webui.api.Api. Uses ``self.lib`` and ``self._popup_factory``.
``copy_reference`` deliberately stays on the base Api (it touches the optional
``pyperclip`` backend, which tests monkeypatch on the api module).
"""
import re

from bibleclip.webui.dicthtml import _TAGS_RE, _dict_page_html, parse_entry


class BibleRoutes:
    # ---- Navigation data ----

    def get_books(self, version):
        return self.lib.books(version)

    def get_chapters(self, version, book):
        return self.lib.get_chapters(version, int(book))

    def get_chapter(self, version, book, chapter):
        book, chapter = int(book), int(chapter)
        db = self.lib.dbs.get(version)
        short = long_ = '?'
        if db and book in db.books:
            short, long_ = db.books[book]
        verses = [{'n': n, 'text': t}
                  for n, t in self.lib.get_chapter(version, book, chapter)]
        return {
            'ref': {'version': version, 'book': book,
                    'short': short, 'long': long_, 'chapter': chapter},
            'verses': verses,
        }

    def get_interlinear(self, book, chapter):
        """Strong's-tagged words per verse (KRV 개역한글S; version-independent)."""
        return [{'n': n, 'words': [{'w': w, 'code': c} for (w, c) in words]}
                for n, words in self.lib.interlinear(int(book), int(chapter))]

    # ---- Reference + Strong's search ----

    def resolve_reference(self, text):
        """Parse a free-text reference (창 1:1, 창세기 1장 1절, 요 1:1-2,4) into a
        navigable target, or None. {book_num, short, long, chapter, verses}.
        Powers the unified jump bar (통합 검색바, Phase 2)."""
        refs = self.lib.parse_reference(text or '')
        if not refs:
            return None
        book_num, short, long_, chapter, verses = refs[0]
        return {'book_num': book_num, 'short': short, 'long': long_,
                'chapter': chapter, 'verses': verses}

    def search_strong(self, code):
        """Reverse Strong's cross-query: KRV verses containing the original-
        language word with this code. {code, count, hits:[{book_num, ref,
        chapter, verse, text}]}. Powers the original-language search (the
        copyright-clean replacement for the removed lexicon-based lookup)."""
        code = (code or '').strip().upper()
        rows = self.lib.search_strong(code)
        primary = self.lib.primary_version()
        shortmap = ({b['num']: b['short'] for b in self.lib.books(primary)}
                    if primary else {})
        hits = [{'book_num': r['book_num'],
                 'ref': f"{shortmap.get(r['book_num'], r['book_num'])} "
                        f"{r['chapter']}:{r['verse']}",
                 'chapter': r['chapter'], 'verse': r['verse'], 'text': r['text']}
                for r in rows]
        return {'code': code, 'count': len(hits), 'hits': hits}

    # ---- Keyword search ----

    def _search_version(self):
        ver = self.lib.primary_version()
        if ver and ver in self.lib.dbs:
            return ver
        for v in ('KRV', 'NRKV', 'KNRSV'):
            if v in self.lib.dbs:
                return v
        return next(iter(self.lib.dbs), None)

    def search(self, keyword, version=None, limit=200):
        """Keyword search in one version (defaults to the primary/Korean one).

        Returns {keyword, version, display, hits:[{book,chapter,verse,short,text}]}."""
        keyword = (keyword or '').strip().lstrip('#').strip()
        if not keyword:
            return {'keyword': '', 'version': None, 'display': '', 'hits': []}
        ver = version if (version and version in self.lib.dbs) else self._search_version()
        db = self.lib.dbs.get(ver)
        if not db:
            return {'keyword': keyword, 'version': None, 'display': '', 'hits': []}
        rows = db.search(keyword, limit=limit)
        hits = [{'book': b, 'chapter': c, 'verse': v,
                 'short': db.books[b][0] if b in db.books else '?', 'text': t}
                for (b, c, v, t) in rows]
        return {'keyword': keyword, 'version': ver,
                'display': db.display_name, 'hits': hits}

    # ---- Lexicon ----

    def lookup_strong(self, code, lang='ko', book=None, chapter=None, verse=None):
        """Full lexicon entry for a Strong's code: {code, headword, reading,
        html, morph}. ``morph`` (형태소 분석) is filled when verse context is
        given. Returns None only when there's neither a dict entry nor morph."""
        markup = self.lib.lookup_strong(code, lang)
        morph = []
        if book and chapter and verse:
            morph = self.lib.morphology(code, int(book), int(chapter), int(verse))
        if not markup:
            if morph:
                return {'code': code, 'headword': '', 'reading': '',
                        'html': '', 'morph': morph}
            return None
        entry = parse_entry(markup)
        entry['code'] = code
        entry['morph'] = morph
        return entry

    def hover_summary(self, code, book=None, chapter=None, verse=None):
        """Short preview for a Strong's word (hover tooltip): the original-
        language headword (shown large by the UI) + reading + a short gloss
        line. Prefers verse morphology, falls back to the lexicon entry.
        {code, headword, reading, lines:[...]}."""
        headword = reading = ''
        lines = []
        if book and chapter and verse:
            morph = self.lib.morphology(code, int(book), int(chapter), int(verse))
            if morph:
                w = morph[0]
                headword = w['lemma']
                reading = w['translit']
                parts = []
                if w['pos']:
                    parts.append(w['pos'])
                if w['gloss'] and w['gloss'] != '_':
                    parts.append(w['gloss'])
                if parts:
                    lines.append(' · '.join(parts))
        if not headword and not lines:
            markup = self.lib.lookup_strong(code, 'ko') or self.lib.lookup_strong(code, 'en')
            if markup:
                e = parse_entry(markup)
                headword, reading = e['headword'], e['reading']
                txt = _TAGS_RE.sub('', e['html']).replace('^', ' ')
                txt = re.sub(r'\s+', ' ', txt).strip()
                if txt:
                    lines.append(txt[:80] + ('…' if len(txt) > 80 else ''))
        return {'code': code, 'headword': headword, 'reading': reading, 'lines': lines}

    def open_dict_window(self, code, lang='ko', book=None, chapter=None,
                         verse=None, theme='light'):
        """Open an independent native window with the full dict entry (the
        right-click behaviour from the desktop app). No-op without a factory."""
        if self._popup_factory is None:
            return {'ok': False}
        entry = self.lookup_strong(code, lang, book, chapter, verse)
        html = _dict_page_html(code, entry, theme)
        try:
            self._popup_factory(f"사전 · {code}", html)
        except Exception:
            return {'ok': False}
        return {'ok': True}
