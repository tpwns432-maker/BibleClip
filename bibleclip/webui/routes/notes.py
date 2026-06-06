"""묵상 노트 (verse-anchored notes, Phase 3) bridge routes.

Thin wrappers over Library.notes (bibleclip.notes.Notes). Mixed into
webui.api.Api; uses only ``self.lib``.
"""


class NoteRoutes:
    def get_chapter_notes(self, book, chapter):
        """{verse -> text} for one chapter — the UI renders a 📄 badge on each."""
        return self.lib.notes.for_chapter(int(book), int(chapter))

    def get_all_notes(self):
        """All meditation notes in bible order — drives the 노트 모아보기 card.
        [{book, chapter, verse, text, ts}, ...]; book names resolved on the UI
        side (bookShortFor) so they honor the displayed version."""
        return self.lib.notes.all()

    def get_note(self, book, chapter, verse):
        """The note for a verse ({text, ts}) or None."""
        return self.lib.notes.get(int(book), int(chapter), int(verse))

    def set_note(self, book, chapter, verse, text):
        """Create/update a verse note (empty text deletes). Returns {ok, note}."""
        note = self.lib.notes.set(int(book), int(chapter), int(verse), text)
        return {'ok': True, 'note': note}

    def delete_note(self, book, chapter, verse):
        self.lib.notes.delete(int(book), int(chapter), int(verse))
        return {'ok': True}
