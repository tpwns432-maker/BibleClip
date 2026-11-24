"""웹판 서버 테스트 (docs/WEB_PLAN.md 1단계).

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
from bibleclip.server.__main__ import main as server_main  # noqa: E402
from bibleclip.server.app import create_app  # noqa: E402
from bibleclip.server.webapi import ALLOWED, WebApi  # noqa: E402

H = {'X-BibleClip': '1'}


def post(client, name, *args, headers=H):
    return client.post('/api/' + name, json={'args': list(args)}, headers=headers)


def value(client, name, *args):
    r = post(client, name, *args)
    assert r.status_code == 200, (name, r.status_code, r.get_data(as_text=True))
    return r.get_json()['value']


def run():
    # 데이터 폴더: 임시 폴더 + 저장소 자료도 찾는다.
    assert os.path.realpath(config.BASE_DIR) == os.path.realpath(DATA), config.BASE_DIR
    assert config.get_app_dir() in config.candidate_data_roots()

    # 허용 목록의 이름은 모두 진짜 기능이어야 한다(오타 방지).
    missing = [n for n in ALLOWED if not callable(getattr(WebApi, n, None))]
    assert not missing, missing

    apimod.pyperclip = None   # 서버 실행(__main__)과 같게: 서버 클립보드는 안 건드림
    lib = Library()
    assert 'KRV' in lib.dbs, '저장소의 개역한글을 찾아야 한다'
    lib.settings['viewer_versions'] = ['KRV']
    lib.settings['output_order'] = ['KRV']
    client = create_app(WebApi(lib)).test_client()

    # 화면: index.html 에 연결 JS(맨 앞 스크립트 앞) · 웹용 CSS 를 끼운다.
    html = client.get('/').get_data(as_text=True)
    assert html.index('_web/bridge.js') < html.index('js/i18n.js')
    assert '_web/web.css' in html
    for path in ('/_web/bridge.js', '/_web/web.css', '/js/core.js', '/css/tokens.css', '/favicon.ico'):
        assert client.get(path).status_code == 200, path
    # web/ 밖의 파일은 못 꺼낸다.
    for path in ('/../bibleclip_settings.json', '/..%2Fbibleclip_settings.json',
                 '/_web/../app.py', '/bibleclip/server/app.py'):
        assert client.get(path).status_code == 404, path

    # 머리글 없는 요청(다른 사이트의 폼 등) · 다른 호스트 이름은 거절.
    assert post(client, 'get_initial', headers={}).status_code == 403
    assert client.get('/', headers={'Host': 'evil.example'}).status_code == 403
    assert client.get('/', headers={'Host': 'localhost:8765'}).status_code == 200
    assert client.get('/', headers={'Host': '[::1]:8765'}).status_code == 200
    # 모양이 틀린 요청.
    assert client.post('/api/get_books', json={'args': 'KRV'}, headers=H).status_code == 400
    assert post(client, 'get_note', 1).status_code == 400

    # 첫 화면 값: 웹은 업데이트 확인 · 첫 실행 안내 · 장바구니가 없다.
    init = value(client, 'get_initial')
    assert init['primary'] == 'KRV'
    assert init['auto_update_check'] is False and init['tour_done'] is True and init['cart'] == []

    # 데스크톱 전용 기능은 허용 목록 밖 → null, 아무 일도 안 일어난다.
    for name in ('install_update', 'open_data_folder', 'open_bible_folder', 'add_bible_files',
                 'start_monitoring', 'open_subtitle_window', 'open_cart_window', 'set_cart',
                 'copy_text', 'export_text_file', 'check_update', '__init__', 'lib'):
        assert value(client, name) is None, name

    # 본문 · 검색.
    ch = value(client, 'get_chapter', 'KRV', 10, 1)
    assert '태초' in json.dumps(ch, ensure_ascii=False)
    res = value(client, 'search', '태초', 'KRV')
    assert res and res.get('hits'), res

    # 복사: 서버는 글만 만든다.
    c = value(client, 'copy_reference', 500, 3, [16])
    assert c['ok'] and '하나님이 세상을' in c['text'], c

    # 노트 · 형광펜 · 설정은 임시 데이터 폴더에 저장된다.
    assert value(client, 'set_note', 430, 3, 16, '웹 노트')['ok']
    assert value(client, 'get_note', 430, 3, 16)['text'] == '웹 노트'
    with open(os.path.join(DATA, 'userdata', 'user_notes.json'), encoding='utf-8') as f:
        assert '웹 노트' in f.read()
    value(client, 'note_position', 430, 3)   # 웹엔 창 닫기가 없으니 바로 저장
    with open(os.path.join(DATA, config.SETTINGS_FILE), encoding='utf-8') as f:
        saved = json.load(f)
    assert saved['last_book_num'] == 430 and saved['last_chapter'] == 3

    # 사전 창: 페이지를 돌려주면 브라우저가 새 창으로 연다.
    if lib.lexicon_ko is not None or lib.lexicon_en is not None:
        d = value(client, 'open_dict_window', 'H430', 'ko', 10, 1, None, 'light')
        assert d['ok'] and '<html' in d['html'].lower() and d['title'], d

    # 1단계는 이 컴퓨터에서만 연다.
    try:
        server_main(['--data', DATA, '--host', '0.0.0.0'])
    except SystemExit as e:
        assert e.code == 2
    else:
        raise AssertionError('0.0.0.0 을 거절해야 한다')

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
