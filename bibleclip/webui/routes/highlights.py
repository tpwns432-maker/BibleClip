"""절 내부 단어 하이라이트 (형광펜, v1.1.12) bridge routes.

Thin wrappers over Library.highlights (bibleclip.highlights.Highlights), the
same shape as NoteRoutes. Mixed into webui.api.Api; uses only ``self.lib``.

Highlights are per (book, chapter, verse, **version**) — see highlights.py for
why the version can't be shared.
"""


class HighlightRoutes:
    def get_chapter_highlights(self, book, chapter, versions):
        """{version -> {verse -> [ranges]}} for one chapter.

        Takes the whole displayed version list so painting a card costs one
        bridge round trip no matter the 보기 모드 (절별 대조 / 병렬 독서 both
        show several versions at once)."""
        book, chapter = int(book), int(chapter)
        if isinstance(versions, str):      # tolerate a bare version name
            versions = [versions]
        out = {}
        for v in (versions or []):
            v = str(v)
            out[v] = self.lib.highlights.for_chapter(book, chapter, v)
        return out

    def get_verse_highlights(self, book, chapter, verse, version):
        """The range list for one verse+version ([] if none)."""
        return self.lib.highlights.get(int(book), int(chapter), int(verse),
                                       str(version))

    def set_verse_highlights(self, book, chapter, verse, version, ranges):
        """Replace one verse+version's whole range list (empty list deletes).
        Returns {ok, ranges} with the sanitized stored list."""
        stored = self.lib.highlights.set_verse(
            int(book), int(chapter), int(verse), str(version), ranges)
        return {'ok': True, 'ranges': stored}

    def clear_verse_highlights(self, book, chapter, verse, version):
        self.lib.highlights.clear_verse(int(book), int(chapter), int(verse),
                                        str(version))
        return {'ok': True}

    def get_all_highlights(self):
        """Every highlight in bible order — the hook for a future 하이라이트
        모아보기 panel (parity with get_all_notes)."""
        return self.lib.highlights.all()
