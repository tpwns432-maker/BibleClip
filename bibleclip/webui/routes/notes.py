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
        change. Broadcasts the new cart to every window that shows it (main drawer
        + pop-out window) so they stay in sync live (FEAT-07). Returns {ok, items}
        with the sanitized stored list."""
        stored = self.lib.cart.replace(items)
        self._broadcast_cart(stored)
        return {'ok': True, 'items': stored}

    # ---- 설교 장바구니 팝아웃 창 (FEAT-07) ----

    def open_cart_window(self):
        """Open the independent pop-out sermon-cart window (or focus the existing
        one). F11 프리젠테이션 중 메인이 전체화면이라 레일 패널을 못 보던 문제를 위해
        장바구니를 별도 창으로 분리 — 듀얼 모니터에서 설교 제어. No-op (ok:False)
        without the factory (headless tests / no window). Returns {ok}."""
        if self._cart_window_factory is None:
            return {'ok': False, 'error': 'no factory'}
        try:
            self._cart_window_factory()
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True}

    def cart_goto(self, book, chapter, verses):
        """Pop-out cart → main viewer jump (FEAT-07 크로스 윈도우 인터랙션). Pushes
        the navigation to the MAIN window so its bible card focuses the verse —
        even while the main window is in F11 fullscreen — without stealing focus
        from the cart window. Returns {ok}."""
        try:
            b, c = int(book), int(chapter)
            vs = [int(v) for v in (verses or [])]
        except (TypeError, ValueError):
            return {'ok': False}
        self._push('cartGoto', b, c, vs)
        return {'ok': True}
