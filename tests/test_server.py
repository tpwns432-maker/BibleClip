"""웹판 서버 테스트 (docs/WEB_PLAN.md 1 · 2단계).

    python -X utf8 tests/test_server.py

데이터 폴더를 임시 폴더로 정한 뒤(BIBLECLIP_DATA_DIR) 서버를 Flask 시험 손님으로 부른다.
개발자의 설정 · 노트 파일은 건드리지 않는다. 역본은 저장소의 bible_versions(개역한글)에서 찾는다.
"""
import json
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = tempfile.mkdtemp(prefix='bibleclip-web-')
os.environ['BIBLECLIP_DATA_DIR'] = DATA   # bibleclip 을 가져오기 전에

import bibleclip.config as config          # noqa: E402
import bibleclip.webui.api as apimod        # noqa: E402
from bibleclip.core.library import Library  # noqa: E402
from bibleclip.server import accounts as acc_mod  # noqa: E402
from bibleclip.server.__main__ import main as server_main  # noqa: E402
from bibleclip.server.accounts import Accounts, Throttle, check_password, hash_password  # noqa: E402
from bibleclip.server.app import create_app  # noqa: E402
from bibleclip.server.webapi import ALLOWED, WebApi, WebHub  # noqa: E402

H = {'X-BibleClip': '1'}
PW = {'alice': 'alice-pass-1', 'bob': 'bob-pass-22'}


def post(client, name, *args, headers=H):
    return client.post('/api/' + name, json={'args': list(args)}, headers=headers)


def value(client, name, *args):
    r = post(client, name, *args)
    assert r.status_code == 200, (name, r.status_code, r.get_data(as_text=True))
    return r.get_json()['value']


def login(app, uid, pw=None):
    c = app.test_client()
    r = c.post('/login', data={'id': uid, 'password': pw or PW[uid.strip().lower()]})
    assert r.status_code == 303, (uid, r.status_code)
    return c


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t


def check_accounts(accounts):
    # 비밀번호 해시: 맞는 것만 통과, 원문은 파일에 없다.
    h = hash_password('pässwörd-1')
    assert check_password('pässwörd-1', h) and not check_password('pässwörd-2', h)
    assert not check_password('x', 'garbage') and not check_password('x', 'md5$1$2$3$aa$bb')
    assert accounts.verify('alice', PW['alice'])['name'] == '앨리스'
    assert accounts.verify('alice', 'wrong') is None and accounts.verify('nobody', 'x') is None
    raw = open(os.path.join(DATA, 'users.json'), encoding='utf-8').read()
    assert PW['alice'] not in raw and 'scrypt$' in raw
    for bad in (('Alice', 'n', 'long-enough'), ('a', 'n', 'long-enough'), ('../x', 'n', 'long-enough'),
                ('carol', 'n', 'short'), ('alice', 'n', 'long-enough')):
        try:
            accounts.add(*bad)
        except ValueError:
            continue
        raise AssertionError(f'거절해야 한다: {bad}')
    # 로그인 실패 제한: 15분 안에 5번 → 막힘, 15분 지나면 풀림.
    clock = Clock()
    t = Throttle(clock=clock)
    for _ in range(4):
        t.fail('id:a')
    assert not t.blocked('id:a')
    t.fail('id:a')
    assert t.blocked('id:a', 'ip:x') and not t.blocked('id:b')
    clock.t += 15 * 60 + 1
    assert not t.blocked('id:a')


def run():
    # 데이터 폴더: 임시 폴더 + 저장소 자료도 찾는다.
    assert os.path.realpath(config.BASE_DIR) == os.path.realpath(DATA), config.BASE_DIR
    assert config.get_app_dir() in config.candidate_data_roots()

    # 허용 목록의 이름은 모두 진짜 기능이어야 한다(오타 방지).
    missing = [n for n in ALLOWED if not callable(getattr(WebApi, n, None))]
    assert not missing, missing

    accounts = Accounts(DATA)
    accounts.add('alice', '앨리스', PW['alice'])
    accounts.add('bob', '밥', PW['bob'])
    check_accounts(accounts)

    apimod.pyperclip = None   # 서버 실행(__main__)과 같게: 서버 클립보드는 안 건드림
    engine = Library()
    assert 'KRV' in engine.dbs, '저장소의 개역한글을 찾아야 한다'
    hub = WebHub(engine, DATA)
    app = create_app(hub, accounts, 'k' * 64, Throttle())
    anon = app.test_client()

    # ---- 로그인 없이는 로그인 화면과 아이콘만 ----
    for page in ('/', '/bible', '/community'):
        r = anon.get(page)
        assert r.status_code == 302 and r.headers['Location'].endswith('login'), (page, r.status_code)
    assert 'name="password"' in anon.get('/login').get_data(as_text=True)
    assert anon.get('/favicon.ico').status_code == 200
    for path in ('/js/core.js', '/_web/bridge.js', '/_web/site.js', '/auth/me', '/index.html'):
        assert anon.get(path).status_code in (302, 401), path
    assert post(anon, 'get_initial').status_code == 401
    assert post(anon, 'get_chapter', 'KRV', 10, 1).status_code == 401

    # 틀린 비밀번호 · 다른 사이트에서 보낸 로그인 폼은 거절.
    assert anon.post('/login', data={'id': 'alice', 'password': 'nope'}).status_code == 401
    assert anon.post('/login', data={'id': 'alice', 'password': PW['alice']},
                     headers={'Origin': 'https://evil.example'}).status_code == 403

    alice = login(app, 'alice')
    bob = login(app, 'Bob ')      # 아이디는 앞뒤 공백 · 대문자를 정리한다
    cookie = alice.get_cookie('bibleclip_session')
    assert cookie is not None and cookie.http_only and cookie.same_site == 'Lax'
    assert not cookie.secure
    me = alice.get('/auth/me').get_json()
    assert me['id'] == 'alice' and me['name'] == '앨리스' and 'theme' in me and 'dark_mode' in me
    assert alice.get('/login').status_code == 302

    # ---- 화면: index.html 에 연결 JS(맨 앞 스크립트 앞) · 웹용 CSS 를 끼운다 ----
    # 홈 · 커뮤니티 · 성경(/index.html 은 예전 주소 → 성경).
    assert 'href="bible"' in alice.get('/').get_data(as_text=True)
    assert 'community.js' in alice.get('/community').get_data(as_text=True)
    assert alice.get('/index.html').headers['Location'].endswith('bible')
    html = alice.get('/bible').get_data(as_text=True)
    assert html.index('_web/bridge.js') < html.index('js/i18n.js')
    assert '_web/web.css' in html
    for path in ('/_web/bridge.js', '/_web/web.css', '/_web/site.js', '/_web/site.css',
                 '/_web/community.js', '/js/core.js', '/js/theme.js', '/css/tokens.css'):
        assert alice.get(path).status_code == 200, path
    # web/ 밖의 파일은 못 꺼낸다(계정 파일 · 열쇠 포함).
    for path in ('/../bibleclip_settings.json', '/..%2Fbibleclip_settings.json', '/_web/../app.py',
                 '/bibleclip/server/app.py', '/../users.json', '/_web/../../users.json'):
        assert alice.get(path).status_code == 404, path

    # 머리글 없는 요청(다른 사이트의 폼 등) · 다른 호스트 이름은 거절.
    assert post(alice, 'get_initial', headers={}).status_code == 403
    assert alice.get('/', headers={'Host': 'evil.example'}).status_code == 403
    assert alice.get('/', headers={'Host': 'localhost:8765'}).status_code == 200
    assert alice.get('/', headers={'Host': '[::1]:8765'}).status_code != 403   # 쿠키는 호스트별이라 로그인 화면으로
    assert alice.post('/api/get_books', json={'args': 'KRV'}, headers=H).status_code == 400
    assert post(alice, 'get_note', 1).status_code == 400

    # 휴대폰 화면: 안드로이드 앱의 mobile.css 를 휴대폰일 때만 켜지게(media) 끼우고, 그 두 파일만 내준다.
    assert 'id="bc-phone-css"' in html and 'media="(pointer: coarse)' in html
    assert html.index('_android/mobile.css') < html.index('_web/web.css')
    assert alice.get('/_android/mobile.css').status_code == 200
    assert alice.get('/_android/mobile.js').status_code == 200
    assert alice.get('/_android/../java/com/bibleclip/app/Bridge.kt').status_code == 404
    assert alice.get('/_android/AndroidManifest.xml').status_code == 404
    assert anon.get('/_android/mobile.css').status_code == 401
    # 폰의 카드 배치 · 글자 크기는 PC 설정과 따로.
    assert value(alice, 'get_phone_prefs') == {}
    lay = [{'id': 'bible-1', 'type': 'bible', 'x': 0, 'y': 0, 'w': 100, 'h': 100}]
    assert value(alice, 'save_phone_prefs', {'layout': lay})['ok']
    assert value(alice, 'save_phone_prefs', {'font_size': 999})['ok']
    assert value(alice, 'get_phone_prefs') == {'layout': lay, 'font_size': 400}
    assert value(alice, 'get_initial')['web_cards_layout'] != lay        # PC 배치는 그대로
    assert value(bob, 'get_phone_prefs') == {}                           # 사람마다 따로
    assert value(alice, 'save_phone_prefs', {'layout': 'x' * 70000})['ok'] is False
    assert value(alice, 'save_phone_prefs', 'nope')['ok'] is False

    # 첫 화면 값: 웹은 업데이트 확인 · 첫 실행 안내 · 장바구니가 없고, 누가 들어왔는지 안다.
    init = value(alice, 'get_initial')
    assert init['primary'] == 'KRV', init['primary']
    assert init['auto_update_check'] is False and init['tour_done'] is True and init['cart'] == []
    assert init['web_user'] == {'id': 'alice', 'name': '앨리스'}

    # 데스크톱 전용 기능은 허용 목록 밖 → null, 아무 일도 안 일어난다.
    for name in ('install_update', 'open_data_folder', 'open_bible_folder', 'add_bible_files',
                 'start_monitoring', 'open_subtitle_window', 'open_cart_window', 'set_cart',
                 'copy_text', 'export_text_file', 'check_update', '__init__', 'lib', 'user'):
        assert value(alice, name) is None, name

    # 본문 · 검색 · 복사(서버는 글만 만든다).
    assert '태초' in json.dumps(value(alice, 'get_chapter', 'KRV', 10, 1), ensure_ascii=False)
    res = value(alice, 'search', '태초', 'KRV')
    assert res and res.get('hits'), res
    c = value(alice, 'copy_reference', 500, 3, [16])
    assert c['ok'] and '하나님이 세상을' in c['text'], c

    # ---- 사람마다 따로: 노트 · 형광펜 · 설정 ----
    assert value(alice, 'set_note', 500, 3, 16, '앨리스의 노트')['ok']
    assert value(alice, 'get_note', 500, 3, 16)['text'] == '앨리스의 노트'
    assert value(bob, 'get_note', 500, 3, 16) is None
    assert value(bob, 'set_note', 500, 3, 16, '밥의 노트')['ok']
    assert value(alice, 'get_note', 500, 3, 16)['text'] == '앨리스의 노트'
    rng = [{'s': 0, 'e': 3, 't': '하나님', 'c': 'y'}]
    value(alice, 'set_verse_highlights', 500, 3, 16, 'KRV', rng)
    assert value(alice, 'get_verse_highlights', 500, 3, 16, 'KRV')
    assert not value(bob, 'get_verse_highlights', 500, 3, 16, 'KRV')
    value(alice, 'set_font_size', 30)
    value(alice, 'note_position', 500, 3)     # 웹엔 창 닫기가 없으니 바로 저장
    assert value(bob, 'get_initial')['font_size'] == 11
    assert value(alice, 'get_initial')['font_size'] == 30
    adir = os.path.join(DATA, 'users', 'alice')
    with open(os.path.join(adir, 'user_notes.json'), encoding='utf-8') as f:
        assert '앨리스의 노트' in f.read()
    with open(os.path.join(DATA, 'users', 'bob', 'user_notes.json'), encoding='utf-8') as f:
        assert '앨리스' not in f.read()
    assert os.path.exists(os.path.join(adir, 'user_highlights.json'))
    with open(os.path.join(adir, config.SETTINGS_FILE), encoding='utf-8') as f:
        saved = json.load(f)
    assert saved['last_book_num'] == 500 and saved['viewer_font_size'] == 30
    assert not os.path.exists(os.path.join(DATA, config.SETTINGS_FILE)), '공용 설정 파일에 쓰면 안 된다'
    # 성경 엔진은 한 벌을 나눠 쓴다.
    assert hub.api_for('alice').lib.dbs is engine.dbs is hub.api_for('bob').lib.dbs

    # 상대 형광펜(4단계): 밥은 앨리스가 칠한 것을 받고, 앨리스 자신의 요청엔 앨리스 것이 없다.
    r = alice.post('/capi/partner_highlights', json={'book': 500, 'chapter': 3, 'versions': ['KRV']}, headers=H)
    assert r.status_code == 200 and r.get_json()['value'] == []        # 밥은 아직 안 칠함
    got = bob.post('/capi/partner_highlights', json={'book': 500, 'chapter': 3, 'versions': ['KRV']},
                   headers=H).get_json()['value']
    assert got == [{'user': {'id': 'alice', 'name': '앨리스'}, 'hl': {'KRV': {'16': [dict(rng[0], ts=got[0]['hl']['KRV']['16'][0]['ts'])]}}}], got
    assert bob.post('/capi/partner_highlights', json={'book': 'x', 'chapter': 3}, headers=H).status_code == 400
    assert bob.post('/capi/partner_highlights', json={'book': 500, 'chapter': 3}).status_code == 403
    assert bob.post('/capi/partner_highlights', json={'book': 500, 'chapter': 4, 'versions': ['KRV']},
                    headers=H).get_json()['value'] == []
    # 글에 단 구절의 본문 인용(읽는 사람의 맨 앞 역본).
    vt = hub.verse_text('bob', {'book': 500, 'chapter': 3, 'verse': 16, 'verse_end': 17})
    assert vt['version'].endswith('[KRV]') and [x['n'] for x in vt['verses']] == [16, 17]
    assert '하나님이 세상을' in vt['verses'][0]['text']

    # 사전 창: 페이지를 돌려주면 브라우저가 새 창으로 연다.
    if engine.lexicon_ko is not None or engine.lexicon_en is not None:
        d = value(alice, 'open_dict_window', 'H430', 'ko', 10, 1, None, 'light')
        assert d['ok'] and '<html' in d['html'].lower() and d['title'], d

    # ---- 로그아웃 · 비밀번호 변경 ----
    assert alice.post('/logout').status_code == 403            # 머리글 없는 로그아웃(다른 사이트) 거절
    assert alice.post('/logout', headers=H).get_json() == {'ok': True}
    assert post(alice, 'get_initial').status_code == 401
    accounts.set_password('bob', 'bob-new-pass-3')               # 예전 로그인은 모두 풀린다
    assert post(bob, 'get_initial').status_code == 401
    login(app, 'bob', 'bob-new-pass-3')

    # 로그인 실패 제한(서버): 5번 틀리면 맞는 비밀번호도 잠시 거절.
    c2 = create_app(hub, accounts, 'k' * 64, Throttle()).test_client()
    for _ in range(5):
        assert c2.post('/login', data={'id': 'alice', 'password': 'nope'}).status_code == 401
    assert c2.post('/login', data={'id': 'alice', 'password': PW['alice']}).status_code == 429

    # 쿠키 https 전용 옵션.
    c3 = create_app(hub, accounts, 'k' * 64, Throttle(), secure_cookie=True).test_client()
    c3.post('/login', data={'id': 'alice', 'password': PW['alice']})
    assert c3.get_cookie('bibleclip_session').secure

    # ---- 5단계: Tailscale 뒤에서 ----
    ts = 'bc.tail1234.ts.net'
    app4 = create_app(hub, accounts, 'k' * 64, Throttle(), extra_hosts=[ts.upper()], behind_proxy=True,
                      secure_cookie=True)
    c4 = app4.test_client()
    assert c4.get('/login', headers={'Host': ts}).status_code == 200
    assert c4.get('/login', headers={'Host': 'evil.example'}).status_code == 403
    # 앞 프로그램이 호스트를 127.0.0.1 로 바꿔 넘겨도 정해 둔 주소에서 온 로그인은 받고, 남의 사이트는 거절.
    assert c4.post('/login', data={'id': 'alice', 'password': PW['alice']},
                   headers={'Origin': 'https://' + ts}).status_code == 303
    assert c4.post('/login', data={'id': 'alice', 'password': PW['alice']},
                   headers={'Origin': 'https://evil.example'}).status_code == 403
    # 접속한 사람 주소는 앞 프로그램이 알려 준 것으로 센다 — 한 사람이 틀려도 다른 사람은 안 막힌다.
    c5 = app4.test_client()
    for _ in range(5):
        c5.post('/login', data={'id': 'nobody', 'password': 'x'}, headers={'X-Forwarded-For': '100.64.0.9'})
    assert c5.post('/login', data={'id': 'alice', 'password': PW['alice']},
                   headers={'X-Forwarded-For': '100.64.0.9'}).status_code == 429
    assert c5.post('/login', data={'id': 'alice', 'password': PW['alice']},
                   headers={'X-Forwarded-For': '100.64.0.10'}).status_code == 303

    # ---- 내 비밀번호 바꾸기 ----
    me1 = login(app, 'alice')
    me2 = login(app, 'alice')                                   # 다른 기기
    PWC = lambda c, cur, new, h=H: c.post('/account/password', json={'current': cur, 'new': new}, headers=h)  # noqa: E731
    assert PWC(me1, PW['alice'], 'new-alice-pass', {}).status_code == 403   # 머리글 없음
    assert PWC(me1, 'wrong-pass', 'new-alice-pass').get_json()['error'] == 'wrong'
    assert PWC(me1, PW['alice'], 'short').status_code == 400
    assert PWC(me1, PW['alice'], 'new-alice-pass').get_json() == {'ok': True}
    assert post(me1, 'get_initial').status_code == 200            # 이 기기는 그대로
    assert post(me2, 'get_initial').status_code == 401            # 다른 기기는 풀림
    login(app, 'alice', 'new-alice-pass')
    assert anon.post('/account/password', json={}, headers=H).status_code == 401
    accounts.set_password('alice', PW['alice'])

    # ---- 명령 ----
    try:
        server_main(['--data', DATA, '--host', '0.0.0.0'])   # 아직 이 컴퓨터에서만 연다
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError('0.0.0.0 을 거절해야 한다')
    answers = iter(['carol-pass-9', 'carol-pass-9'])
    acc_mod.getpass.getpass = lambda prompt='': next(answers)
    assert acc_mod.main(['--data', DATA, 'add', 'carol', '--name', '캐럴']) == 0
    assert accounts.verify('carol', 'carol-pass-9')['name'] == '캐럴'
    assert acc_mod.main(['--data', DATA, 'remove', 'carol']) == 0
    assert accounts.get('carol') is None
    # 계정이 없으면 서버가 켜지지 않고 만드는 법을 알려 준다(⚠ config 를 다시 읽으므로 맨 마지막).
    empty = tempfile.mkdtemp(prefix='bibleclip-web-empty-')
    try:
        server_main(['--data', empty])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError('계정이 없으면 켜지면 안 된다')
    finally:
        shutil.rmtree(empty, ignore_errors=True)

    print('test_server: ok')


if __name__ == '__main__':
    code = 0
    try:
        run()
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        shutil.rmtree(DATA, ignore_errors=True)
    sys.stdout.flush()
    os._exit(code)
