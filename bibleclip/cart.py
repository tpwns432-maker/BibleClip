"""설교 장바구니 (sermon cart / cue sheet) — verse-reference cue list persisted
to disk so it survives an app restart (FEAT-08).

Stored in userdata/sermon_cart.json as a JSON list of items:
    [{"book_num": int, "chapter": int, "verses": [int, ...], "short_name": str}, ...]

The front-end used to keep the cart only in localStorage, but pywebview serves
the page from 127.0.0.1 on a RANDOM port each launch, so the localStorage origin
(scheme+host+port) changes every run and the previous cart is orphaned — the
'cart resets on restart' bug. Persisting it backend-side (userdata file, surfaced
via get_initial) makes it origin-independent and reliable. All disk I/O is
fail-soft so a missing or corrupt file never breaks the app — it just starts
with an empty cart.
"""
import json
import os

from bibleclip.config import get_userdata_dir

CART_FILE = "sermon_cart.json"


def _path():
    return os.path.join(get_userdata_dir(), CART_FILE)


def _sanitize(items):
    """Coerce arbitrary front-end input into a clean list of cart items, dropping
    anything malformed. Keeps the same shape the front-end stores/reads so a save
    → boot round-trip is lossless."""
    clean = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        try:
            book = int(it.get("book_num", it.get("book")))
            chapter = int(it.get("chapter"))
        except (TypeError, ValueError):
            continue
        verses = []
        for v in (it.get("verses") or []):
            try:
                verses.append(int(v))
            except (TypeError, ValueError):
                pass
        clean.append({"book_num": book, "chapter": chapter, "verses": verses,
                      "short_name": str(it.get("short_name") or "")})
    return clean


class Cart:
    """In-memory sermon-cart store backed by userdata/sermon_cart.json
    (write-through, sanitized on every replace)."""

    def __init__(self):
        self.items = self._load()

    def _load(self):
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            return _sanitize(d) if isinstance(d, list) else []
        except Exception:
            return []

    def _save(self):
        try:
            with open(_path(), "w", encoding="utf-8") as f:
                json.dump(self.items, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def all(self):
        """The current cart as a fresh list copy (boot payload / get_cart)."""
        return list(self.items)

    def replace(self, items):
        """Replace the WHOLE cart with a sanitized copy of ``items`` and persist.
        The front-end owns ordering (drag-and-drop), so it always sends the full
        list — we mirror it rather than diffing. Returns the stored list."""
        self.items = _sanitize(items)
        self._save()
        return list(self.items)
