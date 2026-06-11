"""Headless test for the web bridge (bibleclip.webui.api.Api).

Run with:  python -X utf8 tests/test_webui_api.py

Does NOT import `webview` (the Api is deliberately backend-free) and never
calls save_settings. Exits via os._exit(0).
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import bibleclip.webui.api as apimod
from bibleclip.config import __version__
from bibleclip.core.library import Library
from bibleclip.webui.api import Api, markup_to_html


class FakeClipboard:
    """In-memory stand-in for pyperclip (no real system clipboard touched)."""
    def __init__(self):
        self.text = ''

    def paste(self):
        return self.text

    def copy(self, text):
        self.text = text


class FakeWindow:
    """Captures the JS pushed via window.evaluate_js (the Python→JS channel)."""
    def __init__(self):
        self.calls = []

    def evaluate_js(self, js):
        self.calls.append(js)


def wait_for(predicate, timeout=3.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def force_korean_primary(api):
    """Pin KRV as the primary/output/viewer version so the Korean assertions
    ('태초' …) hold regardless of the developer's personal bibleclip_settings.json
    (which may have an English version first). In-memory only — save_settings is
    never called here, so the user's saved file is untouched."""
    if 'KRV' in api.lib.dbs:
        api.lib.settings['viewer_versions'] = ['KRV']
        api.lib.settings['output_order'] = ['KRV']


def monitor_check():
    """Drive the clipboard monitor end-to-end against fakes: a reference is
    converted in place and pushed to JS as onReference; a '#keyword' as
    onKeyword. Never touches the real clipboard or imports webview."""
    fake = FakeClipboard()
    apimod.pyperclip = fake          # swap the module's clipboard backend
    win = FakeWindow()
    api = Api(Library())
    force_korean_primary(api)
    api.set_window(win)

    res = api.start_monitoring()
    assert res.get('ok'), res

    # The monitor picks up its poll interval from settings and is live-tunable.
    assert api.lib._monitor is not None
    assert api.lib._monitor.poll_interval == api.lib.settings['poll_interval']
    api.lib.set_poll_interval(0.25)
    assert api.lib._monitor.poll_interval == 0.25

    # A reference: should be converted in place and pushed as onReference.
    fake.text = '창 1:1'
    assert wait_for(lambda: any('onReference' in c for c in win.calls)), \
        "onReference was never pushed"
    assert '태초' in fake.text, f"clipboard not converted in place: {fake.text!r}"
    print(f"monitor: '창 1:1' -> onReference; clipboard now: {fake.text[:24]}…")

    # A '#keyword' query: should be pushed as onKeyword.
    n_ref = sum('onReference' in c for c in win.calls)
    fake.text = '#사랑'
    assert wait_for(lambda: any('onKeyword' in c for c in win.calls)), \
        "onKeyword was never pushed"
    assert sum('onReference' in c for c in win.calls) == n_ref, \
        "keyword wrongly produced a reference"
    print("monitor: '#사랑' -> onKeyword")

    api.stop_monitoring()
    assert api.monitoring is False


def main():
    api = Api(Library())
    force_korean_primary(api)

    init = api.get_initial()
    assert init['versions'], "no versions"
    assert init['primary'], "no primary version"
    assert init['books'], "no books"
    last = init['last']
    assert last['book'] and last['chapter'], last
    assert isinstance(init['dark_mode'], bool) and isinstance(init['font_size'], int)
    assert init['lex_lang'] in ('ko', 'en'), init['lex_lang']
    assert isinstance(init['search_click_navigates'], bool)
    assert init['version'] == __version__, init['version']
    print(f"get_initial: primary={init['primary']} versions={len(init['versions'])} "
          f"books={len(init['books'])} last={last['book']}:{last['chapter']}")

    assert isinstance(init['viewer'], list) and init['viewer'], init['viewer']
    assert init['primary'] in init['viewer'], (init['primary'], init['viewer'])

    ver = init['primary']
    books = api.get_books(ver)
    assert any(b['num'] == 10 for b in books), "Genesis (10) missing"

    chs = api.get_chapters(ver, 10)
    assert chs and chs[0] == 1
    print(f"get_chapters({ver},10) -> {len(chs)} chapters")

    ch = api.get_chapter(ver, 10, 1)
    assert ch['ref']['chapter'] == 1 and ch['verses'], ch['ref']
    assert ch['verses'][0]['n'] == 1 and '태초' in ch['verses'][0]['text'], ch['verses'][0]
    print(f"get_chapter({ver},10,1) -> {len(ch['verses'])} verses; "
          f"v1: {ch['verses'][0]['text'][:24]}…")

    inter = api.get_interlinear(10, 1)
    assert inter and inter[0]['words'], "interlinear empty"
    first = inter[0]['words'][0]
    assert first['w'] and first['code'], first
    print(f"get_interlinear(10,1) -> {len(inter)} verses; "
          f"v1 first word: {first['w']}/{first['code']}")

    # KJV+ (영어 원전 분해): a Strong-tagged English bible yields the breakdown from
    # its OWN words, H/G prefixed by testament. Gen 1:1 'God'→H430, 'created'→H1254;
    # John 3:16 (NT) carries Greek G-codes. Skipped if KJV+ isn't installed.
    if 'KJV+' in api.lib.dbs:
        kjv = api.get_interlinear(10, 1, 'KJV+')
        words = {w['w']: w['code'] for w in kjv[0]['words']}
        assert words.get('God') == 'H430', words
        assert words.get('created') == 'H1254', words
        assert api.lookup_strong('H430', 'en'), 'H430 not in HebGrkEn.dct'
        john = next(v for v in api.get_interlinear(500, 3, 'KJV+') if v['n'] == 16)
        assert any((w['code'] or '').startswith('G') for w in john['words']), john
        # 한국어 폴백 불변: 비-Strong 역본/버전 미지정은 개역한글S 분해 그대로.
        assert api.get_interlinear(10, 1, 'KRV')[0]['words'][0]['code'].startswith('H')
        print(f"get_interlinear KJV+ -> God/{words['God']} created/{words['created']}; "
              f"John3:16 Greek OK; 개역한글S fallback intact")

    # set_viewer_versions: validation + ordering, WITHOUT touching the real
    # settings file (save_settings stubbed — see headless-test-no-save rule).
    saved = []
    api.lib.save_settings = lambda: saved.append(True)
    all_names = [v['name'] for v in init['versions']]
    if len(all_names) >= 2:
        picked = api.set_viewer_versions([all_names[1], all_names[0], 'BOGUS'])
        assert 'BOGUS' not in picked, picked
        assert set(picked) == {all_names[0], all_names[1]}, picked
        # order follows viewer_version_order, not the argument order
        order = api.lib.settings.get('viewer_version_order') or all_names
        assert picked == [n for n in order if n in (all_names[0], all_names[1])], picked
        assert saved, "save_settings not called"
        # refuse to drop to an empty set
        kept = api.set_viewer_versions([])
        assert kept == picked, kept
        print(f"set_viewer_versions -> {picked} (empty rejected)")

    # ---- Output settings tab (get_settings / set_setting / order / preview) ----
    # save_settings is still the stub from above (no disk writes).
    gs = api.get_settings()
    assert set(gs['format']) == set(Api._FORMAT_KEYS), gs['format'].keys()
    assert isinstance(gs['output_order'], list)
    assert gs['versions'], "no versions in get_settings"

    # enum: valid accepted, invalid rejected
    assert api.set_setting('chapter_verse_format', 'korean')['ok']
    assert api.lib.settings['chapter_verse_format'] == 'korean'
    assert not api.set_setting('chapter_verse_format', 'bogus')['ok']
    assert not api.set_setting('no_such_key', 'x')['ok']
    # bool coercion
    assert api.set_setting('hide_reference', 1)['ok']
    assert api.lib.settings['hide_reference'] is True

    # FEAT-02 클립보드 매직 포맷터: 자유 템플릿 문자열 + 토글. 켜면 매크로 치환 서식이
    # 표준 조립을 대체해 미리보기/복사에 반영된다. (save_settings는 위에서 스텁됨.)
    api.set_setting('hide_reference', False)
    assert api.set_setting('custom_format_template', '[{book_full} {chap}:{verse}] {content}')['ok']
    assert api.set_setting('custom_format_enabled', True)['ok']
    api.set_output_order([all_names[0]])
    prev_tmpl = api.get_preview()
    assert prev_tmpl.startswith('['), prev_tmpl
    assert ':' in prev_tmpl.split(']')[0], prev_tmpl       # [책 1:1-3] 형태
    assert api.set_setting('custom_format_enabled', False)['ok']  # 끄면 표준 서식 복귀
    assert not api.get_preview().startswith('[요'), api.get_preview()
    print(f"custom formatter OK -> {prev_tmpl[:24]}…")

    # FEAT-05 병렬 복사 부스터: 템플릿이 {content2}/{version2}를 쓰고 역본이 2개 이상이면
    # 앞 두 역본을 ONE 블록으로 결합(한/영 한 세트). 클립보드는 FakeClipboard.
    if len(all_names) >= 2:
        assert api.set_setting('custom_format_enabled', True)['ok']
        assert api.set_setting('custom_format_template',
                               '[{book_full} {chap}:{verse}]\n{content}\n[{version2}] {content2}')['ok']
        pair = [all_names[0], all_names[1]]
        r = api.copy_reference(500, 3, [16], pair)            # 요 3:16
        assert r['ok'] and r['n_parts'] == 2, r
        assert f"[{all_names[1]}]" in r['text'], r['text']     # 둘째 역본 라벨 결합
        assert r['text'].count('\n') >= 2, r['text']          # ref / content / content2
        # 템플릿에 content2 없으면 다시 역본별 블록(\n\n)
        api.set_setting('custom_format_template', '[{book_full} {chap}:{verse}] {content}')
        r2 = api.copy_reference(500, 3, [16], pair)
        assert '\n\n' in r2['text'], r2['text']
        api.set_setting('custom_format_enabled', False)
        print(f"parallel copy OK -> 2 versions in one block")

    # output order: filter bogus, dedup, preserve given order
    picked = api.set_output_order([all_names[0], 'BOGUS', all_names[0]])
    assert picked == [all_names[0]], picked
    print(f"get_settings/set_setting/order OK -> order={picked}")

    # preview reflects the current order (요 1:1-3 → John 1:1-3 text)
    api.set_output_order([all_names[0]])
    prev = api.get_preview()
    assert prev and '(' != prev[0], f"preview empty/placeholder: {prev!r}"
    print(f"get_preview -> {prev[:32]}…")
    # empty order → placeholder, not a crash
    api.set_output_order([])
    assert api.get_preview() == '(출력할 성경 버전을 추가하세요)', api.get_preview()

    # markup converter unit checks
    assert markup_to_html('<num>H1</num> a^b') == '<span class="lex-num" data-code="H1">H1</span> a  b'
    assert markup_to_html('') == ''

    strong = api.lookup_strong('H3068')
    if strong is not None:
        assert strong['code'] == 'H3068' and '여호와' in strong['html']
        assert '<num>' not in strong['html'], "raw <num> leaked into html"
        # refined entry: headword (before '^') + reading (first <font>) extracted
        assert strong['headword'] and strong['headword'][0] >= '֐', strong['headword']
        assert 'Yhwh' in strong['reading'], strong['reading']
        # reading was lifted out of the body (not duplicated there)
        assert 'Yhwh' not in strong['html'], strong['html'][:40]
        assert isinstance(strong['morph'], list)
        print(f"lookup_strong('H3068') -> head={strong['headword']} reading={strong['reading'][:16]}…")
    else:
        print("(no lexicon data — skipped lookup_strong)")

    # hover summary (falls back to lexicon gloss when 원전분해 morphology absent)
    hov = api.hover_summary('H3068', 10, 1, 1)
    assert hov['code'] == 'H3068'
    print(f"hover_summary -> {len(hov['lines'])} line(s)")

    # keyword search + copy_reference (clipboard write stubbed out)
    import bibleclip.webui.api as apimod_local
    # check_update lives in the SystemRoutes mixin now (9차 라우트 분리); stub the
    # network where the name is looked up (routes.system), not on the api facade.
    import bibleclip.webui.routes.system as sysroutes
    apimod_local.pyperclip = None  # don't touch the real clipboard
    # search an explicit Korean version (a prior test left primary on English)
    sr = api.search('태초', version=ver)
    assert sr['hits'] and sr['hits'][0]['short'] == '창', sr['hits'][:1]
    api.set_output_order([sr['version']])  # earlier test emptied output_order
    cp = api.copy_reference(sr['hits'][0]['book'], sr['hits'][0]['chapter'],
                            [sr['hits'][0]['verse']])
    assert cp['ok'] and '태초' in cp['text'], cp
    # explicit versions override output_order (viewer manual copy)
    cp2 = api.copy_reference(10, 1, [1], versions=[ver])
    assert cp2['ok'] and '태초' in cp2['text'], cp2
    print(f"search('태초') -> {len(sr['hits'])} hits; copy_reference ok")

    # v1.0.5: 띄어쓰기 다중 키워드 AND/OR 스마트 검색(역색인). AND ⊆ OR, 둘 다 창1:1 포함.
    s_and = api.search('하나님 천지', version=ver, mode='and')
    s_or = api.search('하나님 천지', version=ver, mode='or')
    g11 = lambda r: any(h['book'] == 10 and h['chapter'] == 1 and h['verse'] == 1
                        for h in r['hits'])
    assert s_and['mode'] == 'and' and s_or['mode'] == 'or'
    # 하이라이트용 matched_tokens(조사 제거된 어근) — 프론트가 본문 강조에 사용
    assert s_and['matched_tokens'] == ['하나님', '천지'], s_and['matched_tokens']
    assert g11(s_and) and g11(s_or), "smart search should reach 창1:1"
    assert len(s_or['hits']) >= len(s_and['hits']), (len(s_or['hits']), len(s_and['hits']))
    # 어간 회수: '창조'는 '창조하시니라' 부분일치로 창1:1 도달
    assert g11(api.search('하나님 창조', version=ver, mode='and')), "stem recovery failed"
    print(f"smart search AND={len(s_and['hits'])} OR={len(s_or['hits'])}; 창1:1 + 어간회수 OK")

    # refresh_databases returns the (unchanged here) version list
    rd = api.refresh_databases()
    assert isinstance(rd['added'], list) and rd['versions'], rd
    assert len(rd['versions']) == len(init['versions'])
    print(f"refresh_databases -> +{len(rd['added'])}, total {len(rd['versions'])}")

    # set_viewer_order trusts the given order (drag reorder)
    if len(all_names) >= 2:
        ordr = api.set_viewer_order([all_names[1], all_names[0]])
        assert ordr[:2] == [all_names[1], all_names[0]], ordr

    # open_dict_window is a no-op without a popup factory (headless)
    assert api.open_dict_window('H3068') == {'ok': False}

    # UI prefs (save_settings still stubbed): clamp + persist into settings.
    # Cap raised to 400 in v1.0.6 (대형 스크린/방송 송출); 40 is in-range now.
    assert api.set_font_size(40) == 40 and api.lib.settings['viewer_font_size'] == 40
    assert api.set_font_size(500) == 400
    assert api.set_font_size(2) == 8
    api.set_dark_mode(True)
    assert api.lib.settings['dark_mode'] is True
    api.note_position(500, 3)
    assert api.lib.settings['last_book_num'] == 500 and api.lib.settings['last_chapter'] == 3
    print("ui prefs (font/dark/position) OK")

    # update check: stub the network so the test stays offline/deterministic
    sysroutes.fetch_latest_release = lambda timeout=8: (
        {'version': 'v99.0.0', 'download_url': 'http://x/a.zip',
         'asset_name': 'a.zip', 'body': 'notes'}, '')
    up = api.check_update()
    assert up['ok'] and up['has_update'] and up['latest'] == 'v99.0.0', up
    api.skip_update('v99.0.0')
    assert api.lib.settings['skip_update_version'] == 'v99.0.0'
    assert api.check_update()['skipped'] is True
    sysroutes.fetch_latest_release = lambda timeout=8: (None, '네트워크 오류')
    assert api.check_update()['ok'] is False
    # install only runs in a frozen build → graceful refusal under source mode
    assert api.install_update()['ok'] is False
    print("check_update (stubbed) + install source-mode guard OK")

    # ---- App settings (⚙ window): get / set / reset (save_settings stubbed) ----
    aset = api.get_app_settings()
    assert aset['version'] == __version__, aset['version']
    assert aset['lex_lang'] in ('ko', 'en'), aset
    assert isinstance(aset['poll_interval'], float), aset
    assert aset['repo_url'].startswith('https://'), aset['repo_url']
    # poll_interval: coerced to float and clamped to [0.1, 2.0]
    assert api.set_app_setting('poll_interval', 5)['value'] == 2.0
    assert api.set_app_setting('poll_interval', 0)['value'] == 0.1
    assert api.set_app_setting('poll_interval', 0.25)['value'] == 0.25
    assert api.lib.settings['poll_interval'] == 0.25
    # lex_lang enum: valid accepted, invalid rejected
    assert api.set_app_setting('lex_lang', 'en')['ok']
    assert api.lib.settings['lex_lang'] == 'en'
    assert not api.set_app_setting('lex_lang', 'fr')['ok']
    # boolean keys coerced
    assert api.set_app_setting('search_click_navigates', 1)['ok']
    assert api.lib.settings['search_click_navigates'] is True
    assert api.set_app_setting('auto_update_check', 0)['ok']
    assert api.lib.settings['auto_update_check'] is False
    # 검색 최고점 자동 복사 옵션 (기본 False, get_initial/get_app_settings 노출)
    assert api.get_initial()['auto_copy_top_result'] is False
    assert api.get_app_settings()['auto_copy_top_result'] is False
    assert api.set_app_setting('auto_copy_top_result', 1)['ok']
    assert api.lib.settings['auto_copy_top_result'] is True
    assert api.get_app_settings()['auto_copy_top_result'] is True
    # unknown key rejected
    assert not api.set_app_setting('no_such_app_key', 1)['ok']
    print("app settings get/set (poll clamp, lex enum, bool) OK")

    # web_cards_layout: 'any' spec — stored verbatim, exposed by get_initial /
    # get_app_settings, and clearable back to None. Non-serializable rejected.
    assert 'web_cards_layout' in api.get_initial()
    layout = [{'id': 'bible-1', 'type': 'bible', 'version': ver,
               'book': 10, 'chapter': 1, 'locked': False},
              {'id': 'bible-2', 'type': 'bible', 'version': ver,
               'book': 10, 'chapter': 2, 'locked': True}]
    assert api.save_cards_layout(layout)['ok']
    assert api.lib.settings['web_cards_layout'] == layout
    assert api.get_initial()['web_cards_layout'] == layout
    assert api.get_app_settings()['web_cards_layout'] == layout
    # a non-JSON value is rejected without mutating the stored layout
    assert not api.set_app_setting('web_cards_layout', {1, 2, 3})['ok']
    assert api.lib.settings['web_cards_layout'] == layout
    # None clears it
    assert api.save_cards_layout(None)['ok']
    assert api.lib.settings['web_cards_layout'] is None
    print("web_cards_layout get/set/clear (any spec) OK")

    # reset restores every default
    api.save_cards_layout([{'id': 'bible-1', 'type': 'bible'}])  # dirty it first
    api.reset_settings()
    assert api.lib.settings['poll_interval'] == Library.DEFAULT_SETTINGS['poll_interval']
    assert api.lib.settings['lex_lang'] == 'ko'
    assert api.lib.settings['search_click_navigates'] is False
    assert api.lib.settings['web_cards_layout'] is None
    print("reset_settings -> defaults restored")

    monitor_check()

    # unified search bar (Phase 2): resolve_reference parses → navigable target;
    # search_strong reverse-queries the Strong-tagged KRV (개역한글S).
    rr = api.resolve_reference('창 1:1')
    assert rr and rr['book_num'] == 10 and rr['chapter'] == 1 and rr['verses'] == [1], rr
    assert api.resolve_reference('점심 뭐먹지') is None
    if api.lib.bethlehem_strongs:
        ss = api.search_strong('H7225')
        assert ss['count'] >= 1 and any(h['ref'].endswith('1:1') for h in ss['hits']), ss
        print(f"resolve_reference + search_strong('H7225') -> {ss['count']} hits OK")
    else:
        print("resolve_reference OK (개역한글S absent — search_strong skipped)")

    # 묵상 노트 CRUD (Phase 3) — stub the disk write so the test never touches
    # userdata/user_notes.json, and start from an empty store so the test is
    # hermetic (the real file may hold notes from manual testing).
    api.lib.notes._save = lambda: True
    api.lib.notes.data = {}
    assert api.get_note(10, 1, 1) is None
    api.set_note(10, 1, 1, "  태초 묵상  ")
    n = api.get_note(10, 1, 1)
    assert n and n['text'] == '태초 묵상', n
    assert api.get_chapter_notes(10, 1) == {1: '태초 묵상'}, api.get_chapter_notes(10, 1)
    api.set_note(10, 1, 1, "")  # empty text deletes
    assert api.get_note(10, 1, 1) is None
    print("notes CRUD (set/get/chapter/delete) OK")

    # 설교 장바구니 영속성 (FEAT-08, v1.1.4) — stub the disk write and start empty
    # so the test never touches userdata/sermon_cart.json. set_cart replaces the
    # whole list (sanitizing junk); get_cart + get_initial.cart reflect it.
    api.lib.cart._save = lambda: True
    api.lib.cart.items = []
    assert api.get_cart() == []
    r = api.set_cart([
        {'book_num': 10, 'chapter': 1, 'verses': ['1', '2', 3], 'short_name': '창'},
        {'book': 470, 'chapter': 3, 'verses': [16]},   # book→book_num alias
        'garbage', {'no_book': True},                  # dropped
    ])
    assert r['ok'] and len(r['items']) == 2, r
    assert r['items'][0] == {'book_num': 10, 'chapter': 1,
                             'verses': [1, 2, 3], 'short_name': '창'}, r['items'][0]
    assert api.get_cart() == r['items']
    assert api.get_initial()['cart'] == r['items']     # boot payload restores it
    print("cart persistence (set/get/get_initial round-trip) OK")

    # 설교 장바구니 팝아웃 창 + 양방향 동기화 (FEAT-07, v1.1.5). Fake windows record
    # evaluate_js so we can assert the broadcast/jump without a real webview.
    class _FakeWin:
        def __init__(self):
            self.calls = []

        def evaluate_js(self, js):
            self.calls.append(js)

    main_win, cart_win = _FakeWin(), _FakeWin()
    api.set_window(main_win)
    assert api.open_cart_window()['ok'] is False        # no factory yet → no-op
    opened = []

    def _factory():
        api._cart_window = cart_win
        opened.append(1)
        return cart_win
    api.set_cart_window_factory(_factory)
    assert api.open_cart_window()['ok'] is True and opened == [1]
    api.set_cart([{'book_num': 10, 'chapter': 1, 'verses': [1], 'short_name': '창'}])
    assert any('onCartChanged' in c for c in main_win.calls)   # main drawer synced
    assert any('renderCartItems' in c for c in cart_win.calls)  # pop-out synced
    main_win.calls.clear()
    assert api.cart_goto(10, 1, [1])['ok'] is True
    assert any('cartGoto' in c for c in main_win.calls)        # jumps the main viewer
    api._cart_window = None
    api.set_cart([])                                           # closed window → no raise
    api.set_window(None)                                       # restore headless state
    print("cart pop-out window (open/broadcast/cart_goto) OK")

    # 패치노트 모달 가드 (Phase 4): show once, then dismissed. Stub save_settings
    # so the test never writes to disk.
    api.lib.save_settings = lambda: None
    api.lib.settings['seen_version'] = None
    api.lib.settings['dismissed_patches'] = []
    p = api.get_patch_notes()
    assert p['version'] == __version__, p
    if p['notes']:
        assert p['show'] is True
        api.dismiss_patch(False)
        assert api.get_patch_notes()['show'] is False  # seen this version now
        api.lib.settings['seen_version'] = None
        api.dismiss_patch(True)  # forever
        assert __version__ in api.lib.settings['dismissed_patches']
        assert api.get_patch_notes()['show'] is False
        print(f"patch modal guard OK (v{__version__}: {len(p['notes'])} notes)")
    else:
        print(f"patch modal guard OK (no notes for v{__version__})")

    print("\nALL WEBUI API CHECKS PASSED ✅")


if __name__ == '__main__':
    main()
    sys.stdout.flush()
    os._exit(0)
