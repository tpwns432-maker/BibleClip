"""묵상 노트 (verse-anchored notes, Phase 3) bridge routes.

Thin wrappers over Library.notes (bibleclip.notes.Notes). Also hosts the 설교
장바구니 persistence routes (Library.cart) since both are verse-anchored user
content. Mixed into webui.api.Api; uses only ``self.lib``.
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

    # ---- 설교 장바구니 영속성 (FEAT-08) ----

    def get_cart(self):
        """The persisted sermon cart as a list of items (also bundled into
        get_initial, but exposed for an explicit refresh). [{book_num, chapter,
        verses, short_name}, ...]."""
        return self.lib.cart.all()

    def set_cart(self, items):
        """Replace the whole cart with ``items`` and persist (write-through). The
        front-end owns ordering (drag-and-drop) and sends the full list on every
        change. Returns {ok, items} with the sanitized stored list."""
        return {'ok': True, 'items': self.lib.cart.replace(items)}
