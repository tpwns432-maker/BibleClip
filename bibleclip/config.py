"""Configuration: version, platform flags, fonts, paths, GitHub URLs."""
import os
import sys

from bibleclip._version import __version__

IS_WINDOWS = sys.platform.startswith('win')

# Single app-wide font: each OS's default Korean Gothic (always pre-installed),
# used uniformly for UI, scripture body, and the log.
if sys.platform == 'darwin':
    APP_FONT = 'Apple SD Gothic Neo'
elif IS_WINDOWS:
    APP_FONT = 'Malgun Gothic'
else:  # Linux / other
    APP_FONT = 'Noto Sans CJK KR'
UI_FONT = BODY_FONT = MONO_FONT = APP_FONT

# Serif font for scripture body (editorial "book" feel); each is OS-default.
if sys.platform == 'darwin':
    SERIF_FONT = 'AppleMyungjo'
elif IS_WINDOWS:
    SERIF_FONT = '바탕'
else:
    SERIF_FONT = 'Noto Serif CJK KR'

GITHUB_OWNER = "tpwns432-maker"
GITHUB_REPO = "BibleClip"
UPDATE_CHECK_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
RELEASES_PAGE_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}/releases/latest"
# Remote kill switch manifest (public raw file). The maintainer flips
# "disabled" to true (or raises "min_version") to remotely stop distributed
# copies. Fetched anonymously at startup; any failure is fail-open (see
# bibleclip.killswitch). Keep the repo PUBLIC so this URL stays reachable.
KILLSWITCH_URL = f"https://raw.githubusercontent.com/{GITHUB_OWNER}/{GITHUB_REPO}/main/killswitch.json"
# Optional anonymous "app launched" ping (실사용 카운터, Phase 1). Best-effort,
# fail-open, NO personal data — just an anonymous GET in a background thread.
# Defaults to the public repo API endpoint (the maintainer owns it); set to None
# to disable, or repoint at a dedicated analytics/count endpoint.
USAGE_PING_URL = f"https://api.github.com/repos/{GITHUB_OWNER}/{GITHUB_REPO}"

def _is_mac_app():
    """True when running from inside a frozen macOS .app bundle."""
    return (getattr(sys, 'frozen', False) and sys.platform == 'darwin'
            and os.path.dirname(sys.executable).endswith(os.path.join('Contents', 'MacOS')))


def get_app_dir():
    """Folder that holds the program: BibleClip.exe's folder, the folder the
    macOS .app sits in, or the source tree. The updater replaces files here."""
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if _is_mac_app():
            # exe_dir = /path/BibleClip.app/Contents/MacOS -> /path
            return os.path.dirname(os.path.dirname(os.path.dirname(exe_dir)))
        return exe_dir
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


MAC_DATA_DIR = os.path.join('~', 'Library', 'Application Support', 'BibleClip')


def get_base_dir():
    """Writable data folder: settings, userdata/, bible_versions/, fonts/.

    Windows and the source tree keep it next to the program (get_app_dir). A
    macOS .app uses ~/Library/Application Support/BibleClip (v1.2.1~): next to
    the .app is /Applications, which a standard account can't write to, and an
    app run from the DMG or moved inside a folder is "translocated" to a
    read-only temp path, where settings and notes were silently lost.
    """
    if _is_mac_app():
        return os.path.expanduser(MAC_DATA_DIR)
    return get_app_dir()

def get_resource_dir():
    """Get bundled resource directory (for --add-data assets inside exe)."""
    if getattr(sys, 'frozen', False):
        return sys._MEIPASS
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def system_env():
    """Environment for running SYSTEM binaries (e.g. pbpaste) from a frozen app.

    PyInstaller injects DYLD_/LD_LIBRARY_PATH pointing at the bundle's libs,
    which can break system executables. Restore the original values (saved by
    the bootloader with a _ORIG suffix) so the child runs in a clean env.
    """
    env = dict(os.environ)
    for var in ('DYLD_LIBRARY_PATH', 'DYLD_FRAMEWORK_PATH', 'LD_LIBRARY_PATH'):
        orig = env.pop(var + '_ORIG', None)
        if orig:
            env[var] = orig
        else:
            env.pop(var, None)
    # A .app launched from Finder has no LANG, so pbpaste emits '?' for Korean.
    # Force a UTF-8 locale so non-ASCII text round-trips correctly.
    env['LANG'] = 'en_US.UTF-8'
    env['LC_ALL'] = 'en_US.UTF-8'
    return env

BASE_DIR = get_base_dir()
SETTINGS_FILE = "bibleclip_settings.json"
# App-managed per-install config folder (premium flag etc.), separate from the
# user's UI settings file. Meant to be written by a licensing backend / the
# maintainer. See bibleclip.userconfig.
USERDATA_DIR = "userdata"


def get_userdata_dir():
    """Writable folder for app-managed config (userdata/), in the data folder.
    Created on demand; failures are swallowed (caller falls back to defaults)."""
    d = os.path.join(BASE_DIR, USERDATA_DIR)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d
# Pre-1.6 settings filename. Read once (and only as a fallback) so existing
# users keep their version order, last position, theme, window size, etc.
LEGACY_SETTINGS_FILE = "autobible_settings.json"
BIBLE_DIR = "bible_versions"


def candidate_data_roots():
    """Folders to search for data (bible_versions, original_lang), in order.

    BASE_DIR first (the data folder — lets users drop in extra data).
    On a frozen build also the executable's own dir, and inside a macOS .app
    Contents/Resources, where bundled data lives (v1.2.1~) so it survives App
    Translocation and the app being moved. Data used to sit in Contents/MacOS,
    but codesign treats everything there as code and an unsigned .SQLite3 made
    Gatekeeper report the whole app as "damaged".
    """
    roots = [BASE_DIR]
    if getattr(sys, 'frozen', False):
        exe_dir = os.path.dirname(sys.executable)
        if exe_dir not in roots:
            roots.append(exe_dir)
        if sys.platform == 'darwin':
            res = os.path.join(os.path.dirname(exe_dir), 'Resources')
            if res not in roots:
                roots.append(res)
        try:
            mei = sys._MEIPASS
            if mei not in roots:
                roots.append(mei)
        except Exception:
            pass
    return roots


def resolve_data_dir(name):
    """First existing candidate root containing `name`, else BASE_DIR/name."""
    for root in candidate_data_roots():
        p = os.path.join(root, name)
        if os.path.isdir(p):
            return p
    return os.path.join(BASE_DIR, name)


def data_dirs(name):
    """Every existing `name` folder across the candidate roots, in priority order.

    Unlike resolve_data_dir (first hit only), callers that load files merge all
    of them: on macOS the bible_versions folder in the user's data folder
    must ADD to the bible bundled inside it, not hide it. Symlinked duplicates
    (e.g. Contents/MacOS/x -> Contents/Resources/x) are listed once.
    """
    out, seen = [], set()
    for root in candidate_data_roots():
        p = os.path.join(root, name)
        if os.path.isdir(p):
            real = os.path.realpath(p)
            if real not in seen:
                seen.add(real)
                out.append(p)
    return out


# What the data folder holds, copied over once when it moves (see prepare_data_dir).
_MIGRATE_ITEMS = (SETTINGS_FILE, LEGACY_SETTINGS_FILE, USERDATA_DIR, BIBLE_DIR,
                  'fonts', 'original_lang')


def prepare_data_dir(base=None, legacy=None):
    """Make sure the data folder exists before anything reads settings.

    When it is not the program folder (macOS: Application Support), copy the
    user's files from the old place next to the .app once — only while the new
    folder has no settings/userdata yet, and copying, never moving, so the old
    files stay as a fallback. bible_versions/ is always created there so that
    files written into it (aliases_override.json, added bibles) never land
    inside the signed .app bundle. Returns the names copied."""
    base = base or BASE_DIR
    legacy = legacy or get_app_dir()
    import shutil
    copied = []
    try:
        os.makedirs(base, exist_ok=True)
    except Exception:
        return copied
    if os.path.realpath(base) == os.path.realpath(legacy):
        return copied
    fresh = not (os.path.exists(os.path.join(base, SETTINGS_FILE))
                 or os.path.exists(os.path.join(base, USERDATA_DIR)))
    if fresh:
        for name in _MIGRATE_ITEMS:
            src, dst = os.path.join(legacy, name), os.path.join(base, name)
            if not os.path.exists(src) or os.path.exists(dst):
                continue
            try:
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
                copied.append(name)
            except Exception:
                pass
    try:
        os.makedirs(os.path.join(base, BIBLE_DIR), exist_ok=True)
    except Exception:
        pass
    return copied
