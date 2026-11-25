"""성경읽기 체크 테스트 (bibleclip/server/readingcheck.py + community 의 reading_day).

    python -X utf8 tests/test_readingcheck.py
"""
import os
import shutil
import sys
import tempfile
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = tempfile.mkdtemp(prefix='bibleclip-rc-')
os.environ['BIBLECLIP_DATA_DIR'] = DATA

from bibleclip.server import readingplan as rp  # noqa: E402
from bibleclip.server.community import Community, CommunityError  # noqa: E402
from bibleclip.server.readingcheck import ReadingCheck  # noqa: E402

BOOKS = [(10, '창', 50), (20, '출', 40)] + [(30 + i, f'b{i}', 30) for i in range(40)]
NAMES = {'alice': {'name': '앨리스'}, 'bob': {'name': '밥'}}


def err(code, fn, *args):
    try:
        fn(*args)
    except CommunityError as e:
        assert e.code == code, (code, e.code, e.detail)
        return
    raise AssertionError(f'{code} 이어야 한다')


def run():
    today = {'v': date(2026, 11, 27)}
    box = {}
    events = []
    com = Community(os.path.join(DATA, 'c.db'), names=lambda: NAMES, on_event=events.append,
                    today=lambda: today['v'], reading_info=lambda iso: box['c'].info_iso(iso))
    check = ReadingCheck(com, lambda: NAMES, rp.chapter_list(BOOKS), today=lambda: today['v'])
    box['c'] = check
    tid = com.reading_topic()['id']
    assert [t['name'] for t in com.topics('alice')][0] == '성경읽기 체크'

    def write(uid, day, title='t'):
        return com.post_save(uid, {'topic_id': tid, 'title': title, 'body': '짧은 생각', 'reading_day': day})['id']

    # 날짜 검사: 시작일 ~ 오늘만, 모양이 틀리면 거절. 비우면 일반 글.
    for bad in ('2026-11-24', '2026-11-28', '어제', '2026-13-01', 5):
        err('invalid', write, 'alice', bad)
    plain = com.post_save('alice', {'topic_id': tid, 'title': 'x', 'body': 'y', 'reading_day': ''})['id']
    assert com.post('alice', {'id': plain})['reading_day'] is None

    # 시작 전 · 첫날.
    st = check.status('alice')
    assert st['started'] and st['today']['day'] == 3 and len(st['history']) == 3
    assert [u['id'] for u in st['users']] == ['alice', 'bob'] and st['users'][0]['me']
    assert st['users'][0] == {'id': 'alice', 'name': '앨리스', 'me': True, 'today': None, 'streak': 0,
                              'done': 0, 'elapsed': 3}

    # 체크: 1 · 2 · 3일째 앨리스, 2일째 밥(지난 날도 나중에 쓰면 체크).
    a1 = write('alice', '2026-11-25')
    write('alice', '2026-11-26')
    a3 = write('alice', '2026-11-27')
    b2 = write('bob', '2026-11-26')
    write('alice', '2026-11-27', 'two')         # 같은 날 두 번 써도 하루로 센다(처음 글이 기록)
    assert events[-1] == {'kind': 'post', 'author': 'alice', 'post_id': events[-1]['post_id'],
                          'reading_day': '2026-11-27'}
    st = check.status('alice')
    me, bob = st['users']
    assert (me['today'], me['streak'], me['done']) == (a3, 3, 3)
    assert (bob['today'], bob['streak'], bob['done']) == (None, 1, 1)   # 오늘 아직 → 어제까지 이어진 1일
    assert st['today']['done'] == {'alice': a3}
    assert [h['date'] for h in st['history']] == ['2026-11-27', '2026-11-26', '2026-11-25']
    assert st['history'][1]['done'] == {'alice': st['history'][1]['done']['alice'], 'bob': b2}
    assert st['history'][2]['label'] == '창 1–4장' and st['history'][2]['day'] == 1
    assert check.done_on(date(2026, 11, 26)).keys() == {'alice', 'bob'}

    # 글 칩: 몇째 날 · 범위.
    p = com.post('bob', {'id': a1})
    assert p['reading_day'] == '2026-11-25' and p['reading']['day'] == 1 and p['reading']['label'] == '창 1–4장'
    assert com.posts('bob', {'topic_id': tid})['posts'][0]['reading'] is not None

    # 고칠 때 날짜를 안 보내면 그대로, 지우면 체크에서 빠진다(댓글이 있어 자리만 남아도).
    com.post_save('alice', {'id': a1, 'topic_id': tid, 'title': 't2', 'body': 'b'})
    assert com.post('alice', {'id': a1})['reading_day'] == '2026-11-25'
    com.comment_save('bob', {'post_id': a1, 'body': '아멘'})
    com.post_delete('alice', {'id': a1})
    st = check.status('alice')
    assert st['users'][0]['done'] == 2 and 'alice' not in st['history'][2]['done']
    assert st['users'][0]['streak'] == 2

    # 이틀 비우면 연속이 끊긴다.
    today['v'] = date(2026, 11, 30)
    assert check.status('alice')['users'][0]['streak'] == 0
    # 날짜 → 범위.
    assert check.info_iso('2026-11-25')['label'] == '창 1–4장'
    assert check.info_iso('2026-11-24') is None and check.info_iso('nope') is None
    # 시작 전에는 기록이 없다.
    today['v'] = date(2026, 11, 24)
    st = check.status('bob')
    assert st['started'] is False and st['history'] == [] and st['users'][0]['id'] == 'bob'
    com.close()

    # ---- 사이트 경로 ----
    from bibleclip.core.library import Library
    from bibleclip.server.accounts import Accounts, Throttle
    from bibleclip.server.app import create_app
    from bibleclip.server.webapi import WebHub
    acc = Accounts(DATA)
    acc.add('alice', '앨리스', 'alice-pass-1')
    today['v'] = date(2026, 11, 26)
    com = Community(os.path.join(DATA, 'r.db'), names=acc.users, today=lambda: today['v'])
    check = ReadingCheck(com, acc.users, rp.chapter_list(BOOKS), today=lambda: today['v'])
    app = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle(), com, reading_check=check)
    assert app.test_client().get('/rc/status').status_code == 401
    c = app.test_client()
    c.post('/login', data={'id': 'alice', 'password': 'alice-pass-1'})
    st = c.get('/rc/status').get_json()
    assert st['today']['day'] == 2 and st['users'][0]['name'] == '앨리스'
    assert c.get('/rc/day?date=2026-11-25').get_json()['label'] == '창 1–4장'
    assert c.get('/rc/day?date=bad').status_code == 404
    app2 = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle(), com)
    c2 = app2.test_client()
    c2.post('/login', data={'id': 'alice', 'password': 'alice-pass-1'})
    assert c2.get('/rc/status').status_code == 404
    com.close()
    print('test_readingcheck: ok')


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
