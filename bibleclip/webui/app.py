"""BibleClip web UI entry point — launches the pywebview window.

Runs the High-redesign front-end (web/) in a native window, exposing the
Library core to JavaScript via the Api bridge. The CustomTkinter app
(bibleclip.ui.app) is unaffected; this is a separate, parallel entry point.
"""
import html as _html
import os

from bibleclip import i18n
from bibleclip.config import __version__, get_resource_dir, IS_WINDOWS
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


def _conn_error_html(lang):
    """Friendly, bilingual guide shown when the local page fails to load
    (ERR_CONNECTION_REFUSED) — almost always security software / a firewall
    blocking the 127.0.0.1 loopback the WebView uses, or the local server thread
    being blocked from starting. Rendered via load_html → NavigateToString, so it
    displays WITHOUT the loopback server (it shows even when that's exactly what's
    blocked). pywebview already binds a random free port on 127.0.0.1, so a fixed-
    port collision isn't the cause — the guidance targets the real (external) one."""
    def esc(k):
        return _html.escape(i18n.t(k, lang))
    title = esc('conn.errTitle')
    intro = esc('conn.errIntro')
    steps = ''.join(f'<li>{esc(k)}</li>'
                    for k in ('conn.errAdmin', 'conn.errWhitelist', 'conn.errReboot'))
    return f"""<!DOCTYPE html>
<html lang="{_html.escape(lang)}"><head><meta charset="utf-8">
<style>
  html,body{{margin:0;height:100%;
    font-family:'Malgun Gothic','Apple SD Gothic Neo','Noto Sans CJK KR',sans-serif;
    background:#1b1d22;color:#e8e8ea;
    display:flex;align-items:center;justify-content:center;}}
  .box{{max-width:480px;padding:44px 48px;}}
  .title{{font-size:20px;font-weight:700;margin-bottom:14px;color:#ffb454;}}
  .msg{{font-size:14.5px;line-height:1.7;color:#c9c9cf;margin-bottom:18px;}}
  ol{{margin:0;padding-left:20px;}}
  li{{font-size:14px;line-height:1.9;color:#e3e3e7;}}
</style></head>
<body><div class="box">
  <div class="title">BibleClip — {title}</div>
  <div class="msg">{intro}</div>
  <ol>{steps}</ol>
</div></body></html>"""


# Microsoft 공식 고정 리다이렉트 → .NET Framework 4.8 오프라인 설치본
# (NDP48-x86-x64-AllOS-ENU.exe, ~121MB)을 브라우저가 곧바로 내려받는다(검증된 fwlink).
DOTNET_DOWNLOAD_URL = 'https://go.microsoft.com/fwlink/?linkid=2088631'


def _is_runtime_error(exc):
    """True if an exception looks like the pywebview(winforms) → pythonnet → .NET
    Framework CLR initialization failure ('Failed to resolve
    Python.Runtime.Loader.Initialize …') — i.e. .NET Framework < 4.7.2 or
    missing/broken on the user's PC. Matched on the exception text only."""
    s = f'{type(exc).__name__}: {exc}'.lower()
    return any(k in s for k in (
        'python.runtime', 'pythonnet', 'clr_loader', 'loader.initialize',
        'coreclr', 'mscoree', 'winforms', '.net framework'))


def _show_runtime_error():
    """Last-resort guide when the .NET/pywebview backend can't even start. Uses
    ONLY stdlib (a Win32 message box + the browser) so it works with no .NET, no
    WebView2, and no local server — exactly the broken state it reports. Without
    this the user just gets PyInstaller's cryptic 'Failed to execute script' crash.
    [확인] → the .NET Framework 4.8 installer downloads directly."""
    lang = i18n.resolve_ui_lang()
    title = i18n.t('dotnet.errTitle', lang)
    body = i18n.t('dotnet.errBody', lang)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, body, title, 0x10)  # MB_OK | MB_ICONERROR
    except Exception:
        pass
    try:
        import webbrowser
        webbrowser.open(DOTNET_DOWNLOAD_URL)
    except Exception:
        pass


def main():
    """Public entry point. Wraps the real startup so a .NET/CLR backend failure
    becomes a friendly native guide instead of a raw PyInstaller crash. Unrelated
    errors propagate unchanged."""
    try:
        _main()
    except Exception as exc:
        if IS_WINDOWS and _is_runtime_error(exc):
            _show_runtime_error()
            return
        raise


def _main():
    import webview  # imported lazily so api.py stays headless-testable

    # Remote kill switch: stop here (showing only the notice) if this build has
    # been disabled by the maintainer. Fail-open — a fetch failure returns
    # (False, '') so a network outage never blocks startup.
    blocked, message = check_killswitch()
    if blocked:
        # No Library yet on this path → resolve the UI language from the settings
        # file directly. A maintainer-supplied `message` is shown verbatim (any
        # language); only our default fallback is localized.
        lang = i18n.resolve_ui_lang()
        webview.create_window(
            "BibleClip",
            html=_blocked_html(message or i18n.t('killswitch.blocked', lang)),
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

    library = Library()
    api = Api(library)

    # v1.0.5: 한국어 역색인(스마트 검색)을 데몬 스레드에서 미리 빌드 — 첫 다중 키워드
    # 검색의 ~0.6초 빌드 지연을 숨긴다. 순수 dict/set 이라 네이티브 크래시 위험이 없다
    # (v1.0.4 Kiwi 워밍업 크래시와 달리 안전). 실패해도 lazy 빌드로 폴백되므로 fail-soft.
    try:
        import threading

        def _warm_index():
            try:
                pv = library.primary_version()
                db = library.dbs.get(pv)
                if db is not None and not db.is_english:
                    db.inverted_index()
            except Exception:
                pass
        threading.Thread(target=_warm_index, daemon=True).start()
    except Exception:
        pass

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

    # Startup connection watchdog (Fix-C): if the front-end never reaches the
    # bridge (get_initial) within the timeout, the local HTTP page failed to load
    # — ERR_CONNECTION_REFUSED, typically security software/firewall blocking the
    # 127.0.0.1 loopback the WebView uses, or the local server thread being
    # blocked. Replace the bare Chromium error with a friendly bilingual guide via
    # load_html (NavigateToString — no server, so it shows even when the loopback
    # is what's blocked). A normal launch fires get_initial in ~1-2s and stands
    # the watchdog down well within the generous timeout.
    import threading

    def _conn_watchdog():
        if not api._booted.wait(15):
            try:
                window.load_html(_conn_error_html(i18n.resolve_ui_lang(library.settings)))
            except Exception:
                pass
    threading.Thread(target=_conn_watchdog, daemon=True).start()

    webview.start()


if __name__ == "__main__":
    main()
