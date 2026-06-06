"""Library: the UI-agnostic core of BibleClip.

Owns every piece of non-UI state and logic — loaded bible databases, the
original-language data (Strong's bible + lexicons), user settings, the
reference→formatted-output pipeline, search, and clipboard monitoring.

Both the CustomTkinter desktop app (`bibleclip.ui`) and the future web UI
consume this same object; nothing here imports tkinter or touches a window,
so a `Library()` can be constructed and exercised headlessly.
"""
import os
import re
import json

from bibleclip.config import (
    BASE_DIR, SETTINGS_FILE, LEGACY_SETTINGS_FILE, BIBLE_DIR,
    resolve_data_dir,
)
from bibleclip.core.engine import Engine
from bibleclip.core.formatter import Formatter
from bibleclip.userconfig import load_user_config
from bibleclip.core.clipboard_monitor import ClipboardMonitor
from bibleclip.data.bible_db import BibleDB
from bibleclip.data.original_lang import (
    resolve_original_lang_dir, BethlehemDB, Lexicon, parse_korean_strongs,
    parse_english_strongs, parse_wonjun_verse, strip_korean_strongs,
)


class Library:
    DEFAULT_SETTINGS = {
        'book_name': 'short_ko',         # short_ko, long_ko, short_en, long_en
        'chapter_verse_format': 'colon',  # colon, korean
        'bracket_style': 'none',          # none, [], ()
        'ref_position': 'before',         # before, after
        'range_symbol': '-',              # -, ~
        'ref_body_separator': ' ',        # ' ' (space), ' - ' (hyphen), ': ' (colon)
        'show_version_header': True,
        'hide_reference': False,
        'output_mode': 'inline',          # inline, newline
        'newline_show_cv': False,         # show chapter:verse on each line
        'output_order': [],               # ordered list of version names
        'viewer_versions': [],            # checked versions in viewer (ordered subset)
        'viewer_version_order': [],       # full viewer ordering (checked + unchecked)
        'viewer_font_size': 11,
        'auto_update_check': True,
        'skip_update_version': '',
        'seen_version': None,            # last version whose patch-note modal was acknowledged
        'dismissed_patches': [],         # versions with "다시 보지 않기" checked
        'lex_lang': 'ko',                 # default dictionary language (ko/en)
        'poll_interval': 0.5,             # clipboard polling interval (seconds)
        'search_click_navigates': False,  # search hit click also jumps the viewer
        'dark_mode': False,
        'geometry': '1100x780',
        'last_book_num': None,            # remember last viewed book/chapter
        'last_chapter': None,
        'viewer_hsash': [],               # horizontal 3-panel sash x positions
        'viewer_vsash': None,             # vertical (panels/log) sash y position
        'lex_popup_size': '440x480',      # size for new independent dict windows
        'web_geometry': None,             # {w,h,x,y} for the web UI window (web-only;
                                          # kept separate from tk 'geometry')
        'web_cards_layout': None,         # web-only: serialized card layout for the
                                          # modular multi-card viewer (list of card
                                          # descriptors; None until the web UI saves one)
    }

    def __init__(self):
        self.dbs = {}
        self.bethlehem_strongs = None  # 개역한글S — KRV-based, drives middle panel
        self.bethlehem_wonjun = None   # 원전분해 — kept for potential future use
        self.lexicon_ko = None
        self.lexicon_en = None
        self.settings = dict(self.DEFAULT_SETTINGS)
        self._monitor = None

        # Per-install business config (premium flag etc.). Fail-soft; default
        # permissive (full features) until a licensing backend exists.
        self.user_config = load_user_config()
        self.is_premium = bool(self.user_config.get('is_premium', True))

        # 묵상 노트 store (userdata/user_notes.json). Fail-soft.
        from bibleclip.notes import Notes
        self.notes = Notes()

        self.load_databases()
        self.load_bethlehem()
        self.load_settings()

    def reload_user_config(self):
        """Re-read userdata/config.json (e.g. after a backend writes it) and
        refresh the premium flag. Returns the new is_premium value."""
        self.user_config = load_user_config()
        self.is_premium = bool(self.user_config.get('is_premium', True))
        return self.is_premium

    # ---- Database loading ----

    def load_databases(self):
        db_dir = resolve_data_dir(BIBLE_DIR)
        if not os.path.isdir(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            return
        for fname in sorted(os.listdir(db_dir)):
            if fname.lower().endswith(('.sqlite3', '.sqlite', '.db')):
                path = os.path.join(db_dir, fname)
                try:
                    db = BibleDB(path)
                    self.dbs[db.name] = db
                except Exception as e:
                    print(f"Error loading {fname}: {e}")

    def load_bethlehem(self):
        """Load KRV-with-Strong's + lexicons from the original_lang folder."""
        bdir = resolve_original_lang_dir(BASE_DIR)
        if not os.path.isdir(bdir):
            return
        strongs_path = os.path.join(bdir, '개역한글S.sdb')
        if os.path.exists(strongs_path):
            try:
                self.bethlehem_strongs = BethlehemDB(strongs_path)
            except Exception as e:
                print(f"개역한글S load error: {e}")
        wonjun_path = os.path.join(bdir, '원전분해.sdb')
        if os.path.exists(wonjun_path):
            try:
                self.bethlehem_wonjun = BethlehemDB(wonjun_path)
            except Exception as e:
                print(f"원전분해 load error: {e}")
        for fname, attr in (('HebGrkKo.dct', 'lexicon_ko'),
                            ('HebGrkEn.dct', 'lexicon_en')):
            p = os.path.join(bdir, fname)
            if os.path.exists(p):
                try:
                    setattr(self, attr, Lexicon(p))
                except Exception as e:
                    print(f"{fname} load error: {e}")

    def bethlehem_ready(self):
        return bool(self.bethlehem_strongs and (self.lexicon_ko or self.lexicon_en))

    def refresh_databases(self):
        """Rescan the bible_versions folder for new DB files.

        Returns the list of newly loaded version names (so a UI can refresh its
        own version lists).
        """
        db_dir = resolve_data_dir(BIBLE_DIR)
        if not os.path.isdir(db_dir):
            return []
        existing = set(self.dbs.keys())
        added = []
        for fname in sorted(os.listdir(db_dir)):
            if fname.lower().endswith(('.sqlite3', '.sqlite', '.db')):
                name = os.path.splitext(fname)[0]
                if name not in existing:
                    path = os.path.join(db_dir, fname)
                    try:
                        db = BibleDB(path)
                        self.dbs[db.name] = db
                        added.append(db.name)
                    except Exception:
                        pass
        return added

    # ---- Settings ----

    def load_settings(self):
        """Load + validate settings from disk. UI concerns (window geometry)
        are left to the caller, which reads ``self.settings['geometry']``."""
        path = os.path.join(BASE_DIR, SETTINGS_FILE)
        # One-time migration: if the new file doesn't exist yet but the legacy
        # autobible_settings.json does, read from it. The next save_settings
        # writes the new file; the legacy file is left untouched (rollback-safe).
        if not os.path.exists(path):
            legacy = os.path.join(BASE_DIR, LEGACY_SETTINGS_FILE)
            if os.path.exists(legacy):
                path = legacy
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    saved = json.load(f)
                for k, v in saved.items():
                    if k in self.settings:
                        self.settings[k] = v
            except Exception:
                pass

        # Validate output_order. When empty (fresh install), default to a
        # Korean version so clipboard monitoring produces output immediately
        # instead of silently doing nothing.
        valid_order = [n for n in self.settings['output_order'] if n in self.dbs]
        if not valid_order and self.dbs:
            versions = list(self.dbs.keys())
            korean_pref = [v for v in ('KRV', 'NRKV', 'KNRSV') if v in versions]
            valid_order = [korean_pref[0] if korean_pref else versions[0]]
        self.settings['output_order'] = valid_order

        # Validate viewer_versions; default to KRV (or next-best Korean) when empty.
        valid_viewer = [n for n in self.settings.get('viewer_versions', []) if n in self.dbs]
        # Migration from v1.0.0: previous default was alphabetical ['KNRSV'].
        # If the saved choice is exactly that default and KRV is available, switch.
        if valid_viewer == ['KNRSV'] and 'KRV' in self.dbs:
            valid_viewer = ['KRV']
        if not valid_viewer and self.dbs:
            versions = list(self.dbs.keys())
            korean_pref = [v for v in ('KRV', 'NRKV', 'KNRSV') if v in versions]
            valid_viewer = [korean_pref[0] if korean_pref else versions[0]]
        self.settings['viewer_versions'] = valid_viewer

        # Validate viewer_version_order: must contain all loaded DBs in some order.
        saved_order = [n for n in self.settings.get('viewer_version_order', []) if n in self.dbs]
        for n in self.dbs:
            if n not in saved_order:
                saved_order.append(n)
        if not saved_order:
            saved_order = list(self.dbs.keys())
        self.settings['viewer_version_order'] = saved_order

        # Normalize the legacy 4-value book_name (long_ko/short_ko/long_en/
        # short_en) down to the 2-value form the v1.0.6 formatter actually uses
        # (each version renders its own native book name → only length matters).
        bn = str(self.settings.get('book_name', 'short_ko'))
        self.settings['book_name'] = 'long_ko' if bn.startswith('long') else 'short_ko'

        # Clamp font size
        try:
            self.settings['viewer_font_size'] = int(self.settings.get('viewer_font_size', 11))
        except (TypeError, ValueError):
            self.settings['viewer_font_size'] = 11
        self.settings['viewer_font_size'] = max(8, min(30, self.settings['viewer_font_size']))

    def save_settings(self):
        """Persist settings to disk. The caller is responsible for stamping any
        UI-only fields (e.g. ``settings['geometry']``) before calling."""
        path = os.path.join(BASE_DIR, SETTINGS_FILE)
        try:
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---- Read API (UI-agnostic) ----

    def versions(self):
        """[{'name', 'display'}] for every loaded version, in load order."""
        return [{'name': name, 'display': db.display_name}
                for name, db in self.dbs.items()]

    def books(self, version):
        """[{'num', 'short', 'long'}] for one version (canonical book order)."""
        db = self.dbs.get(version)
        if not db:
            return []
        return [{'num': bn, 'short': short, 'long': long_}
                for bn, short, long_ in db.book_list]

    def primary_version(self):
        """Best default version: first checked viewer version, else first DB."""
        for n in self.settings.get('viewer_versions', []):
            if n in self.dbs:
                return n
        return next(iter(self.dbs), None)

    def book_aliases(self):
        """``{normalized_name: book_num}`` gathered from EVERY loaded version's own
        book list (short + long names). Lets the reference parser recognize a
        version's OWN abbreviations (e.g. ESV '1Ths', which isn't in the static
        English map) — and, as more language modules drop into bible_versions/,
        their book names too, with zero hardcoding. Built from whatever .SQLite3
        files are present and cached; auto-rebuilt when the loaded set changes."""
        names = frozenset(self.dbs)
        if getattr(self, '_alias_key', None) != names:
            amap = {}
            for db in self.dbs.values():
                for bn, short, long_ in getattr(db, 'book_list', []):
                    for nm in (short, long_):
                        k = Engine._norm_book(nm)
                        if k and k != '?' and k not in amap:
                            amap[k] = bn
            self._merge_alias_overrides(amap)
            self._book_aliases = amap
            self._alias_key = names
        return self._book_aliases

    def _merge_alias_overrides(self, amap):
        """Merge user fixes from ``bible_versions/aliases_override.json`` on top of
        the auto-built map (manual entries WIN). For odd DBs whose book names are
        wrong/blank, a human can map a name → a book number OR a known abbrev:

            { "1 Ths": "1thess",  "ルツ記": "ruth",  "創世記": 10 }

        Keys starting with '_' are treated as comments. Picked up on (re)build —
        i.e. after a restart or a DB rescan. Fail-soft: any error → no overrides."""
        overrides = self.load_alias_overrides()
        if not overrides:
            return
        from bibleclip.constants import ENGLISH_BOOK_MAP
        for raw, val in overrides.items():
            if not isinstance(raw, str) or raw.startswith('_'):
                continue
            key = Engine._norm_book(raw)
            if not key:
                continue
            # value: a book number, or a known name/abbrev to resolve to one.
            bn = None
            if isinstance(val, bool):
                bn = None
            elif isinstance(val, int):
                bn = val
            elif isinstance(val, str):
                v = val.strip()
                if v.isdigit():
                    bn = int(v)
                else:
                    vk = Engine._norm_book(v)
                    bn = amap.get(vk) or ENGLISH_BOOK_MAP.get(vk)
            if bn is not None:
                amap[key] = bn   # manual override wins

    def parse_reference(self, text):
        return Engine.parse_reference(text, self.book_aliases())

    # ---- User alias overrides (앱 내 약칭 관리 UI 백엔드) ----
    # The UI reads/writes the SAME bible_versions/aliases_override.json the
    # auto-built alias map merges (manual entries win). After any write we drop
    # the cache key so book_aliases() rebuilds with the new entry on next parse.

    # Valid alias: digits, if present, only as a LEADING run (1요, 1Jn) — a digit
    # in the middle/end is rejected (요1·벧1 would clash with chapter numbers in
    # "요1 5:4"). At least one letter (한글/라틴) is required.
    _ALIAS_RE = re.compile(r'^\d*\s*[가-힣A-Za-z][^\d]*$')

    def _alias_overrides_path(self):
        return os.path.join(resolve_data_dir(BIBLE_DIR), 'aliases_override.json')

    def load_alias_overrides(self):
        """The raw override dict from disk (fail-soft {})."""
        try:
            with open(self._alias_overrides_path(), 'r', encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _write_alias_overrides(self, data):
        try:
            path = self._alias_overrides_path()
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def _resolve_override_value(self, val):
        """An override value (book number, or a name/abbrev to resolve) → book_num
        or None."""
        from bibleclip.constants import ENGLISH_BOOK_MAP
        if isinstance(val, bool):
            return None
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            v = val.strip()
            if v.isdigit():
                return int(v)
            vk = Engine._norm_book(v)
            return self.book_aliases().get(vk) or ENGLISH_BOOK_MAP.get(vk)
        return None

    def list_alias_overrides(self):
        """User-defined aliases for the management UI:
        ``[{alias, book_num, book_name}]`` (comment keys '_…' skipped)."""
        out = []
        for k, v in self.load_alias_overrides().items():
            if not isinstance(k, str) or k.startswith('_'):
                continue
            bn = self._resolve_override_value(v)
            name = self._display_book_name(bn) if bn else None
            out.append({'alias': k, 'book_num': bn, 'book_name': name or '?'})
        return out

    def add_alias_override(self, alias, book_num):
        """Add/replace one alias → book mapping. Validates the number rule and the
        target book. Returns {ok} or {ok:False, error_code}."""
        alias = (alias or '').strip()
        if not alias or len(alias) > 20 or not self._ALIAS_RE.match(alias):
            return {'ok': False, 'error_code': 'alias.errFormat'}
        try:
            bn = int(book_num)
        except (TypeError, ValueError):
            return {'ok': False, 'error_code': 'alias.errBook'}
        if Engine._canon(bn) is None:
            return {'ok': False, 'error_code': 'alias.errBook'}
        data = self.load_alias_overrides()
        data[alias] = bn
        if not self._write_alias_overrides(data):
            return {'ok': False, 'error_code': 'alias.errWrite'}
        self._alias_key = None   # force book_aliases() rebuild
        return {'ok': True}

    def remove_alias_override(self, alias):
        """Delete one alias (exact, then normalized-match fallback). {ok}."""
        alias = (alias or '').strip()
        data = self.load_alias_overrides()
        removed = False
        if alias in data:
            del data[alias]
            removed = True
        else:
            nk = Engine._norm_book(alias)
            for k in list(data):
                if isinstance(k, str) and not k.startswith('_') and Engine._norm_book(k) == nk:
                    del data[k]
                    removed = True
        if removed:
            if not self._write_alias_overrides(data):
                return {'ok': False, 'error_code': 'alias.errWrite'}
            self._alias_key = None
        return {'ok': removed}

    def get_chapters(self, version, book_num):
        db = self.dbs.get(version)
        return db.get_chapters(book_num) if db else []

    def get_chapter(self, version, book_num, chapter):
        """Return [(verse, text), ...] for one chapter of one version."""
        db = self.dbs.get(version)
        return db.get_verses(book_num, chapter) if db else []

    def search(self, version, keyword):
        db = self.dbs.get(version)
        return db.search(keyword) if db else []

    def lookup_strong(self, code, lang='ko'):
        """Raw lexicon entry (pseudo-HTML markup) for a Strong's code, or None.

        Rendering the markup is a UI concern (tk: original_lang.render_dict_html;
        web: a markup→HTML converter)."""
        lex = self.lexicon_en if lang == 'en' else self.lexicon_ko
        return lex.lookup(code) if lex else None

    def search_strong(self, code):
        """Reverse Strong's lookup over the Strong-tagged KRV (개역한글S): every
        verse whose original text carries `code` ('H3068'/'G26'). Returns
        [{book_num, chapter, verse, text}] with clean (tag-stripped) Korean text,
        or [] when the tagged bible isn't loaded. Copyright-clean (KRV + PD
        Strong's numbering only) — the basis of the original-language search."""
        if not self.bethlehem_strongs or not code:
            return []
        return [{'book_num': ob, 'chapter': ch, 'verse': v,
                 'text': strip_korean_strongs(bt)}
                for ob, ch, v, bt in self.bethlehem_strongs.search_by_strong(code)]

    def interlinear(self, book_num, chapter, version=None):
        """[(verse, [(word, code), ...]), ...] for one chapter.

        Default source is the Strong's-tagged KRV (개역한글S). When `version` names
        a loaded bible that carries inline Strong's numbers (KJV+ → strong_numbers
        flag), the breakdown is built from THAT version's own English words instead
        — identical shape, so the 원전 분해 card and dict routing stay version-
        agnostic. The H/G prefix for KJV+ comes from the testament (parse_english_
        strongs), matching the codes in HebGrkEn/Ko.dct."""
        db = self.dbs.get(version) if version else None
        if db is not None and getattr(db, 'has_strongs', False):
            return [(verse, parse_english_strongs(raw, book_num))
                    for verse, raw in db.get_chapter_raw(book_num, chapter)]
        if not self.bethlehem_strongs:
            return []
        return [(verse, parse_korean_strongs(btext))
                for verse, btext in self.bethlehem_strongs.get_chapter_verses(book_num, chapter)]

    def morphology(self, code, book_num, chapter, verse):
        """Morphological analysis entries for one Strong's code in one verse,
        from 원전분해.sdb: [{'lemma','translit','pos','gloss'}, ...] (possibly
        empty when the data isn't loaded or the word isn't present)."""
        if not (self.bethlehem_wonjun and verse and book_num):
            return []
        try:
            rows = self.bethlehem_wonjun.get_chapter_verses(book_num, chapter)
        except Exception:
            return []
        btext = next((t for vn, t in rows if vn == verse), None)
        if not btext:
            return []
        return [{'lemma': w['lemma'], 'translit': w['translit'],
                 'pos': w['pos'], 'gloss': w['gloss']}
                for w in parse_wonjun_verse(btext) if w['code'] == code]

    # ---- Reference → output pipeline ----

    def build_output(self, text):
        """Turn clipboard text into a structured result, or None.

        Returns one of:
          {'kind': 'keyword', 'keyword': str}
          {'kind': 'reference', 'book_num', 'chapter', 'verses', 'short_name',
           'text' (multi-version formatted string), 'n_parts'}
          None  — no reference matched, or matched but no loaded version had it.
        """
        text = (text or '').strip()
        if not text:
            return None

        if text.startswith('#'):
            keyword = text[1:].strip()
            if keyword:
                return {'kind': 'keyword', 'keyword': keyword}
            return None

        refs = Engine.parse_reference(text, self.book_aliases())
        if not refs:
            return None
        book_num, short_name, long_name, chapter, verses = refs[0]

        text_out, n_parts = self.format_reference(book_num, chapter, verses)
        if not text_out:
            return None
        # 토스트/활동로그 라벨은 주 출력 역본의 *자기* 책이름으로(본문과 일치). 영어
        # 역본이면 'Ruth'처럼 나오고, 파서가 돌려준 한국어 정식맵 값은 폴백으로만 쓴다.
        display_name = self._display_book_name(book_num) or short_name
        return {
            'kind': 'reference',
            'book_num': book_num,
            'chapter': chapter,
            'verses': verses,
            'short_name': display_name,
            'text': text_out,
            'n_parts': n_parts,
        }

    def _display_book_name(self, book_num, order=None):
        """Book name for toast/log labels — taken from the PRIMARY version of
        ``order`` (defaults to the configured ``output_order``) so it matches the
        copied text's language (ESV → 'Ruth', not the parser's canonical Korean).
        Honors the 정식/약칭 (long/short) setting. A caller that copied with an
        explicit version set (the viewer's manual copy) passes that order so the
        label's version matches the text it produced. None when no version
        supplies a usable name."""
        if order is None:
            order = self.settings.get('output_order') or []
        primary = order[0] if order else self.primary_version()
        db = self.dbs.get(primary)
        if db and book_num in db.books:
            short, long_ = db.books[book_num]
            name = long_ if str(self.settings.get('book_name', 'short')).startswith('long') else short
            if name and name != '?':
                return name
        return None

    def format_reference(self, book_num, chapter, verses, order=None):
        """Format one reference across a list of versions.

        ``order`` defaults to the configured ``output_order`` (clipboard
        output); callers may pass an explicit list (e.g. the viewer's versions
        for manual copy). ``verses`` may be a list or empty/None for the whole
        chapter. Returns ``(text, n_parts)`` — ``('', 0)`` when nothing matched."""
        if order is None:
            order = self.settings.get('output_order') or []
        if not order:
            return '', 0
        fmt = Formatter(self.settings, self.dbs)
        parts = []
        for ver_name in order:
            db = self.dbs.get(ver_name)
            if db is None or book_num not in db.books:
                continue
            if verses:
                verse_data = [(v, db.get_verse_text(book_num, chapter, v)) for v in verses]
            else:
                verse_data = db.get_verses(book_num, chapter)
            verse_data = [(v, t) for v, t in verse_data if t]
            if not verse_data:
                continue
            actual_verses = [v for v, _ in verse_data]
            result = fmt.format_version_output(db, book_num, chapter, actual_verses, verse_data)
            if result:
                parts.append(result)
        if not parts:
            return '', 0
        return '\n\n'.join(parts), len(parts)

    # ---- Clipboard monitoring ----

    def start_monitoring(self, read_fn, write_fn, on_reference, on_keyword):
        self.stop_monitoring()
        interval = (self.settings.get('poll_interval')
                    or ClipboardMonitor.POLL_INTERVAL)
        self._monitor = ClipboardMonitor(read_fn, write_fn, self.build_output,
                                         on_reference, on_keyword,
                                         poll_interval=interval)
        self._monitor.start()

    def stop_monitoring(self):
        if self._monitor is not None:
            self._monitor.stop()
            self._monitor = None

    def set_poll_interval(self, seconds):
        """Re-tune a running monitor's polling interval (no restart needed)."""
        if self._monitor is not None:
            self._monitor.poll_interval = seconds

    def notify_clipboard_written(self, text):
        """Tell an active monitor that `text` was just placed on the clipboard
        by other code, so it isn't re-detected as fresh input."""
        if self._monitor is not None:
            self._monitor.last = text
