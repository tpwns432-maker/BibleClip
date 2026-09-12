"""자막(PPT) 화면 bridge routes — v1.2.0.

예배 현장의 영상 송출 구조를 그대로 옮긴다: 노트북에는 조작 화면, 빔프로젝터에는
자막만. 장바구니 팝아웃 창(FEAT-07)과 같은 배관을 쓴다(자체완결 HTML + js_api +
_child_windows 추적 + evaluate_js 푸시).

**줄바꿈은 여기서 하지 않는다.** 어디서 줄을 나눌지는 그리는 쪽(자막 창)이 자기
글꼴·창 폭으로 실제 렌더 폭을 재서 정해야 한다(web/js/versebreak.js). 백엔드는
"무슨 글자를 띄울지"까지만 책임진다 — 역본 텍스트와 참조 문자열.

현재 슬라이드 번호를 **백엔드가 들고 있는 이유**: 조작 창과 자막 창이 각자 상태를
가지면 둘이 어긋난다. 한 곳에만 두고 양쪽에 밀어준다(장바구니와 같은 방식).
"""
import json


class SlideRoutes:
    # ---- 창 ----

    def open_subtitle_window(self):
        """자막 창을 열거나(이미 열려 있으면) 그대로 둔다. 팩토리가 없으면
        (헤드리스 테스트) no-op. Returns {ok}."""
        if self._subtitle_window_factory is None:
            return {'ok': False, 'error': 'no factory'}
        try:
            self._subtitle_window_factory()
        except Exception as e:
            return {'ok': False, 'error': str(e)}
        self._broadcast_slide()
        return {'ok': True}

    def close_subtitle_window(self):
        win = self._subtitle_window
        if win is None:
            return {'ok': True}
        try:
            win.destroy()
        except Exception:
            pass
        self._subtitle_window = None
        return {'ok': True}

    def subtitle_window_open(self):
        return self._subtitle_window is not None

    # ---- 슬라이드 ----

    def get_slides(self):
        """자막에 띄울 수 있는 슬라이드 목록 = 장바구니 순서 그대로.
        [{book_num, chapter, verses, short_name}, ...]"""
        return self.lib.cart.all()

    def get_slide(self, index=None):
        """슬라이드 하나를 '띄울 글자'로 풀어 돌려준다.

        index 를 생략하면 현재 슬라이드. 임시 슬라이드(F9 즉석 입력)가 걸려 있으면
        그것이 우선한다 — 발표 중 준비한 순서를 벗어나 즉석으로 한 구절을 띄우는
        일이 실제로 자주 생긴다.

        Returns {ok, ref, verses:[{n, text}], version, index, total} 또는 {ok:False}.
        """
        if index is None and self._slide_adhoc is not None:
            return dict(self._slide_adhoc, ok=True, index=-1,
                        total=len(self.lib.cart.all()),
                        page=self._slide_page, pages=self._slide_pages)
        items = self.lib.cart.all()
        if not items:
            return {'ok': False, 'error': 'empty'}
        i = self._slide_index if index is None else int(index)
        i = max(0, min(i, len(items) - 1))
        payload = self._resolve_slide(items[i])
        if payload is None:
            return {'ok': False, 'error': 'no text'}
        return dict(payload, ok=True, index=i, total=len(items),
                    page=self._slide_page, pages=self._slide_pages)

    def set_slide(self, index):
        """현재 슬라이드를 지정하고 자막 창에 반영. 즉석 슬라이드는 해제된다."""
        items = self.lib.cart.all()
        if not items:
            return {'ok': False, 'error': 'empty'}
        self._slide_adhoc = None
        self._slide_index = max(0, min(int(index), len(items) - 1))
        self._reset_pages()
        self._broadcast_slide()
        return {'ok': True, 'index': self._slide_index, 'total': len(items)}

    def slide_step(self, delta):
        """◀ ▶ — 한 걸음 이동.

        긴 본문은 한 구절이 여러 '장'이므로 **장 안에서 먼저** 움직이고, 장의 끝에
        닿았을 때만 다음/이전 구절로 넘어간다. 준비한 순서를 장 단위로 훑는 것이
        발표 중의 자연스러운 흐름이다.

        즉석 슬라이드(F9)도 마찬가지로 장 이동이 먼저다. 장의 끝을 넘어설 때 비로소
        준비된 순서로 복귀한다 — 그때도 건너뛰지 않고 '현재 번호' 그대로 돌아온다.
        ⚠️ 예전에는 즉석 슬라이드에서 첫 걸음에 무조건 빠져나와, F9 로 띄운 긴 본문의
           2장 이후를 아예 볼 수 없었다.
        """
        d = int(delta)

        def _page_step():
            """현재 장 안에서 한 걸음. 옮겼으면 True, 장의 끝을 넘었으면 False."""
            nxt = self._slide_page + d
            if 0 <= nxt < self._slide_pages:
                self._slide_page = nxt
                return True
            return False

        def _reply(index):
            self._broadcast_slide()
            return {'ok': True, 'index': index, 'page': self._slide_page,
                    'total': len(self.lib.cart.all())}

        # 즉석 슬라이드: 장 이동 → (끝나면) 준비된 순서로 복귀.
        # 장바구니가 비어 있어도 장 이동은 되어야 하므로 'empty' 검사보다 먼저 둔다.
        if self._slide_adhoc is not None:
            if _page_step():
                return _reply(-1)
            self._slide_adhoc = None
            self._reset_pages()
            return _reply(self._slide_index if self.lib.cart.all() else -1)

        items = self.lib.cart.all()
        if not items:
            return {'ok': False, 'error': 'empty'}
        if not _page_step():
            self._slide_index = max(0, min(self._slide_index + d, len(items) - 1))
            # 뒤로 넘어갈 때는 앞 구절의 '마지막 장'에서 이어져야 자연스럽다.
            # 몇 장인지는 아직 모르므로(창이 그려 봐야 안다) **-1 = 마지막 장**이라는
            # 약속을 쓴다. 큰 수를 sentinel 로 쓰면 그 값이 payload 에 그대로 새어
            # 나가 "1000001 / 1" 같은 것이 보인다.
            self._slide_page = 0 if d > 0 else -1
            self._slide_pages = 1
        return _reply(self._slide_index)

    def report_slide_pages(self, pages):
        """자막 창이 '이 슬라이드는 몇 장이더라'를 알려준다.

        장수는 글꼴·창 크기에 달려 있어 백엔드가 알 수 없다. 창이 그려 보고 보고하면
        여기서 현재 장 번호를 그 범위로 맞춘다(뒤로 넘어와 마지막 장을 원하는 경우 포함).
        범위가 바뀌었을 때만 되쏘아 무한 왕복을 피한다."""
        try:
            n = max(1, int(pages))
        except (TypeError, ValueError):
            return {'ok': False}
        # -1 = '마지막 장'(뒤로 넘어온 경우). 그 외에는 범위 안으로 맞춘다.
        page = n - 1 if self._slide_page < 0 else max(0, min(self._slide_page, n - 1))
        changed = (page != self._slide_page)
        self._slide_pages, self._slide_page = n, page
        if changed:
            self._broadcast_slide()
        return {'ok': True, 'page': page, 'pages': n}

    def _reset_pages(self):
        self._slide_page, self._slide_pages = 0, 1

    # ---- 겉모습(배색 · 글꼴) ----

    def get_subtitle_style(self):
        """자막 창이 쓸 겉모습. {preset, font_family, font_file}

        자막 창은 자체완결 페이지라 메인 창이 주입해 둔 커스텀 글꼴을 모른다. 글꼴
        '이름'만으론 부족하고 실제 파일까지 알아야 @font-face 를 심을 수 있으므로,
        설정의 family 를 list_fonts 목록과 맞춰 파일명을 함께 돌려준다.
        (바이트는 무거우니 여기서 주지 않는다 — 창이 get_font 로 따로 받아간다.)
        """
        family = self.lib.settings.get('reading_font') or ''
        file = ''
        if family:
            for f in (self.list_fonts() or []):
                if f.get('family') == family:
                    file = f.get('file') or ''
                    break
        return {
            'preset': self.lib.settings.get('subtitle_preset') or 'green',
            'font_family': family,
            'font_file': file,
        }

    def _broadcast_subtitle_style(self):
        """배색·글꼴이 바뀌면 자막 창에 즉시 반영한다(슬라이드와 같은 푸시 방식)."""
        win = self._subtitle_window
        if win is None:
            return
        try:
            blob = json.dumps(self.get_subtitle_style(), ensure_ascii=False)
            win.evaluate_js(f"window.applySubtitleStyle && window.applySubtitleStyle({blob})")
        except Exception:
            self._subtitle_window = None

    def show_slide_ref(self, book, chapter, verses):
        """F9 즉석 입력 — 장바구니에 없는 구절을 지금 바로 자막에 띄운다."""
        payload = self._resolve_slide({
            'book_num': int(book), 'chapter': int(chapter),
            'verses': [int(v) for v in (verses or [])],
        })
        if payload is None:
            return {'ok': False, 'error': 'no text'}
        self._slide_adhoc = payload
        self._reset_pages()
        self._broadcast_slide()
        return {'ok': True}

    def clear_slide_adhoc(self):
        """즉석 슬라이드를 걷고 준비된 순서로 돌아간다."""
        self._slide_adhoc = None
        self._reset_pages()
        self._broadcast_slide()
        return {'ok': True}
