"""BibleClip web UI entry point — launches the pywebview window.

Runs the High-redesign front-end (web/) in a native window, exposing the
Library core to JavaScript via the Api bridge. The CustomTkinter app
(bibleclip.ui.app) is unaffected; this is a separate, parallel entry point.
"""
import html as _html
import os

from bibleclip.config import __version__, get_resource_dir
from bibleclip.core.library import Library
from bibleclip.killswitch import check_killswitch
from bibleclip.webui.api import Api


def _index_path():
    return os.path.join(get_resource_dir(), 'web', 'index.html')


def _blocked_html(message):
    """Full-window notice shown when the remote kill switch blocks this build."""
    safe = _html.escape(message).replace('\n', '<br>')
    return f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<style>
  html,body{{margin:0;height:100%;
    font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans CJK KR',sans-serif;
    background:#1b1d22;color:#e8e8ea;
    display:flex;align-items:center;justify-content:center;}}
  .box{{text-align:center;padding:48px;max-width:440px;}}
  .title{{font-size:21px;font-weight:700;margin-bottom:18px;color:#ff6b6b;}}
  .msg{{font-size:15px;line-height:1.7;color:#c9c9cf;}}
</style></head>
<body><div class="box">
  <div class="title">BibleClip</div>
  <div class="msg">{safe}</div>
</div></body></html>"""


def main():
    import webview  # imported lazily so api.py stays headless-testable

    # Remote kill switch: stop here (showing only the notice) if this build has
    # been disabled by the maintainer. Fail-open — a fetch failure returns
    # (False, '') so a network outage never blocks startup.
    blocked, message = check_killswitch()
    if blocked:
        webview.create_window(
            "BibleClip",
            html=_blocked_html(message or "이 버전은 더 이상 사용할 수 없습니다."),
            width=520, height=360, min_size=(420, 300),
        )
        webview.start()
        return

    # Anonymous, fail-open 'app launched' ping (실사용 카운터, Phase 1). Runs on a
    # daemon thread so it never delays or blocks startup; offline = silent no-op.
    try:
        from bibleclip.usage import ping_usage_async
        ping_usage_async()
    except Exception:
        pass

    # Pre-warm the Kiwi 형태소 분석기 on a daemon thread (9차 Phase 2). This forces
    # its heavy/native construction to happen here, on a normal Python thread —
    # NOT lazily on the pywebview bridge thread during the first multi-keyword
    # search, which crashed the process. Fail-soft: any error just leaves search
    # on its trigram fallback.
    try:
        import threading
        from bibleclip import morph
        threading.Thread(target=morph.warmup, daemon=True).start()
    except Exception:
        pass

    library = Library()
    api = Api(library)

    # Restore the last web-window size/position (separate from the desktop app's
    # tk-format 'geometry' so the two UIs don't clobber each other's window).
    geo = library.settings.get('web_geometry') or {}
    kw = dict(width=int(geo.get('w') or 1100), height=int(geo.get('h') or 780))
    if geo.get('x') is not None and geo.get('y') is not None:
        kw['x'], kw['y'] = int(geo['x']), int(geo['y'])

    window = webview.create_window(
        f"BibleClip v{__version__}",
        url=_index_path(),
        js_api=api,
        min_size=(900, 650),
        text_select=True,  # allow selecting verse text (CSS limits it to panels)
        **kw,
    )
    api.set_window(window)  # lets the clipboard monitor push events back to JS

    def _on_closing():
        # Persist window geometry + any in-memory state (last position, etc.).
        try:
            library.settings['web_geometry'] = {
                'w': window.width, 'h': window.height, 'x': window.x, 'y': window.y,
            }
        except Exception:
            pass
        library.save_settings()

    window.events.closing += _on_closing

    _popup_count = [0]

    def _open_popup(title, html):
        # Independent dict window (right-click). Unique name per call so
        # pywebview doesn't reuse/replace an existing window.
        _popup_count[0] += 1
        webview.create_window(title, html=html, width=460, height=560,
                              min_size=(360, 360))

    api.set_popup_factory(_open_popup)
    webview.start()


if __name__ == "__main__":
    main()
