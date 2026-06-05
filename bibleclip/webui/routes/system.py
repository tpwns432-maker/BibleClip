"""System / app-plumbing bridge routes: bootstrap payload, persisted UI prefs,
the ⚙ app settings, GitHub update check + 패치노트 modal + in-place self-update,
and the 출력 설정 (output format) surface.

Mixed into webui.api.Api. Uses ``self.lib``, ``self._push``, ``self._update``,
and ``self._window``. Clipboard monitoring stays on the base Api.
"""
import os
import sys
import json
import threading
import tempfile
import subprocess
import webbrowser

from bibleclip.config import (
    __version__, RELEASES_PAGE_URL, IS_WINDOWS, get_base_dir,
    GITHUB_OWNER, GITHUB_REPO,
)
from bibleclip.update import fetch_latest_release, parse_version
from bibleclip.core.installer import (
    download_file, stage_payload, write_windows_bat, write_mac_sh,
)

REPO_HOME_URL = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"


class SystemRoutes:
    # ---- Bootstrap ----

    def get_initial(self):
        """Everything the UI needs on load, in one round-trip."""
        primary = self.lib.primary_version()
        s = self.lib.settings
        last_book = s.get('last_book_num')
        last_chapter = s.get('last_chapter')
        # Fall back to the first available book/chapter of the primary version.
        books = self.lib.books(primary) if primary else []
        if not (last_book and any(b['num'] == last_book for b in books)):
            last_book = books[0]['num'] if books else None
            last_chapter = None
        if last_book is not None and not last_chapter:
            chs = self.lib.get_chapters(primary, last_book)
            last_chapter = chs[0] if chs else 1
        return {
            'versions': self.lib.versions(),
            'primary': primary,
            'viewer': list(self.lib.settings.get('viewer_versions', [])),
            'books': books,
            'last': {'version': primary, 'book': last_book, 'chapter': last_chapter},
            'dark_mode': bool(s.get('dark_mode')),
            'font_size': int(s.get('viewer_font_size', 11)),
            'auto_update_check': bool(s.get('auto_update_check', True)),
            'lex_lang': 'en' if s.get('lex_lang') == 'en' else 'ko',
            # Which original-language dictionaries are installed (user-supplied
            # modules in original_lang/). When both are false the UI guides the
            # user to add a module instead of showing an empty lexicon panel.
            'lex': {'ko': self.lib.lexicon_ko is not None,
                    'en': self.lib.lexicon_en is not None},
            # Business guard (Phase 1): premium unlocks multi-card, the chapter
            # shortcut, and notes/badge. Default True until a licensing backend
            # writes userdata/config.json with {"is_premium": false}.
            'is_premium': bool(getattr(self.lib, 'is_premium', True)),
            'search_click_navigates': bool(s.get('search_click_navigates', False)),
            # Persisted modular-card layout (None until the web UI saves one; the
            # front-end builds a sensible default when this is null).
            'web_cards_layout': s.get('web_cards_layout'),
            'version': __version__,
        }

    def save_cards_layout(self, layout):
        """Persist the web viewer's card layout (a JSON-serializable list of card
        descriptors). Thin convenience wrapper over set_app_setting so the front-
        end can call ``api.save_cards_layout(layout)`` directly. Returns {ok}."""
        return self.set_app_setting('web_cards_layout', layout)

    # ---- UI preferences (persisted; shared with the desktop app) ----

    def set_dark_mode(self, on):
        self.lib.settings['dark_mode'] = bool(on)
        self.lib.save_settings()
        return {'ok': True}

    def set_font_size(self, size):
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = 11
        size = max(8, min(30, size))
        self.lib.settings['viewer_font_size'] = size
        self.lib.save_settings()
        return size

    def refresh_databases(self):
        """Rescan the bible_versions folder for newly added DB files (no restart
        needed). Returns {added:[names], versions:[...]} for the UI to refresh."""
        added = self.lib.refresh_databases()
        return {'added': added, 'versions': self.lib.versions()}

    # ---- App-wide settings (the gear ⚙ window — distinct from 출력 설정) ----

    # Whitelisted app settings. Enums carry allowed values; None = boolean;
    # 'poll_interval' is a float clamped on write.
    _APP_KEYS = {
        'auto_update_check': None,
        'search_click_navigates': None,
        'lex_lang': {'ko', 'en'},
        'poll_interval': 'float',
        # The web card layout is an opaque, front-end-owned blob (a list of card
        # descriptors). 'any' = store whatever JSON-serializable value JS sends,
        # no server-side validation. None clears it back to the default.
        'web_cards_layout': 'any',
    }

    def get_app_settings(self):
        """Everything the ⚙ settings window shows."""
        s = self.lib.settings
        return {
            'auto_update_check': bool(s.get('auto_update_check', True)),
            'search_click_navigates': bool(s.get('search_click_navigates', False)),
            'lex_lang': 'en' if s.get('lex_lang') == 'en' else 'ko',
            'poll_interval': float(s.get('poll_interval', 0.5) or 0.5),
            'web_cards_layout': s.get('web_cards_layout'),
            'version': __version__,
            'repo_url': REPO_HOME_URL,
        }

    def set_app_setting(self, key, value):
        """Update one whitelisted app setting and persist. A poll-interval change
        is also applied to a running monitor live. Returns {ok, value}."""
        if key not in self._APP_KEYS:
            return {'ok': False, 'error': f'unknown key: {key}'}
        spec = self._APP_KEYS[key]
        if spec == 'float':
            try:
                value = float(value)
            except (TypeError, ValueError):
                value = 0.5
            value = round(max(0.1, min(2.0, value)), 2)
        elif spec == 'any':
            # Stored verbatim — must be JSON-serializable so it survives a
            # save/load round-trip; reject anything that isn't.
            try:
                json.dumps(value)
            except (TypeError, ValueError):
                return {'ok': False, 'error': f'value for {key} is not JSON-serializable'}
        elif spec is None:
            value = bool(value)
        elif value not in spec:
            return {'ok': False, 'error': f'invalid value for {key}: {value!r}'}
        self.lib.settings[key] = value
        self.lib.save_settings()
        if key == 'poll_interval':
            self.lib.set_poll_interval(value)
        return {'ok': True, 'value': value}

    def reset_settings(self):
        """Restore every setting to its default (the "설정 초기화" button). The
        front-end reloads afterwards to re-read the fresh state."""
        self.lib.settings = dict(self.lib.DEFAULT_SETTINGS)
        self.lib.save_settings()
        return {'ok': True}

    def open_data_folder(self):
        """Open the folder that holds bible_versions/original_lang in the OS file
        manager (so the user can drop in new .db files)."""
        path = get_base_dir()
        try:
            if IS_WINDOWS:
                os.startfile(path)  # noqa: S606 - user-initiated
            elif sys.platform == 'darwin':
                subprocess.Popen(['open', path])
            else:
                subprocess.Popen(['xdg-open', path])
            return {'ok': True}
        except Exception:
            return {'ok': False}

    def open_github(self):
        try:
            webbrowser.open(REPO_HOME_URL)
            return {'ok': True}
        except Exception:
            return {'ok': False}

    # ---- Update check (GitHub releases) ----

    def check_update(self):
        """Check GitHub for a newer release. Returns {ok, has_update, current,
        latest, notes, url, skipped} or {ok:False, error}. (Download/install of
        a frozen build is deferred to packaging — see HANDOFF.)"""
        info, error = fetch_latest_release()
        if error or not info:
            return {'ok': False, 'error': error or '응답 없음'}
        self._update = info  # remembered for install_update()
        has = parse_version(info['version']) > parse_version(__version__)
        # Soft forced-update (Phase 4): when below the manifest's recommend_version
        # the UI shows a non-dismissible modal (but the app still runs — the hard
        # block is the kill switch's min_version). Fail-open.
        mandatory = False
        if has:
            try:
                from bibleclip.killswitch import recommended_version
                rec = recommended_version()
                if rec and parse_version(__version__) < parse_version(rec):
                    mandatory = True
            except Exception:
                mandatory = False
        return {
            'ok': True, 'has_update': has, 'mandatory': mandatory,
            'current': __version__, 'latest': info['version'],
            'notes': info.get('body') or '', 'url': info.get('download_url') or '',
            'skipped': self.lib.settings.get('skip_update_version') == info['version'],
        }

    # ---- 패치노트 (first-run-after-update modal, Phase 4) ----

    def _version_changes(self):
        import json
        from bibleclip.config import BASE_DIR, get_resource_dir
        for root in (BASE_DIR, get_resource_dir()):
            try:
                with open(os.path.join(root, 'version_changes.json'), 'r',
                          encoding='utf-8') as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    return d
            except Exception:
                continue
        return {}

    def get_patch_notes(self):
        """The current version's patch notes + whether to show the modal: shown
        once after an update unless this version was dismissed with '다시 보지
        않기'. {version, notes:[...], show}."""
        notes = self._version_changes().get(__version__, [])
        seen = self.lib.settings.get('seen_version')
        dismissed = self.lib.settings.get('dismissed_patches') or []
        show = bool(notes) and __version__ != seen and __version__ not in dismissed
        return {'version': __version__, 'notes': notes, 'show': show}

    def dismiss_patch(self, forever=False):
        """Acknowledge the patch modal. `forever` also adds this version to the
        '다시 보지 않기' list so it never reappears."""
        self.lib.settings['seen_version'] = __version__
        if forever:
            lst = list(self.lib.settings.get('dismissed_patches') or [])
            if __version__ not in lst:
                lst.append(__version__)
            self.lib.settings['dismissed_patches'] = lst
        self.lib.save_settings()
        return {'ok': True}

    def open_releases_page(self):
        try:
            webbrowser.open(RELEASES_PAGE_URL)
            return {'ok': True}
        except Exception:
            return {'ok': False}

    def skip_update(self, version):
        self.lib.settings['skip_update_version'] = version
        self.lib.save_settings()
        return {'ok': True}

    def install_update(self):
        """Download the latest release and apply it in place (the desktop app's
        self-update). Runs in a worker thread; progress/result are pushed to JS
        as window.bibleclip.onUpdateProgress / onUpdateReady / onUpdateError.
        Only works in a frozen build on Windows/macOS."""
        if not getattr(sys, 'frozen', False):
            return {'ok': False, 'error': '소스 실행 모드에서는 자동 설치가 안 됩니다. 릴리스 페이지를 이용하세요.'}
        info = self._update
        if not info or not info.get('download_url'):
            return {'ok': False, 'error': '업데이트 정보가 없습니다. 먼저 업데이트 확인을 해주세요.'}
        if not (IS_WINDOWS or sys.platform == 'darwin'):
            return {'ok': False, 'error': '이 OS에서는 자동 설치가 지원되지 않습니다.'}
        threading.Thread(target=self._run_install, args=(info,), daemon=True).start()
        return {'ok': True, 'started': True}

    def _run_install(self, info):
        try:
            tmp = tempfile.mkdtemp(prefix='bibleclip_update_')
            zip_path = os.path.join(tmp, info.get('asset_name') or 'update.zip')

            def prog(done, total):
                pct = round(done * 100.0 / total, 1) if total else 0
                self._push('onUpdateProgress', pct, done // 1024,
                           (total // 1024) if total else 0)

            download_file(info['download_url'], zip_path, prog)
            self._push('onUpdateProgress', 100, 0, 0)

            is_mac = sys.platform == 'darwin'
            payload = 'BibleClipWeb.app' if is_mac else 'BibleClipWeb.exe'
            src = stage_payload(zip_path, os.path.join(tmp, 'extract'), payload)

            if is_mac:
                sh = os.path.join(tmp, 'updater.sh')
                write_mac_sh(sh, src, self._running_app_path(), os.getpid())
                subprocess.Popen(['/bin/bash', sh], start_new_session=True, close_fds=True)
            else:
                bat = os.path.join(tmp, 'updater.bat')
                write_windows_bat(bat, src, get_base_dir(), 'BibleClipWeb.exe')
                flags = (subprocess.CREATE_NEW_PROCESS_GROUP
                         | getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000))
                subprocess.Popen(['cmd', '/c', bat], creationflags=flags, close_fds=True)

            self._push('onUpdateReady')
            self._quit_for_update()
        except Exception as e:
            self._push('onUpdateError', str(e))

    def _running_app_path(self):
        """Full path of the running .app bundle (macOS), for in-place replace."""
        p = os.path.dirname(sys.executable)
        while p and not p.endswith('.app'):
            parent = os.path.dirname(p)
            if parent == p:
                return os.path.join(get_base_dir(), 'BibleClipWeb.app')
            p = parent
        return p

    def _quit_for_update(self):
        try:
            self.lib.stop_monitoring()
            self.lib.save_settings()
        except Exception:
            pass
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception:
            pass
        os._exit(0)  # ensure the process exits so the updater can overwrite files

    def note_position(self, book, chapter):
        """Remember the last viewed book/chapter (saved to disk on window close
        or on the next settings write — cheap, no immediate disk I/O)."""
        try:
            self.lib.settings['last_book_num'] = int(book)
            self.lib.settings['last_chapter'] = int(chapter)
        except (TypeError, ValueError):
            pass

    def set_viewer_versions(self, names):
        """Replace the set of versions shown in parallel in the viewer.

        The given names are filtered to loaded versions and re-sorted by the
        persistent ``viewer_version_order`` so the on-screen order stays stable
        regardless of toggle order. At least one version is always kept.
        Returns the cleaned, ordered list."""
        order = (self.lib.settings.get('viewer_version_order')
                 or list(self.lib.dbs.keys()))
        valid = {n for n in names if n in self.lib.dbs}
        ordered = [n for n in order if n in valid]
        for n in names:           # preserve any valid name missing from order
            if n in self.lib.dbs and n not in ordered:
                ordered.append(n)
        if not ordered:
            return list(self.lib.settings.get('viewer_versions', []))
        self.lib.settings['viewer_versions'] = ordered
        self.lib.save_settings()
        return ordered

    def set_viewer_order(self, names):
        """Set the explicit display order of the viewer's versions (chip drag).

        Unlike set_viewer_versions this trusts the given order verbatim (it's a
        reorder of the already-checked set) and pushes it to the front of the
        persistent viewer_version_order. Returns the cleaned list."""
        valid = [n for n in names if n in self.lib.dbs]
        if not valid:
            return list(self.lib.settings.get('viewer_versions', []))
        self.lib.settings['viewer_versions'] = valid
        rest = [n for n in (self.lib.settings.get('viewer_version_order') or [])
                if n in self.lib.dbs and n not in valid]
        self.lib.settings['viewer_version_order'] = valid + rest
        self.lib.save_settings()
        return valid

    # ---- Output settings (the "출력 설정" tab) ----

    # Format keys the settings tab may write. Enums carry their allowed values;
    # bool keys map to None (coerced to a real bool on write).
    _FORMAT_KEYS = {
        'book_name': {'long_ko', 'short_ko', 'long_en', 'short_en'},
        'chapter_verse_format': {'colon', 'korean'},
        'bracket_style': {'none', '[]', '()'},
        'ref_position': {'before', 'after'},
        'range_symbol': {'-', '~'},
        'ref_body_separator': {' - ', ': ', ' '},
        'output_mode': {'inline', 'newline'},
        'newline_show_cv': None,
        'show_version_header': None,
        'hide_reference': None,
    }

    def get_settings(self):
        """The format settings + output order the settings tab needs."""
        s = self.lib.settings
        return {
            'format': {k: s.get(k) for k in self._FORMAT_KEYS},
            'output_order': list(s.get('output_order', [])),
            'versions': self.lib.versions(),  # name + display for label lookups
        }

    def set_setting(self, key, value):
        """Update one whitelisted format setting and persist. Returns {ok}."""
        if key not in self._FORMAT_KEYS:
            return {'ok': False, 'error': f'unknown key: {key}'}
        allowed = self._FORMAT_KEYS[key]
        if allowed is None:               # boolean setting
            value = bool(value)
        elif value not in allowed:
            return {'ok': False, 'error': f'invalid value for {key}: {value!r}'}
        self.lib.settings[key] = value
        self.lib.save_settings()
        return {'ok': True}

    def set_output_order(self, names):
        """Replace the clipboard output order (versions used when a reference is
        caught/copied). Filtered to loaded versions, dedup, order preserved as
        given. Returns the cleaned list."""
        seen = set()
        cleaned = []
        for n in names:
            if n in self.lib.dbs and n not in seen:
                seen.add(n)
                cleaned.append(n)
        self.lib.settings['output_order'] = cleaned
        self.lib.save_settings()
        return cleaned

    def get_preview(self):
        """Formatted output for the fixed sample (요 1:1-3) under current
        settings — exactly what would land on the clipboard."""
        r = self.lib.build_output('요 1:1-3')
        if r and r.get('kind') == 'reference':
            return r['text']
        if not self.lib.settings.get('output_order'):
            return '(출력할 성경 버전을 추가하세요)'
        return '(데이터를 찾을 수 없습니다)'
