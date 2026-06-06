"""JS-facing bridge API for the pywebview front-end.

Each public method is callable from JavaScript as ``pywebview.api.<method>(...)``
and must return JSON-serializable values. This module deliberately does NOT
import `webview`, so it can be unit-tested headlessly against a plain Library.
Events that originate in Python (caught clipboard references) are pushed to the
front-end via the injected window's ``evaluate_js`` — still no `webview` import.

The bridge surface is large, so it's split into mixin classes under
``webui/routes/`` (pywebview's js_api must be a single object → composition via
multiple inheritance). This module keeps the shared plumbing (__init__, window/
popup injection, the JS push channel) plus the clipboard monitoring + copy path
— those touch the optional ``pyperclip`` backend, which the headless tests
monkeypatch on *this* module, so they must reference it here.
"""
import json

from bibleclip.webui.routes import BibleRoutes, NoteRoutes, SystemRoutes
# Lexicon-markup helpers live in their own module to avoid a circular import
# (the route mixins need them too). Re-exported here for backwards compatibility
# — `from bibleclip.webui.api import markup_to_html` still works.
from bibleclip.webui.dicthtml import (  # noqa: F401  (re-export)
    markup_to_html, parse_entry, _morph_html, _dict_page_html,
    _TAGS_RE, _NUM_RE, _FIRST_FONT_RE, _LEAD_BR_RE, _DICT_THEMES,
)

try:
    import pyperclip
except Exception:  # pragma: no cover - clipboard backend optional at import
    pyperclip = None


class Api(SystemRoutes, BibleRoutes, NoteRoutes):
    """Thin, JSON-friendly facade over Library for the web front-end.

    Composed from the route mixins (system/bible/notes); the methods below are
    the shared core every mixin relies on."""

    def __init__(self, library):
        self.lib = library
        self._window = None        # pywebview window, injected by webui.app.main()
        self._popup_factory = None  # callable(title, html) -> new native window
        self._update = None        # last fetch_latest_release info (for install)
        self.monitoring = False

    def set_window(self, window):
        """Receive the pywebview window so Python-side events can reach JS.

        Kept separate from __init__ so headless tests construct an Api with no
        window (pushes become no-ops)."""
        self._window = window

    def set_popup_factory(self, factory):
        """Receive a callable that opens a new native window from (title, html).
        Supplied by webui.app (which owns `webview`); None in headless tests."""
        self._popup_factory = factory

    def _push(self, fn, *args):
        """Invoke ``window.bibleclip.<fn>(...args)`` in the web view.

        Safe to call from the monitor worker thread (pywebview marshals
        evaluate_js to the UI thread) and a no-op when no window is attached."""
        if self._window is None:
            return
        payload = ", ".join(json.dumps(a, ensure_ascii=False) for a in args)
        js = f"window.bibleclip && window.bibleclip.{fn}({payload})"
        try:
            self._window.evaluate_js(js)
        except Exception:
            pass

    # ---- Clipboard monitoring ----

    def start_monitoring(self):
        """Begin watching the system clipboard. Caught references are converted
        in place (the formatted multi-version text replaces the clipboard) and
        pushed to JS via window.bibleclip.onReference; '#keyword' queries go to
        onKeyword."""
        if pyperclip is None:
            return {'ok': False, 'error': 'pyperclip unavailable'}
        self.lib.start_monitoring(
            self._clip_read, self._clip_write,
            self._on_reference, self._on_keyword)
        self.monitoring = True
        return {'ok': True}

    def stop_monitoring(self):
        self.lib.stop_monitoring()
        self.monitoring = False
        return {'ok': True}

    def _clip_read(self):
        try:
            return pyperclip.paste() or ''
        except Exception:
            return ''

    def _clip_write(self, text):
        try:
            pyperclip.copy(text)
        except Exception:
            pass

    def _on_reference(self, result):
        # result is already JSON-serializable (see Library.build_output).
        self._push('onReference', result)

    def _on_keyword(self, keyword):
        self._push('onKeyword', keyword)

    # ---- Clipboard copy (stays here: touches the monkeypatched pyperclip) ----

    def copy_reference(self, book, chapter, verses, versions=None):
        """Format book/chapter/verses via the output pipeline, place it on the
        clipboard, and tell the monitor (so it isn't re-detected). ``verses`` is
        a list (empty = whole chapter). ``versions`` overrides output_order
        (the viewer passes its displayed versions for manual copy). ``n_parts``
        (역본 수) is returned so the front-end can record this in-app copy in the
        activity log alongside monitor-caught references. ``short_name`` is the
        book label honoring the 정식/약칭 setting + the copied version's own book
        name (same source as the monitor toast, Library._display_book_name) so the
        front-end no longer hard-codes the abbreviation. Returns
        {ok, text, n_parts, short_name} or {ok:False}."""
        book, chapter = int(book), int(chapter)
        vs = [int(v) for v in (verses or [])]
        order = [v for v in versions if v in self.lib.dbs] if versions else None
        text, n_parts = self.lib.format_reference(book, chapter, vs, order)
        if not text:
            return {'ok': False}
        if pyperclip is not None:
            try:
                pyperclip.copy(text)
            except Exception:
                pass
        self.lib.notify_clipboard_written(text)
        return {'ok': True, 'text': text, 'n_parts': n_parts,
                'short_name': self.lib._display_book_name(book, order)}

    def copy_references(self, items, versions=None):
        """Format MANY references into one clipboard block — the sermon cart's
        일괄 추출(전체/선택). ``items`` is a list of {book|book_num, chapter, verses}
        dicts (the cart's stored shape); each is formatted via the output
        pipeline (current 포맷터 규격 — same as a single copy) and the blocks are
        joined with a blank line, preserving the given order. ``versions``
        overrides output_order. Returns {ok, text, n_items} or {ok:False}."""
        order = [v for v in versions if v in self.lib.dbs] if versions else None
        blocks = []
        for it in (items or []):
            if not isinstance(it, dict):
                continue
            raw_book = it.get('book', it.get('book_num'))
            try:
                book = int(raw_book)
                chapter = int(it.get('chapter'))
                verses = [int(v) for v in (it.get('verses') or [])]
            except (TypeError, ValueError):
                continue
            text, _ = self.lib.format_reference(book, chapter, verses, order)
            if text:
                blocks.append(text)
        if not blocks:
            return {'ok': False}
        out = '\n\n'.join(blocks)
        if pyperclip is not None:
            try:
                pyperclip.copy(out)
            except Exception:
                pass
        self.lib.notify_clipboard_written(out)
        return {'ok': True, 'text': out, 'n_items': len(blocks)}
