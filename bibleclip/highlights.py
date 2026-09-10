"""절 내부 단어 하이라이트 (형광펜) — sub-verse text ranges (v1.1.12).

Stored in userdata/user_highlights.json as:
    { "<book>:<chapter>:<verse>:<version>": [ {"s":int,"e":int,"t":str,"c":str,
                                               "ts":"ISO8601"}, ... ] }
where book is our 10..730 numbering.

``s``/``e`` are character offsets into the RAW verse text **of that one
version** — highlights are per-version by design, so 개역개정에 칠한 형광펜이
KJV 셀로 번지지 않는다(역본마다 번역어가 달라 오프셋을 공유할 수 없다).

``t`` is the highlighted snippet itself. Offsets alone are fragile: a bible DB
refresh or a re-bundled 역본 shifts the text and every stored range would then
paint the wrong words. The front-end therefore verifies ``t`` before painting,
re-finds it on mismatch, and drops the highlight if it's gone — 발표 중 엉뚱한
곳이 칠해지는 것보다 사라지는 게 낫다는 판단.

Stored range lists are kept sorted and non-overlapping so the renderer can walk
them in one pass. All disk I/O is fail-soft, exactly like notes.py — a missing
or corrupt file just means "no highlights", never a broken app.
"""
import json
import os
from datetime import datetime

from bibleclip.config import get_userdata_dir

HIGHLIGHTS_FILE = "user_highlights.json"

#: The pen colors the UI offers. Anything else is coerced to the first one.
COLORS = ("y", "g", "b", "p")

#: Guards against a runaway file if a caller ever loops: per verse+version.
MAX_RANGES = 64
#: Verse texts are short; a longer snippet means junk input.
MAX_SNIPPET = 400


def _path():
    return os.path.join(get_userdata_dir(), HIGHLIGHTS_FILE)


def _key(book, chapter, verse, version):
    return f"{int(book)}:{int(chapter)}:{int(verse)}:{version}"


def _norm(ranges):
    """Sanitize a range list: drop junk, sort, and remove overlaps.

    The front-end already merges as the user paints (it needs to anyway, to
    redraw live), so this is a safety net for whatever actually reaches disk —
    but it's the renderer's contract, so it's enforced here too: sorted by
    start, never overlapping. On overlap the earlier range wins and the later
    one is trimmed (dropped if nothing is left).
    """
    clean = []
    for r in (ranges or []):
        if not isinstance(r, dict):
            continue
        try:
            s, e = int(r.get("s")), int(r.get("e"))
        except (TypeError, ValueError):
            continue
        if s < 0 or e <= s:
            continue
        c = r.get("c")
        c = c if c in COLORS else COLORS[0]
        t = r.get("t")
        t = t[:MAX_SNIPPET] if isinstance(t, str) else ""
        ts = r.get("ts")
        clean.append({"s": s, "e": e, "t": t, "c": c,
                      "ts": ts if isinstance(ts, str) and ts else
                      datetime.now().isoformat(timespec="seconds")})
    clean.sort(key=lambda r: (r["s"], r["e"]))
    out = []
    for r in clean:
        if out and r["s"] < out[-1]["e"]:
            r["s"] = out[-1]["e"]          # trim the overlap away
            if r["e"] <= r["s"]:
                continue                    # fully swallowed → drop
            r["t"] = ""                     # snippet no longer matches the range
        out.append(r)
        if len(out) >= MAX_RANGES:
            break
    return out


class Highlights:
    """In-memory highlight store backed by userdata/user_highlights.json
    (write-through), mirroring bibleclip.notes.Notes."""

    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            if not isinstance(d, dict):
                return {}
            # Drop anything that isn't a list of ranges so one corrupt entry
            # can't poison the whole store.
            return {k: v for k, v in d.items() if isinstance(v, list)}
        except Exception:
            return {}

    def _save(self):
        try:
            with open(_path(), "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get(self, book, chapter, verse, version):
        """The sorted, non-overlapping range list for one verse+version ([] if
        none)."""
        return self.data.get(_key(book, chapter, verse, version), [])

    def set_verse(self, book, chapter, verse, version, ranges):
        """Replace one verse+version's whole range list (the front-end owns the
        merge/erase semantics and sends the full list on every change, like the
        장바구니). An empty list deletes the entry. Returns the stored list."""
        k = _key(book, chapter, verse, version)
        stored = _norm(ranges)
        if stored:
            self.data[k] = stored
        else:
            self.data.pop(k, None)
        self._save()
        return stored

    def clear_verse(self, book, chapter, verse, version):
        self.data.pop(_key(book, chapter, verse, version), None)
        self._save()
        return True

    def for_chapter(self, book, chapter, version):
        """{verse:int -> [ranges]} for one chapter in one version — this is what
        drives the painting. Keyed by verse so the front-end can index it with
        the DOM's data-v (JSON turns the int keys into strings, same as
        Notes.for_chapter)."""
        prefix = f"{int(book)}:{int(chapter)}:"
        out = {}
        for k, v in self.data.items():
            if not k.startswith(prefix):
                continue
            # key = book:chapter:verse:version — the version itself may contain
            # ':' in principle, so split off only the first three fields.
            parts = k.split(":", 3)
            if len(parts) != 4 or parts[3] != version:
                continue
            try:
                out[int(parts[2])] = v
            except ValueError:
                pass
        return out

    def all(self):
        """Every highlight as a flat list in canonical bible order:
        [{book, chapter, verse, version, s, e, t, c, ts}, ...]. Nothing consumes
        this yet — it's the hook for a future 하이라이트 모아보기 panel, and it
        keeps parity with Notes.all()."""
        out = []
        for k, ranges in self.data.items():
            parts = k.split(":", 3)
            if len(parts) != 4:
                continue
            try:
                b, c, vs = int(parts[0]), int(parts[1]), int(parts[2])
            except ValueError:
                continue
            for r in ranges:
                out.append({"book": b, "chapter": c, "verse": vs,
                            "version": parts[3], "s": r.get("s"), "e": r.get("e"),
                            "t": r.get("t", ""), "c": r.get("c", COLORS[0]),
                            "ts": r.get("ts", "")})
        out.sort(key=lambda h: (h["book"], h["chapter"], h["verse"],
                                h["version"], h["s"]))
        return out
