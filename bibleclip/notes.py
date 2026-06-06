"""묵상 노트 (meditation notes) — verse-anchored personal notes (Phase 3).

Stored in userdata/user_notes.json as:
    { "<book>:<chapter>:<verse>": {"text": str, "ts": "ISO8601"} }
where book is our 10..730 numbering. All disk I/O is fail-soft so a missing or
corrupt file never breaks the app — it just starts with no notes.
"""
import json
import os
from datetime import datetime

from bibleclip.config import get_userdata_dir

NOTES_FILE = "user_notes.json"


def _path():
    return os.path.join(get_userdata_dir(), NOTES_FILE)


def _key(book, chapter, verse):
    return f"{int(book)}:{int(chapter)}:{int(verse)}"


class Notes:
    """In-memory note store backed by userdata/user_notes.json (write-through)."""

    def __init__(self):
        self.data = self._load()

    def _load(self):
        try:
            with open(_path(), "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save(self):
        try:
            with open(_path(), "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def get(self, book, chapter, verse):
        """The note dict {text, ts} for a verse, or None."""
        return self.data.get(_key(book, chapter, verse))

    def set(self, book, chapter, verse, text):
        """Create/update a verse note. Empty text deletes it. Returns the stored
        note dict (or None when deleted)."""
        k = _key(book, chapter, verse)
        text = (text or "").strip()
        if not text:
            self.data.pop(k, None)
            self._save()
            return None
        entry = {"text": text, "ts": datetime.now().isoformat(timespec="seconds")}
        self.data[k] = entry
        self._save()
        return entry

    def delete(self, book, chapter, verse):
        self.data.pop(_key(book, chapter, verse), None)
        self._save()
        return True

    def all(self):
        """Every note as a flat list in canonical bible order:
        [{book, chapter, verse, text, ts}, ...]. Powers the 노트 모아보기 card."""
        out = []
        for k, v in self.data.items():
            try:
                b, c, vs = (int(x) for x in k.split(":"))
            except Exception:
                continue
            out.append({"book": b, "chapter": c, "verse": vs,
                        "text": (v or {}).get("text", ""), "ts": (v or {}).get("ts", "")})
        out.sort(key=lambda n: (n["book"], n["chapter"], n["verse"]))
        return out

    def for_chapter(self, book, chapter):
        """{verse:int -> text} for one chapter — drives the note badges."""
        prefix = f"{int(book)}:{int(chapter)}:"
        out = {}
        for k, v in self.data.items():
            if k.startswith(prefix):
                try:
                    out[int(k.split(":")[2])] = (v or {}).get("text", "")
                except Exception:
                    pass
        return out
