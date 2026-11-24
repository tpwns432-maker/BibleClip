"""웹판 Api — 데스크톱 Api 를 그대로 쓰되, 브라우저가 부를 수 있는 기능을 정해 둔다.

docs/WEB_PLAN.md. 데스크톱(pywebview)은 화면이 Python 객체의 모든 공개 메서드를 부를 수
있다. 웹은 인터넷 너머에서 부르므로 **허용 목록**(ALLOWED)에 있는 것만 연다. 목록에 없는
이름은 None 을 돌려준다 — 폰판(Bridge.kt)과 같은 약속이라 화면 코드가 그대로 돈다.

데스크톱 전용(클립보드 감시 · 장바구니 · 자막 창 · 업데이트 · 폴더 열기 · 성경 파일 추가)은
목록에 없다. 복사는 서버가 글을 만들어 돌려주고, 클립보드에 넣는 일은 브라우저가 한다
(server/static/bridge.js).
"""
import threading

from bibleclip.webui.api import Api

#: 브라우저가 부를 수 있는 기능.
ALLOWED = frozenset({
    # 시작 · 언어 · 글꼴
    'get_initial', 'get_locale', 'list_fonts', 'get_font',
    # 성경 본문 · 참조 · 검색 · 원어
    'get_books', 'get_chapters', 'get_chapter', 'get_interlinear', 'resolve_reference',
    'search', 'search_strong', 'lookup_strong', 'hover_summary', 'open_dict_window',
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
})


class WebApi(Api):
    """웹 서버가 쓰는 Api. 요청은 여러 스레드에서 오지만 Library 는 한 사람이 쓰는
    데스크톱용이라, 기능 하나가 끝날 때까지 다음 요청을 기다리게 한다(사용자 둘이면 충분)."""

    def __init__(self, library):
        super().__init__(library)
        self._lock = threading.RLock()

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
        return d

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
