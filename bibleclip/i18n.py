"""Backend-side i18n for Python-rendered surfaces that the front-end's
``web/js/i18n.js`` cannot reach — the kill-switch full-window page, the
right-click dictionary popup windows, and the 출력 설정 preview string.

**Single source of truth:** this reads the SAME ``web/locales/<lang>.json`` the
front-end uses (loaded once per language, cached), so the two never drift. The
active UI language is the persisted ``ui_lang`` setting (the front-end writes it
on every switch); it falls back to Korean when missing/unreadable.

Pure stdlib (json/os), no native deps → frozen-safe (PyInstaller). The locale
files are bundled via ``--add-data "web;web"`` and resolved with
``config.get_resource_dir()`` exactly like ``api.get_locale``.
"""
import json
import os

DEFAULT_LANG = 'ko'

_cache = {}   # lang -> {key: str}  (empty dict cached on miss to avoid re-reads)


def _locale_path(lang):
    from bibleclip.config import get_resource_dir
    return os.path.join(get_resource_dir(), 'web', 'locales', lang + '.json')


def _table(lang):
    """The (cached) string table for ``lang`` — {} if the file is absent/bad."""
    if lang in _cache:
        return _cache[lang]
    data = {}
    try:
        with open(_locale_path(lang), 'r', encoding='utf-8') as f:
            loaded = json.load(f)
        if isinstance(loaded, dict):
            data = loaded
    except Exception:
        data = {}
    _cache[lang] = data
    return data


def t(key, lang=DEFAULT_LANG, **fmt):
    """Translate ``key`` for ``lang``: current → ko → the key itself.

    Optional ``**fmt`` are ``str.format`` substituted (e.g. ``code=...`` for
    ``dict.popupTitle`` = "사전 · {code}"). A formatting error leaves the raw
    string rather than raising — these run on UI-render paths."""
    if not isinstance(lang, str) or not lang:
        lang = DEFAULT_LANG
    val = _table(lang).get(key)
    if val is None and lang != DEFAULT_LANG:
        val = _table(DEFAULT_LANG).get(key)
    if val is None:
        val = key
    if fmt:
        try:
            val = val.format(**fmt)
        except Exception:
            pass
    return val


def resolve_ui_lang(settings=None):
    """The active UI language code.

    With a ``settings`` mapping (an Api route has ``self.lib.settings``) read it
    from there. Without one (the kill-switch path runs before a Library exists)
    read the persisted settings file directly. Korean on any miss."""
    if settings is not None:
        try:
            lang = settings.get('ui_lang')
        except Exception:
            lang = None
        return lang if isinstance(lang, str) and lang else DEFAULT_LANG
    try:
        from bibleclip.config import SETTINGS_FILE
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            d = json.load(f)
        lang = d.get('ui_lang')
        return lang if isinstance(lang, str) and lang else DEFAULT_LANG
    except Exception:
        return DEFAULT_LANG
