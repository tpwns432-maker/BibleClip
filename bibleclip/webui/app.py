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
# 설치 파일을 바로 받지 않고 공식 '안내 페이지'를 연다(반복 실행 때마다 설치본이
# 자동 다운로드되는 불편 제거 — 사용자가 페이지에서 직접 받도록).
DOTNET_PAGE_URL = 'https://dotnet.microsoft.com/download/dotnet-framework/net48'
WEBVIEW2_PAGE_URL = 'https://developer.microsoft.com/microsoft-edge/webview2/'


def _is_runtime_error(exc):
    """True if an exception looks like the pywebview(winforms) → pythonnet → .NET
    Framework CLR initialization failure ('Failed to resolve
    Python.Runtime.Loader.Initialize …') — i.e. .NET Framework < 4.7.2 or
    missing/broken on the user's PC. Matched on the exception text only."""
    s = f'{type(exc).__name__}: {exc}'.lower()
    return any(k in s for k in (
        'python.runtime', 'pythonnet', 'clr_loader', 'loader.initialize',
        'coreclr', 'mscoree', 'winforms', '.net framework'))


def _dotnet_release():
    """Installed .NET Framework 4.x 'Release' DWORD, or None. >= 461808 = 4.7.2+
    (pywebview/pythonnet 최소요건)."""
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full') as k:
            rel, _ = winreg.QueryValueEx(k, 'Release')
            return int(rel)
    except Exception:
        return None


def _webview2_version():
    """Installed Evergreen WebView2 Runtime version string, or None. Reads the
    EdgeUpdate client key for the stable WebView2 GUID across per-machine(64/32)
    and per-user locations — Microsoft's documented detection method."""
    try:
        import winreg
    except Exception:
        return None
    guid = '{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}'
    base = r'SOFTWARE\Microsoft\EdgeUpdate\Clients' + '\\' + guid
    base32 = r'SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients' + '\\' + guid
    for hive, path in ((winreg.HKEY_LOCAL_MACHINE, base32),
                       (winreg.HKEY_LOCAL_MACHINE, base),
                       (winreg.HKEY_CURRENT_USER, base)):
        try:
            with winreg.OpenKey(hive, path) as k:
                pv, _ = winreg.QueryValueEx(k, 'pv')
                if pv and pv != '0.0.0.0':
                    return pv
        except Exception:
            continue
    return None


# 한국 보안/금융 모듈 식별 키워드. 미서명 프로세스의 CLR/네트워크를 가로채 시작 실패를
# 일으키는 흔한 주범 — 진단 로그에 "무엇이 깔려 있는지"를 남긴다.
_SECURITY_KW = (
    'ahnlab', 'v3', '안랩', 'safe transaction', 'astx', 'asdsvc', 'truguard',
    'nprotect', '알약', 'estsoft', 'veraport', '베라포트', 'magicline', '매직라인',
    'inisafe', 'touchen', 'wizvera', '위즈베라', 'crossex', 'delfino', 'hauri', '하우리',
    'tachyon', 'mcafee', 'norton', 'kaspersky', 'avast', 'bitdefender', 'sophos',
)


def _security_software():
    """Installed security/finance-module Windows services matching known keywords
    (service name or DisplayName). Sorted list of labels; best-effort."""
    try:
        import winreg
    except Exception:
        return []
    found = set()
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                            r'SYSTEM\CurrentControlSet\Services') as svc:
            i = 0
            while True:
                try:
                    name = winreg.EnumKey(svc, i)
                except OSError:
                    break
                i += 1
                disp = ''
                try:
                    with winreg.OpenKey(svc, name) as sk:
                        disp, _ = winreg.QueryValueEx(sk, 'DisplayName')
                except Exception:
                    disp = ''
                hay = (name + ' ' + (disp or '')).lower()
                if any(kw in hay for kw in _SECURITY_KW):
                    found.add(disp or name)
    except Exception:
        pass
    return sorted(found)


def _diagnostics(exc):
    """Probe the REAL startup environment so we stop guessing: is .NET present? is
    WebView2 present? which security software is installed? Drives the log + the
    guide branch."""
    rel = _dotnet_release()
    return {
        'net_release': rel,
        'net_ok': bool(rel and rel >= 461808),   # 4.7.2+
        'webview2': _webview2_version(),
        'security': _security_software(),
        'runtime_match': _is_runtime_error(exc),
    }


def _log_startup_error(exc, diag):
    """Append the REAL exception + environment probe to userdata/startup_error.log.
    We used to discard the exception and just show the .NET guide (flying blind);
    this turns any failing PC into a precise diagnosis."""
    try:
        import traceback
        import platform
        from datetime import datetime
        from bibleclip.config import get_userdata_dir
        path = os.path.join(get_userdata_dir(), 'startup_error.log')
        with open(path, 'a', encoding='utf-8') as f:
            f.write('=' * 64 + '\n')
            f.write('[%s] BibleClip v%s 시작 실패\n'
                    % (datetime.now().isoformat(timespec='seconds'), __version__))
            f.write('OS: %s\n' % platform.platform())
            f.write('.NET Release: %s (>=461808/4.7.2+: %s)\n'
                    % (diag.get('net_release'), diag.get('net_ok')))
            f.write('WebView2: %s\n' % (diag.get('webview2') or '(미설치/미검출)'))
            f.write('보안 SW(설치): %s\n'
                    % (', '.join(diag.get('security') or []) or '(미검출)'))
            f.write('runtime_match(.NET 휴리스틱): %s\n' % diag.get('runtime_match'))
            f.write('예외:\n')
            f.write(''.join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
            f.write('\n')
    except Exception:
        pass


def _show_runtime_error(diag):
    """Native last-resort guide, branched on the ACTUAL environment. Uses ONLY
    stdlib (Win32 message box + browser) so it works with no .NET/WebView2/server.
    .NET 없음→.NET 안내, WebView2 없음→WebView2 안내, 둘 다 있으면→보안 차단 안내."""
    lang = i18n.resolve_ui_lang()
    if not diag.get('net_ok'):
        title, body, url = (i18n.t('dotnet.errTitle', lang),
                            i18n.t('dotnet.errBody', lang), DOTNET_PAGE_URL)
    elif not diag.get('webview2'):
        title, body, url = (i18n.t('webview2.errTitle', lang),
                            i18n.t('webview2.errBody', lang), WEBVIEW2_PAGE_URL)
    else:
        title, body, url = (i18n.t('secblock.errTitle', lang),
                            i18n.t('secblock.errBody', lang), None)
    try:
        import ctypes
        ctypes.windll.user32.MessageBoxW(0, body, title, 0x10)  # MB_OK | MB_ICONERROR
    except Exception:
        pass
    if url:
        try:
            import webbrowser
            webbrowser.open(url)
        except Exception:
            pass


def _strip_motw():
    """Remove the Mark-of-the-Web (NTFS 'Zone.Identifier' ADS) from our bundled
    binaries BEFORE the .NET CLR import.

    A ZIP downloaded from the web is tagged 'from the Internet'; Windows Explorer
    propagates that tag to EVERY extracted file. .NET Framework then refuses to
    load the bundled `Python.Runtime.dll` (pywebview→pythonnet→clr CLR bridge)
    because loadFromRemoteSources is off by default → the app dies with
    'Failed to resolve Python.Runtime.Loader.Initialize'. Locally-copied builds
    (no tag) work; only DOWNLOADED ones break — the exact field symptom.

    Stripping the tag here (before `import webview` → clr) fixes it with no
    user action (no right-click→Unblock needed). A onedir build keeps its files
    on disk, so the tag persists across runs → we clear once and drop a marker.
    Best-effort: no-op when not frozen / not Windows / files read-only (the
    bundled BibleClipWeb.exe.config's loadFromRemoteSources covers that case)."""
    if not IS_WINDOWS:
        return
    import sys
    base = getattr(sys, '_MEIPASS', None)
    if not base:
        return  # source run, not frozen — nothing bundled to unblock
    marker = os.path.join(base, '.motw_cleared')
    if os.path.exists(marker):
        return
    for dirpath, _dirs, files in os.walk(base):
        for name in files:
            if name.lower().endswith(('.dll', '.pyd', '.exe')):
                try:
                    os.remove(os.path.join(dirpath, name) + ':Zone.Identifier')
                except OSError:
                    pass  # no ADS on this file, or read-only — skip
    try:
        open(marker, 'w').close()   # clear once; later launches skip the walk
    except OSError:
        pass


def main():
    """Public entry point. Wraps the real startup: first strip the Mark-of-the-Web
    from bundled DLLs (downloaded ZIPs tag them → .NET blocks Python.Runtime.dll),
    then on any Windows startup failure LOG the real exception + an environment
    probe and show a guide branched on what's ACTUALLY wrong (.NET / WebView2 /
    보안·차단) instead of always blaming .NET. Non-runtime errors propagate."""
    try:
        _strip_motw()
    except Exception:
        pass
    try:
        _main()
    except Exception as exc:
        diag = None
        if IS_WINDOWS:
            try:
                diag = _diagnostics(exc)
                _log_startup_error(exc, diag)
            except Exception:
                diag = None
        if IS_WINDOWS and _is_runtime_error(exc):
            _show_runtime_error(diag or {'net_ok': False})
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

    # Every child window we spawn (right-click 사전 팝업 등) is tracked here so the
    # main window's close can tear them all down (BUG-SYS). pywebview's event loop
    # (webview.start) runs until ALL windows close, so a lingering child kept the
    # process alive with an orphaned window on the desktop ('zombie').
    _child_windows = []

    def _on_closing():
        # Persist window geometry + any in-memory state (last position, etc.).
        try:
            library.settings['web_geometry'] = {
                'w': window.width, 'h': window.height, 'x': window.x, 'y': window.y,
            }
        except Exception:
            pass
        library.save_settings()
        # Tear down any open child windows so closing the main window exits the
        # whole app cleanly (no orphaned 사전/장바구니 popups left on the desktop).
        for child in list(_child_windows):
            try:
                child.destroy()
            except Exception:
                pass  # already closed by the user, or destroy unsupported
        _child_windows.clear()

    window.events.closing += _on_closing

    def _open_popup(title, html):
        # Independent dict window (right-click). Unique name per call so
        # pywebview doesn't reuse/replace an existing window. Tracked + self-
        # unregistering so the main window's close can destroy any still open.
        child = webview.create_window(title, html=html, width=460, height=560,
                                      min_size=(360, 360))
        _child_windows.append(child)
        def _forget(*_):  # pywebview may pass the window to the handler
            if child in _child_windows:
                _child_windows.remove(child)
        try:
            child.events.closed += _forget
        except Exception:
            pass
        return child

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
