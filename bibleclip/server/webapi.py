"""웹판 Api — 데스크톱 Api 를 그대로 쓰되, 브라우저가 부를 수 있는 기능을 정해 둔다.

docs/WEB_PLAN.md. 데스크톱(pywebview)은 화면이 Python 객체의 모든 공개 메서드를 부를 수
있다. 웹은 인터넷 너머에서 부르므로 **허용 목록**(ALLOWED)에 있는 것만 연다. 목록에 없는
이름은 None 을 돌려준다 — 폰판(Bridge.kt)과 같은 약속이라 화면 코드가 그대로 돈다.

데스크톱 전용(클립보드 감시 · 장바구니 · 자막 창 · 업데이트 · 폴더 열기 · 성경 파일 추가)은
목록에 없다. 복사는 서버가 글을 만들어 돌려주고, 클립보드에 넣는 일은 브라우저가 한다
(server/static/bridge.js).
"""
import json
import os
import threading

from bibleclip.core.library import Library
from bibleclip.webui.api import Api

#: 브라우저가 부를 수 있는 기능.
ALLOWED = frozenset({
    # 시작 · 언어 · 글꼴
    'get_initial', 'get_locale', 'list_fonts', 'get_font',
    # 성경 본문 · 참조 · 검색 · 원어
    'get_books', 'get_chapters', 'get_chapter', 'get_interlinear', 'get_study', 'resolve_reference',
    'search', 'search_strong', 'lookup_strong', 'lookup_english', 'hover_summary', 'open_dict_window',
    # 설정
    'get_settings', 'set_setting', 'get_preview', 'set_output_order',
    'get_app_settings', 'set_app_setting', 'reset_settings',
    'save_cards_layout', 'set_dark_mode', 'set_font_size',
    'set_viewer_versions', 'set_viewer_order', 'note_position',
    'get_aliases', 'add_alias', 'remove_alias',
    # 노트 · 형광펜
    'get_chapter_notes', 'get_all_notes', 'get_note', 'set_note', 'delete_note',
    'get_chapter_highlights', 'get_verse_highlights', 'set_verse_highlights',
    'clear_verse_highlights', 'get_all_highlights',
    # 복사(글만 만든다 — 클립보드는 브라우저)
    'copy_reference', 'copy_references',
    # 휴대폰 화면의 카드 배치 · 글자 크기(PC 와 따로)
    'get_phone_prefs', 'save_phone_prefs',
})

PHONE_PREFS_FILE = 'phone_prefs.json'
PHONE_PREFS_MAX = 64 * 1024


class WebApi(Api):
    """한 사람 몫의 Api. 요청은 여러 스레드에서 오지만 Library 는 데스크톱용이라, 기능 하나가
    끝날 때까지 다음 요청을 기다리게 한다(사용자 둘이면 충분). 두 사람이 성경 엔진을 나눠 쓰므로
    잠금(lock)도 WebHub 가 하나를 나눠 준다."""

    def __init__(self, library, lock=None, user=None):
        super().__init__(library)
        self._lock = lock or threading.RLock()
        self.user = user or {}      # {'id', 'name'} — 화면의 로그아웃 단추에 쓴다

    def call(self, name, args):
        """브라우저 요청 하나. 허용 목록 밖이면 None."""
        if name not in ALLOWED:
            return None
        with self._lock:
            return getattr(self, name)(*args)

    def get_initial(self):
        d = super().get_initial()
        d['auto_update_check'] = False   # 서버는 git pull 로 바뀐다
        d['tour_done'] = True            # 첫 실행 안내는 데스크톱 버튼을 가리킨다(웹용은 나중에)
        d['cart'] = []
        d['web_user'] = dict(self.user)
        return d

    # ---- 휴대폰 화면 설정: PC 와 같은 계정이어도 카드 배치 · 글자 크기는 따로 ----
    # 같은 설정(web_cards_layout · viewer_font_size)을 쓰면 폰에서 카드 2장으로 줄인 배치가
    # PC 의 원어 · 사전 카드를 지우고, PC 글자 크기가 폰에선 너무 작다. 그래서 사람 폴더에 따로 둔다.

    def _phone_prefs_path(self):
        return os.path.join(self.lib.user_dir, PHONE_PREFS_FILE) if self.lib.user_dir else None

    def get_phone_prefs(self):
        path = self._phone_prefs_path()
        try:
            with open(path, encoding='utf-8') as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except (OSError, TypeError, ValueError):
            return {}

    def save_phone_prefs(self, patch):
        """patch: {layout?, font_size?} — 받은 칸만 바꾼다."""
        path = self._phone_prefs_path()
        if not path or not isinstance(patch, dict):
            return {'ok': False}
        d = self.get_phone_prefs()
        if 'layout' in patch:
            d['layout'] = patch['layout']
        if 'font_size' in patch:
            try:
                d['font_size'] = max(8, min(400, int(patch['font_size'])))
            except (TypeError, ValueError):
                pass
        text = json.dumps(d, ensure_ascii=False)
        if len(text) > PHONE_PREFS_MAX:
            return {'ok': False}
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            f.write(text)
        os.replace(tmp, path)
        return {'ok': True}

    def note_position(self, book, chapter):
        # 데스크톱은 창을 닫을 때 저장한다. 웹에는 '창 닫기'가 없으니 바로 저장.
        super().note_position(book, chapter)
        self.lib.save_settings()

    def open_dict_window(self, code, lang=None, book=None, chapter=None,
                         verse=None, theme='light'):
        """사전 창: 데스크톱은 새 네이티브 창을 띄운다. 웹은 그 페이지(HTML)를 돌려주고
        브라우저가 새 창으로 연다. 반환 {ok, title, html}."""
        box = {}
        self._popup_factory = lambda title, html: box.update(title=title, html=html)
        try:
            r = super().open_dict_window(code, lang, book, chapter, verse, theme)
        finally:
            self._popup_factory = None
        return {'ok': bool(r and r.get('ok') and 'html' in box), **box}


class WebHub:
    """성경 엔진(역본 · 원어)은 한 벌, 설정 · 노트 · 형광펜은 사람마다.

    <데이터 폴더>/users/<아이디>/ 에 그 사람의 bibleclip_settings.json · user_notes.json ·
    user_highlights.json 이 생긴다. 사람별 Api 는 처음 들어올 때 만든다."""

    def __init__(self, engine, data_dir):
        self.engine = engine
        self.users_dir = os.path.join(data_dir, 'users')
        self._lock = threading.RLock()
        self._apis = {}

    def api_for(self, uid, name=None):
        with self._lock:
            api = self._apis.get(uid)
            if api is None:
                folder = os.path.join(self.users_dir, uid)
                os.makedirs(folder, exist_ok=True)
                api = WebApi(Library(user_dir=folder, engine=self.engine), self._lock,
                             {'id': uid, 'name': name or uid})
                self._apis[uid] = api
            elif name:
                api.user = {'id': uid, 'name': name}
            return api

    def verse_text(self, uid, verse):
        """글에 단 구절의 본문 — 읽는 사람이 성경 화면에서 맨 앞에 둔 역본으로."""
        with self._lock:
            lib = self.api_for(uid).lib
            version = lib.primary_version()
            if not version:
                return None
            rows = lib.get_chapter(version, verse['book'], verse['chapter'])
            return {'version': lib.dbs[version].display_name,
                    'verses': [{'n': n, 'text': t} for n, t in rows
                               if verse['verse'] <= n <= verse['verse_end']]}

    def partner_highlights(self, uid, others, book, chapter, versions):
        """상대(들)의 형광펜 — [{user:{id,name}, hl:{역본:{절:[구간]}}}]. 읽기만 한다."""
        out = []
        with self._lock:
            for oid, name in others:
                if oid == uid:
                    continue
                hl = self.api_for(oid, name).lib.highlights
                data = {v: hl.for_chapter(book, chapter, v) for v in versions}
                if any(data.values()):
                    out.append({'user': {'id': oid, 'name': name}, 'hl': data})
        return out
