"""텔레그램 봇 테스트 (bibleclip/server/telegram.py) — 가짜 텔레그램으로, 실제로 보내지 않는다.

    python -X utf8 tests/test_telegram.py
"""
import os
import shutil
import sys
import tempfile
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
DATA = tempfile.mkdtemp(prefix='bibleclip-tg-')
os.environ['BIBLECLIP_DATA_DIR'] = DATA

from bibleclip.server import readingplan as rp  # noqa: E402
from bibleclip.server.telegram import BATCH, CODE_TTL, TelegramBot  # noqa: E402

BOOKS = [(10, '창', 50), (20, '출', 40)] + [(30 + i, f'b{i}', 30) for i in range(40)]
NAMES = {'alice': {'name': '앨리스'}, 'bob': {'name': '밥'}}
GOOD = '123456:GOOD-token'
SITE = 'https://bc.tail.ts.net'


class FakeTelegram:
    def __init__(self):
        self.sent, self.updates, self.calls = [], [], []

    def __call__(self, url, payload, timeout):
        method = url.rsplit('/', 1)[1]
        self.calls.append(method)
        if '/bot' + GOOD + '/' not in url:
            return {'ok': False, 'description': 'Unauthorized'}
        if method == 'getMe':
            return {'ok': True, 'result': {'username': 'bc_test_bot'}}
        if method == 'sendMessage':
            self.sent.append((payload['chat_id'], payload['text']))
            return {'ok': True}
        if method == 'getUpdates':
            ups, self.updates = self.updates, []
            return {'ok': True, 'result': ups}
        return {'ok': False}

    def take(self):
        s, self.sent = self.sent, []
        return s


class Clock:
    def __init__(self):
        self.t = 1_000_000.0

    def __call__(self):
        return self.t


def msg(uid_chat, text, kind='private', n=[0]):
    n[0] += 1
    return {'update_id': n[0], 'message': {'chat': {'id': uid_chat, 'type': kind}, 'text': text}}


def run():
    tg, clock = FakeTelegram(), Clock()
    now = {'v': datetime(2026, 11, 25, 7, 0, tzinfo=rp.KST)}
    LOG = []
    bot = TelegramBot(DATA, lambda: NAMES, SITE + '/', BOOKS, http=tg, clock=clock, now=lambda: now['v'],
                      log=LOG.append)

    # ---- 봇 열쇠 ----
    s = bot.status('alice')
    assert s['configured'] is False and s['linked'] is False
    assert s['today']['day'] == 1 and s['today']['label'] == '창 1–4장', s['today']
    assert s['today']['href'] == SITE + '/bible#go=10.1'
    for bad in ('', 'no-colon', 'x' * 101):
        assert bot.set_token(bad) == {'ok': False, 'error': 'invalid'}
    assert bot.set_token('999:WRONG') == {'ok': False, 'error': 'rejected'}
    assert 'token' not in bot.state
    assert bot.link_url('alice')['ok'] is False                 # 열쇠 없으면 연결 못 함
    assert bot.set_token(' ' + GOOD + ' ') == {'ok': True, 'bot': 'bc_test_bot'}
    assert bot.status('alice')['configured'] and bot.status('alice')['bot'] == 'bc_test_bot'
    assert GOOD not in str(bot.status('alice'))                 # 열쇠는 화면에 안 나간다
    if os.name == 'posix':
        assert oct(os.stat(os.path.join(DATA, 'telegram.json')).st_mode & 0o777) == '0o600'

    # ---- 연결 ----
    url = bot.link_url('alice')['url']
    assert url.startswith('https://t.me/bc_test_bot?start=')
    code = url.split('start=')[1]
    tg.updates = [msg(-100, '/start ' + code, kind='group')]   # 단체방은 무시
    bot.poll_once()
    assert bot.status('alice')['linked'] is False and tg.take() == []
    tg.updates = [msg(111, '/start ' + code)]
    bot.poll_once()
    assert bot.status('alice')['linked'] and bot.state['links']['alice']['chat_id'] == 111
    assert '앨리스님' in tg.take()[0][1]
    tg.updates = [msg(222, '/start ' + code)]                  # 한 번 쓴 코드는 다시 못 씀
    bot.poll_once()
    assert 'bob' not in bot.state['links'] and '지났어요' in tg.take()[0][1]
    code_b = bot.link_url('bob')['url'].split('start=')[1]
    clock.t += CODE_TTL + 1                                     # 10분 지나면 못 씀
    tg.updates = [msg(222, '/start ' + code_b)]
    bot.poll_once()
    assert 'bob' not in bot.state['links']
    tg.take()
    code_b = bot.link_url('bob')['url'].split('start=')[1]
    tg.updates = [msg(222, '/start ' + code_b), msg(333, '안녕')]
    bot.poll_once()
    assert bot.state['links']['bob']['chat_id'] == 222
    out = tg.take()
    assert any('먼저 연결' in t for c, t in out if c == 333)    # 모르는 대화엔 정보 없이 안내만
    assert bot.state['offset'] > 0

    # ---- 커뮤니티 알림: 상대에게만, 1분 묶어서, 제목 없이 ----
    bot.on_community({'kind': 'post', 'author': 'alice', 'post_id': 7})
    bot.flush_community()
    assert tg.take() == []                                      # 아직 1분 안 됨
    clock.t += BATCH
    bot.flush_community()
    assert tg.take() == [(222, '📖 BibleClip · 커뮤니티에 새 글이 있어요\n' + SITE + '/community#/p/7')]
    bot.on_community({'kind': 'comment', 'author': 'alice', 'post_id': 7})
    bot.on_community({'kind': 'comment', 'author': 'alice', 'post_id': 7})
    bot.on_community({'kind': 'post', 'author': 'alice', 'post_id': 8})
    bot.on_community({'kind': 'comment', 'author': 'bob', 'post_id': 8})   # 밥 → 앨리스
    clock.t += BATCH
    bot.flush_community()
    out = dict(tg.take())
    assert out[222] == '📖 BibleClip · 새 글 1 · 새 댓글 2\n' + SITE + '/community'
    assert out[111] == '💬 BibleClip · 새 댓글이 있어요\n' + SITE + '/community#/p/8'
    assert bot.set_prefs('bob', {'community': False})['ok']
    bot.on_community({'kind': 'post', 'author': 'alice', 'post_id': 9})
    bot.flush_community(force=True)
    assert tg.take() == []
    assert bot.set_prefs('carol', {'community': True}) == {'ok': False, 'error': 'not_linked'}

    # ---- 기록: 누구에게 무엇을 보냈는지, 내용 · 열쇠 · 대화 번호는 없이 ----
    joined = '\n'.join(LOG)
    assert '봇 열쇠 설정됨 @bc_test_bot' in joined and '봇 열쇠 거절됨' in joined
    assert '연결됨 alice' in joined and '연결됨 bob' in joined
    assert '대기 새 글 글 #7 (쓴 사람 alice) → bob (60초 뒤 묶어 보냄)' in joined
    assert '보냄 커뮤니티(새 글 1, 글 #7) → bob' in joined
    assert '보냄 커뮤니티(새 글 1 · 새 댓글 2, 글 #7, #8) → bob' in joined
    assert '대기 새 글 글 #9 (쓴 사람 alice) → 받을 사람 없음(상대가 연결 안 했거나 알림 끔)' in joined
    assert '설정 bob: 커뮤니티 꺼짐 · 통독 켜짐' in joined
    assert GOOD not in joined and '111' not in joined and '222' not in joined
    assert '커뮤니티에 새 글이 있어요' not in joined                       # 메시지 내용은 안 남김
    del LOG[:]

    # ---- 성경읽기 알림: 한국 시간 8 · 19 · 22시, 30분 안에만, 한 번씩, 체크한 사람은 저녁부터 뺌 ----
    class FakeCheck:                    # 그날 성경읽기 체크한 사람(ReadingCheck.done_on 흉내)
        done = {}

        def done_on(self, day):
            return self.done.get(day.isoformat(), {})
    bot.check = FakeCheck()
    CHK = SITE + '/community#/new?reading='
    now['v'] = datetime(2026, 11, 25, 7, 59, tzinfo=rp.KST)
    bot.tick_reading()
    assert tg.take() == []
    now['v'] = datetime(2026, 11, 24, 23, 5, tzinfo=rp.timezone.utc)   # = 한국 25일 08:05
    bot.tick_reading()
    out = tg.take()
    assert sorted(c for c, _ in out) == [111, 222]
    assert out[0][1] == ('☀️ 오늘의 성경읽기 (1일째)\n창 1–4장\n📖 ' + SITE + '/bible#go=10.1\n'
                         '✍️ 성경읽기 체크: ' + CHK + '2026-11-25'), out[0][1]
    assert '성경읽기 아침(1일째 창 1–4장) 시작 — 받을 사람 2명' in LOG
    assert '보냄 성경읽기 아침(1일째 창 1–4장) → alice' in LOG and '보냄 성경읽기 아침(1일째 창 1–4장) → bob' in LOG
    bot.tick_reading()
    assert tg.take() == []                                      # 같은 시각엔 한 번만
    # 저녁 7시: 이미 체크한 앨리스는 빼고 밥에게만.
    FakeCheck.done = {'2026-11-25': {'alice': 5}}
    now['v'] = datetime(2026, 11, 25, 19, 10, tzinfo=rp.KST)
    bot.tick_reading()
    assert tg.take() == [(222, '🌙 오늘의 성경읽기 하셨나요? (1일째 창 1–4장)\n✍️ 성경읽기 체크: ' + CHK + '2026-11-25')]
    assert any('이미 체크해서 뺌: alice' in m for m in LOG)
    # 밤 10시: 아직 안 한 밥에게만 한 번 더.
    now['v'] = datetime(2026, 11, 25, 22, 1, tzinfo=rp.KST)
    bot.tick_reading()
    assert tg.take() == [(222, '🔔 아직 오늘 성경읽기 체크를 안 하셨어요 (1일째 창 1–4장)\n✍️ 성경읽기 체크: '
                          + CHK + '2026-11-25')]
    # 다음 날 아침: 어제 체크가 빈 밥에게만 한 줄 더.
    now['v'] = datetime(2026, 11, 26, 8, 0, tzinfo=rp.KST)
    bot.tick_reading()
    out = dict(tg.take())
    assert '어제' not in out[111]
    assert out[222].endswith('\n\n어제(1일째 창 1–4장) 성경읽기 체크가 비어 있어요.\n✍️ ' + CHK + '2026-11-25'), out[222]
    assert out[222].startswith('☀️ 오늘의 성경읽기 (2일째)')
    assert any('어제 체크 비어 있음: bob' in m for m in LOG)
    # 통독 알림을 끈 사람은 아무것도 안 받는다.
    assert bot.set_prefs('alice', {'reading': False})['ok']
    now['v'] = datetime(2026, 11, 26, 19, 0, tzinfo=rp.KST)
    bot.tick_reading()
    assert [c for c, _ in tg.take()] == [222]
    now['v'] = datetime(2026, 11, 27, 8, 40, tzinfo=rp.KST)       # 30분 지나 켜짐 → 건너뜀
    bot.tick_reading()
    assert tg.take() == []
    now['v'] = datetime(2026, 11, 24, 8, 0, tzinfo=rp.KST)        # 시작 전날
    bot2 = TelegramBot(DATA, lambda: NAMES, SITE, BOOKS, http=tg, clock=clock, now=lambda: now['v'])
    bot2.tick_reading()
    assert tg.take() == []

    # 다시 켜도(새 봇) 연결 · 보낸 기록 · 열쇠가 남는다.
    assert bot2.state['links']['bob']['chat_id'] == 222 and bot2.state['token'] == GOOD
    now['v'] = datetime(2026, 11, 26, 19, 15, tzinfo=rp.KST)
    bot2.tick_reading()
    assert tg.take() == []                                      # 19시는 이미 보냄

    # 상대의 성경읽기 체크 글 → 이름과 몇째 날로 알림(일반 '새 글' 알림 대신).
    bot.on_community({'kind': 'post', 'author': 'alice', 'post_id': 12, 'reading_day': '2026-11-25'})
    bot.flush_community(force=True)
    assert tg.take() == [(222, '✅ 앨리스님이 1일째 성경읽기 체크를 했어요\n' + SITE + '/community#/p/12')]
    assert any('대기 성경읽기 체크 글 #12' in m for m in LOG)
    assert bot.set_prefs('bob', {'community': True})['ok']      # (위에서 껐던 커뮤니티 알림을 다시 켬)
    bot.on_community({'kind': 'post', 'author': 'alice', 'post_id': 13, 'reading_day': '2026-11-26'})
    bot.on_community({'kind': 'comment', 'author': 'alice', 'post_id': 7})
    bot.flush_community(force=True)
    assert tg.take() == [(222, '✅ 앨리스님이 2일째 성경읽기 체크를 했어요\n📖 BibleClip · 새 댓글 1\n'
                          + SITE + '/community')]

    # ---- 패치 내역: 연결된 모두에게 한 번, 다시 켜도 또 안 보냄, 새 내역만 ----
    CH = [{'id': 'c2', 'date': '2026-11-25', 'title': '둘째', 'notes': ['나', '다']},
          {'id': 'c1', 'date': '2026-11-24', 'title': '첫째', 'notes': ['가']}]
    assert bot.set_prefs('bob', {'reading': False, 'community': False})['ok']     # 알림 꺼도 패치 안내는 감
    bot.changes = CH
    bot.announce_changes()
    out = tg.take()
    assert sorted(c for c, _ in out) == [111, 222]   # 연결된 모두에게(알림을 끈 밥도)
    assert out[0][1] == ('📢 BibleClip 업데이트\n\n[둘째] 2026-11-25\n· 나\n· 다\n\n[첫째] 2026-11-24\n· 가'
                         '\n\n' + SITE + '/'), out[0][1]
    assert any('패치 안내(c2, c1)' in m for m in LOG)
    bot.announce_changes()
    assert tg.take() == []
    bot3 = TelegramBot(DATA, lambda: NAMES, SITE, BOOKS, http=tg, clock=clock, changes=CH + [], log=LOG.append)
    bot3.announce_changes()
    assert tg.take() == []                       # 다시 켜도 같은 내역은 안 보냄
    bot3.changes = [{'id': 'c3', 'title': '셋째', 'notes': ['라']}] + CH
    bot3.announce_changes()
    assert sorted(tg.take()) == [(c, '📢 BibleClip 업데이트\n\n[셋째]\n· 라\n\n' + SITE + '/') for c in (111, 222)]
    from bibleclip.server.telegram import _load_changes
    real = _load_changes()
    assert real and all(c.get('id') and c.get('title') and c.get('notes') for c in real)   # 실제 내역 파일

    # 실패도 이유와 함께 남기고, 접속 실패는 상태가 바뀔 때만.
    del LOG[:]
    bad = TelegramBot(DATA, lambda: NAMES, SITE, BOOKS, http=lambda u, p, t: {'ok': False, 'description': 'Forbidden: bot was blocked by the user'},
                      clock=clock, now=lambda: now['v'], log=LOG.append)
    assert bad.send(222, 'x', 'bob', '시험') is False
    assert LOG[-1] == '실패 시험 → bob: Forbidden: bot was blocked by the user'
    bad.poll_once(); bad.poll_once()
    assert sum('텔레그램 접속 실패' in m for m in LOG) == 1

    # ---- /stop · 연결 끊기 ----
    tg.updates = [msg(222, '/stop')]
    bot.poll_once()
    assert 'bob' not in bot.state['links'] and '그만' in tg.take()[0][1]
    bot.unlink('alice')
    assert bot.state['links'] == {} and '끊었어요' in tg.take()[0][1]

    # ---- 사이트 경로 ----
    from bibleclip.core.library import Library
    from bibleclip.server.accounts import Accounts, Throttle
    from bibleclip.server.app import create_app
    from bibleclip.server.webapi import WebHub
    acc = Accounts(DATA)
    acc.add('alice', '앨리스', 'alice-pass-1')
    app = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle(), telegram=bot)
    H = {'X-BibleClip': '1'}
    anon = app.test_client()
    assert anon.get('/tg/status').status_code == 401
    c = app.test_client()
    c.post('/login', data={'id': 'alice', 'password': 'alice-pass-1'})
    st = c.get('/tg/status').get_json()
    assert st['configured'] and not st['linked'] and GOOD not in str(st)
    assert c.post('/tg/link', json={}).status_code == 403                    # 머리글 없음
    assert c.post('/tg/link', json={}, headers=H).get_json()['url'].startswith('https://t.me/')
    assert c.post('/tg/token', json={'token': 'bad'}, headers=H).get_json()['ok'] is False
    assert c.post('/tg/prefs', json={'reading': True}, headers=H).get_json()['ok'] is False
    app2 = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle())
    c2 = app2.test_client()
    c2.post('/login', data={'id': 'alice', 'password': 'alice-pass-1'})
    assert c2.get('/tg/status').status_code == 404                           # 봇 없는 서버

    # ---- 커뮤니티가 새 글 · 댓글을 봇에 알린다(고치기는 안 알림) ----
    from bibleclip.server.community import Community
    events = []
    com = Community(os.path.join(DATA, 'c.db'), names=lambda: NAMES, on_event=events.append)
    tid = com.topics('alice')[0]['id']
    pid = com.post_save('alice', {'topic_id': tid, 'title': 't', 'body': 'b'})['id']
    com.post_save('alice', {'id': pid, 'topic_id': tid, 'title': 't2', 'body': 'b'})
    cid = com.comment_save('bob', {'post_id': pid, 'body': 'c'})['id']
    com.comment_save('bob', {'id': cid, 'body': 'c2'})
    assert events == [{'kind': 'post', 'author': 'alice', 'post_id': pid},
                      {'kind': 'comment', 'author': 'bob', 'post_id': pid}], events
    com.close()
    print('test_telegram: ok')


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
