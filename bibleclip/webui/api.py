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
import threading

from bibleclip.webui.routes import (
    BibleRoutes, HighlightRoutes, NoteRoutes, SlideRoutes, SystemRoutes,
)
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


class Api(SystemRoutes, BibleRoutes, NoteRoutes, HighlightRoutes, SlideRoutes):
    """Thin, JSON-friendly facade over Library for the web front-end.

    Composed from the route mixins (system/bible/notes/highlights/slides); the methods below are
    the shared core every mixin relies on."""

    def __init__(self, library):
        self.lib = library
        self._window = None        # pywebview window, injected by webui.app.main()
        self._popup_factory = None  # callable(title, html) -> new native window
        # FEAT-07 설교 장바구니 팝아웃 창(독립 윈도우). 메인과 실시간 양방향 동기화 +
        # 창에서 성구 클릭 시 메인 뷰어 점프(cart_goto). 팩토리는 webui.app 가 주입한다.
        self._cart_window = None        # the pop-out cart window (for pushes), or None
        self._cart_window_factory = None  # callable() -> opens/returns the cart window
        # 자막(PPT) 창 — 장바구니 팝아웃과 같은 배관(v1.2.0).
        self._subtitle_window = None          # 자막 창(푸시 대상), 없으면 None
        self._subtitle_window_factory = None  # callable() -> 창을 열고 반환
        self._slide_index = 0                 # 준비된 순서(=장바구니) 안의 현재 번호
        # F9 즉석 슬라이드. 준비한 순서를 벗어나 한 구절을 바로 띄우는 경우가 실제로
        # 잦아서, 장바구니와 별개의 '임시 한 장'을 둔다(걸려 있으면 이쪽이 우선).
        self._slide_adhoc = None
        # 긴 본문은 한 슬라이드가 여러 '장'이 된다(시편 119편 = 8장). 몇 장인지는
        # 실제로 그려 보는 자막 창만 알 수 있어(글꼴·창 크기에 달림) 창이 보고한다.
        # ◀ ▶ 는 장 안에서 먼저 움직이고, 끝에 닿으면 다음 구절로 넘어간다.
        self._slide_page = 0
        self._slide_pages = 1
        # F11 발표용 네이티브 전체화면 상태(v1.2.0). pywebview 의 toggle_fullscreen 은
        # '토글'이라 지금 상태를 우리가 들고 있지 않으면 프론트와 어긋난다.
        self._fullscreen = False
        self._update = None        # last fetch_latest_release info (for install)
        self.monitoring = False
        # Set when the front-end first reaches the bridge (get_initial) — proof
        # the local HTTP page actually loaded. The startup connection watchdog in
        # webui.app waits on this; if it never fires, it shows the guide screen.
        self._booted = threading.Event()

    def set_window(self, window):
        """Receive the pywebview window so Python-side events can reach JS.

        Kept separate from __init__ so headless tests construct an Api with no
        window (pushes become no-ops)."""
        self._window = window

    def set_native_fullscreen(self, on):
        """창 자체를 전체화면으로 만든다(F11 발표).

        HTML 의 requestFullscreen 은 **웹뷰 안에서만** 전체화면이라 제목표시줄과
        작업표시줄이 그대로 남는다(브라우저에서는 브라우저가 제 창을 OS 전체화면으로
        바꿔주지만, 임베드된 WebView2 에는 그 주인이 없다). 그래서 네이티브 창도
        함께 전체화면으로 만들어야 크롬 F11 과 같은 그림이 된다.

        pywebview 의 toggle_fullscreen() 은 토글이므로 현재 상태를 여기서 들고
        있다가, 이미 원하는 상태면 아무것도 하지 않는다(중복 호출로 어긋나는 것 방지).
        창이 없으면(헤드리스 테스트) 조용히 no-op."""
        on = bool(on)
        if self._window is None:
            return {'ok': False, 'error': 'no window'}
        if on == self._fullscreen:
            return {'ok': True, 'fullscreen': self._fullscreen}
        try:
            self._window.toggle_fullscreen()
            self._fullscreen = on
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'fullscreen': self._fullscreen}

    def set_popup_factory(self, factory):
        """Receive a callable that opens a new native window from (title, html).
        Supplied by webui.app (which owns `webview`); None in headless tests."""
        self._popup_factory = factory

    def set_cart_window_factory(self, factory):
        """Receive a callable() that opens (or returns the already-open) pop-out
        sermon-cart window (FEAT-07). Supplied by webui.app; None in headless
        tests, so open_cart_window degrades to a no-op there."""
        self._cart_window_factory = factory

    def set_subtitle_window_factory(self, factory):
        """webui.app 이 자막 창 생성자를 주입한다(장바구니 창과 같은 방식).
        헤드리스 테스트에는 주입되지 않으므로 open_subtitle_window 가 no-op 이 된다."""
        self._subtitle_window_factory = factory

    def _subtitle_version(self):
        """자막에 쓸 역본 — 화면 첫 번째 역본. 자막은 한 역본만 띄우는 것이 맞다
        (투사 화면에 두 역본을 겹치면 글자가 작아져 뒤에서 안 보인다)."""
        viewer = [v for v in (self.lib.settings.get('viewer_versions') or [])
                  if v in self.lib.dbs]
        return viewer[0] if viewer else self.lib.primary_version()

    def _resolve_slide(self, item):
        """장바구니 항목 하나 → 띄울 글자. {ref, verses:[{n,text}], version} 또는 None.

        줄바꿈은 하지 않는다 — 어디서 줄을 나눌지는 그리는 쪽이 제 글꼴로 폭을 재서
        정한다(web/js/versebreak.js). 여기서는 '무슨 글자'까지만 정한다."""
        try:
            book = int(item.get('book_num'))
            chapter = int(item.get('chapter'))
        except (TypeError, ValueError, AttributeError):
            return None
        version = self._subtitle_version()
        rows = dict(self.lib.get_chapter(version, book, chapter))
        if not rows:
            return None
        wanted = [int(v) for v in (item.get('verses') or [])]
        if not wanted:
            wanted = sorted(rows)                      # 절 지정이 없으면 장 전체
        verses = [{'n': n, 'text': rows[n]} for n in wanted if n in rows]
        if not verses:
            return None
        name = self.lib._display_book_name(book, [version]) or ''
        ns = [v['n'] for v in verses]
        span = f"{ns[0]}-{ns[-1]}" if ns[0] != ns[-1] else f"{ns[0]}"
        ref = f"[{name} {chapter}장 {span}절]" if name else f"[{chapter}:{span}]"
        return {'ref': ref, 'verses': verses, 'version': version}

    def _broadcast_slide(self):
        """현재 슬라이드를 자막 창과 조작 화면 양쪽에 민다.

        상태를 백엔드 한 곳에만 두고 밀어주는 이유는 장바구니(_broadcast_cart)와
        같다 — 창마다 제 상태를 가지면 반드시 어긋난다. 받는 쪽은 **다시 그리기만**
        하고 되쓰지 않으므로 메아리가 없다."""
        try:
            payload = self.get_slide()
        except Exception:
            payload = {'ok': False}
        self._push('onSlideChanged', payload)
        win = self._subtitle_window
        if win is not None:
            try:
                blob = json.dumps(payload, ensure_ascii=False)
                win.evaluate_js(f"window.renderSlide && window.renderSlide({blob})")
            except Exception:
                # 창이 닫혔다 — 낡은 핸들을 버린다(장바구니 창과 동일 처리).
                self._subtitle_window = None

    def _broadcast_cart(self, items):
        """Push the current cart to EVERY window that shows it — the main window's
        drawer (``onCartChanged``) and the pop-out window (its own
        ``renderCartItems`` global) — so add/remove/reorder in either stays in
        sync live (FEAT-07 실시간 양방향 동기화). The receivers only RE-RENDER (they
        never write back), so there's no echo loop."""
        self._push('onCartChanged', items)
        win = self._cart_window
        if win is not None:
            try:
                payload = json.dumps(items, ensure_ascii=False)
                win.evaluate_js(
                    f"window.renderCartItems && window.renderCartItems({payload})")
            except Exception:
                # Window was closed out from under us — drop the stale handle.
                self._cart_window = None

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

    def copy_text(self, text):
        """Put arbitrary text on the clipboard (노트 모아보기 일괄 복사 등). Tells the
        monitor so it doesn't re-detect the write. Returns {ok}."""
        text = str(text or '')
        if not text:
            return {'ok': False}
        self._clip_write(text)
        try:
            self.lib.notify_clipboard_written(text)
        except Exception:
            pass
        return {'ok': True}

    def export_text_file(self, text, suggested_name='bibleclip_notes.txt'):
        """Save text to a user-chosen file via the native Save dialog (노트 일괄
        텍스트 파일 내보내기). Returns {ok, path} or {ok:False, error}. No-op
        (ok:False) without a window/backend, so headless tests stay safe."""
        text = str(text or '')
        if self._window is None:
            return {'ok': False, 'error': 'no window'}
        try:
            import webview  # lazy: keep api.py headless-importable
            result = self._window.create_file_dialog(
                webview.SAVE_DIALOG, save_filename=str(suggested_name or 'notes.txt'))
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        # create_file_dialog → path str, (path,) tuple, or None/'' on cancel.
        path = result[0] if isinstance(result, (list, tuple)) and result else result
        if not path:
            return {'ok': False, 'error': 'cancelled'}
        try:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        return {'ok': True, 'path': path}
