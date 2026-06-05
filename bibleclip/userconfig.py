"""Per-install app config (userdata/config.json) — Phase 1 business guard.

Separate from bibleclip_settings.json (user UI prefs): this file is meant to be
written by a licensing backend or the maintainer to flip the premium flag. Reads
are fail-soft — a missing or malformed file yields the permissive default so the
app never locks itself out on a bad/empty config.

NOTE ON THE DEFAULT: there is no payment backend yet, so the default is
PERMISSIVE (is_premium=True → full features). The free-tier gates (single card,
locked chapter shortcut, notes/badge off) are implemented and honor this flag;
when monetization launches the backend simply writes {"is_premium": false}.
"""
import json
import os

from bibleclip.config import get_userdata_dir

CONFIG_FILE = "config.json"

DEFAULTS = {
    "is_premium": True,   # permissive until a licensing backend exists (see above)
}


def config_path():
    return os.path.join(get_userdata_dir(), CONFIG_FILE)


def load_user_config():
    """Return the user config merged over DEFAULTS. Fail-soft on any error."""
    cfg = dict(DEFAULTS)
    try:
        with open(config_path(), "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            cfg.update(data)
    except Exception:
        pass
    return cfg


def is_premium():
    """True when the install is premium (or no/!malformed config → default True)."""
    return bool(load_user_config().get("is_premium", True))
