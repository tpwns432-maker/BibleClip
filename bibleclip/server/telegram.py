"""텔레그램 봇 — 커뮤니티 알림 · 1년 1독 통독 알림 (docs/TELEGRAM_PLAN.md).

웹 서비스 안의 스레드 하나로 돈다. 서버가 텔레그램에 "나한테 온 메시지 있어?"를 묻는 방식(폴링)이라
집 서버에 들어오는 문을 새로 열지 않는다. 표준 라이브러리(urllib)만 쓴다.

저장(데이터 폴더의 telegram.json, 권한 600):
    token · bot_username        봇 열쇠(사이트에서 한 번 입력 — GitHub · 설정 파일에는 없다)
    links: {아이디: {chat_id, community, reading}}   누가 어느 텔레그램 대화로 받는지 · 켜고 끄기
    offset                      텔레그램에서 어디까지 읽었는지
    sent: {"2026-11-25 08": true}   그 시각 통독 알림을 보냈는지(서버를 다시 켜도 두 번 보내지 않게)
연결 코드(10분)는 메모리에만 둔다.

알림 내용은 일부러 짧다(사용자 결정): "새 글이 있어요" + 링크. 글 제목 · 본문 · 성경 본문은 보내지 않는다.

기록: 무엇을 · 누구(아이디)에게 보냈는지/실패했는지를 서비스 기록(journalctl -u bibleclip-web)에
"telegram: …" 한 줄로 남긴다. 메시지 내용 · 봇 열쇠 · 텔레그램 대화 번호는 남기지 않는다.
"""
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from bibleclip.server import readingplan as rp

STATE_FILE = 'telegram.json'
#: 웹판 패치 내역(새것이 앞). 배포 뒤 서버가 켜지면 아직 안 알린 것을 연결된 모두에게 한 번 보낸다.
CHANGES_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'web_changes.json')
MAX_TEXT = 3800             # 텔레그램 한 메시지 한도(4096) 안쪽
CODE_TTL = 10 * 60          # 연결 코드 유효 시간
BATCH = 60                  # 상대가 연달아 쓰면 1분 안의 것을 한 번에 알린다
SLOTS = ((8, 'morning'), (19, 'evening'), (22, 'late'))   # 성경읽기 알림 시각(한국 시간)
SLOT_NAMES = {'morning': '아침', 'evening': '저녁', 'late': '밤 10시'}
SLOT_WINDOW = 30 * 60       # 그 시각부터 30분 안에만 보낸다(서버가 꺼져 있다 켜져도 몰아서 안 보냄)
API = 'https://api.telegram.org'


def _load_changes():
    try:
        with open(CHANGES_FILE, encoding='utf-8') as f:
            d = json.load(f)
        return [c for c in d if isinstance(c, dict) and c.get('id')] if isinstance(d, list) else []
    except (OSError, ValueError):
        return []


def _print_log(msg):
    print(f'telegram: {msg}', flush=True)      # systemd 가 서비스 기록(journal)으로 모은다


def _urllib_post(url, payload, timeout):
    req = urllib.request.Request(url, data=json.dumps(payload).encode('utf-8'),
                                 headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode('utf-8'))
    except urllib.error.HTTPError as e:      # 텔레그램은 오류도 JSON 으로 준다
        try:
            return json.loads(e.read().decode('utf-8'))
        except ValueError:
            return {'ok': False, 'description': f'HTTP {e.code}'}


class TelegramBot:
    def __init__(self, data_dir, names, site_url, books, start=rp.START,
                 http=_urllib_post, clock=time.time, now=None, log=_print_log, check=None, changes=None):
        """names(): {아이디: {'name': ...}} — 계정 목록. site_url: 링크 앞부분(https://….ts.net).
        books: [(책 번호, 짧은 이름, 장 수)] 성경 순서. http · clock · now 는 시험용으로 바꿔 끼운다."""
        self.path = os.path.join(data_dir, STATE_FILE)
        self.names = names
        self.site = site_url.rstrip('/')
        self.chapters = rp.chapter_list(books)
        self.start = start
        self._http = http
        self._clock = clock
        self._now = now or (lambda: datetime.now(rp.KST))
        self._log = log
        self.check = check          # ReadingCheck — 누가 그날 성경읽기 체크를 했는지(없으면 모두에게 보냄)
        self.changes = changes if changes is not None else _load_changes()
        self._poll_ok = True        # 접속 실패는 상태가 바뀔 때만 기록(실패가 이어질 때 기록이 넘치지 않게)
        self._lock = threading.RLock()
        self._codes = {}            # 코드 → (아이디, 만료 시각)
        self._pending = {}          # 받을 사람 → {'first': 시각, 'posts': set, 'comments': set, 'ids': set}
        self.state = self._load()

    # ---- 저장 ----

    def _load(self):
        try:
            with open(self.path, encoding='utf-8') as f:
                d = json.load(f)
            if isinstance(d, dict):
                d.setdefault('links', {})
                d.setdefault('sent', {})
                return d
        except (OSError, ValueError):
            pass
        return {'links': {}, 'sent': {}}

    def _save(self):
        tmp = self.path + '.tmp'
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(self.state, f, ensure_ascii=False)
        os.replace(tmp, self.path)

    # ---- 텔레그램 부르기 ----

    def _api(self, method, payload, timeout=20):
        token = self.state.get('token')
        if not token:
            return {'ok': False, 'description': 'no token'}
        try:
            return self._http(f'{API}/bot{token}/{method}', payload, timeout)
        except (OSError, ValueError) as e:
            return {'ok': False, 'description': type(e).__name__}

    def send(self, chat_id, text, to='?', what='메시지'):
        """보내고 기록한다. to = 받는 사람 아이디, what = 무슨 알림인지(기록용 — 내용은 남기지 않음)."""
        r = self._api('sendMessage', {'chat_id': chat_id, 'text': text, 'disable_web_page_preview': True})
        if r.get('ok'):
            self._log(f'보냄 {what} → {to}')
            return True
        self._log(f"실패 {what} → {to}: {r.get('description', '알 수 없음')}")
        return False

    # ---- 사이트에서 부르는 것(로그인한 사람) ----

    def status(self, uid):
        with self._lock:
            link = self.state['links'].get(uid)
            r = rp.reading_for(self.chapters, rp.today_kst(self._now()), self.start)
            return {'configured': bool(self.state.get('token')), 'bot': self.state.get('bot_username', ''),
                    'linked': bool(link), 'community': bool(link and link.get('community', True)),
                    'reading': bool(link and link.get('reading', True)),
                    'today': {'day': r['day'], 'label': r['label'], 'href': self._bible_href(r)} if r else None,
                    'start': self.start.isoformat()}

    def set_token(self, token):
        """봇 열쇠 넣기. 텔레그램에 물어 진짜인지 확인한다(getMe)."""
        token = (token or '').strip()
        if not token or len(token) > 100 or ':' not in token:
            return {'ok': False, 'error': 'invalid'}
        with self._lock:
            old = self.state.get('token')
            self.state['token'] = token
            me = self._api('getMe', {})
            if not me.get('ok'):
                if old:
                    self.state['token'] = old
                else:
                    self.state.pop('token', None)
                self._log(f"봇 열쇠 거절됨: {me.get('description', '')}")
                return {'ok': False, 'error': 'rejected'}
            self.state['bot_username'] = me['result'].get('username', '')
            if old != token:
                self.state['offset'] = 0
            self._save()
            self._log(f"봇 열쇠 설정됨 @{self.state['bot_username']}")
            return {'ok': True, 'bot': self.state['bot_username']}

    def link_url(self, uid):
        with self._lock:
            if not self.state.get('token'):
                return {'ok': False, 'error': 'no_token'}
            now = self._clock()
            self._codes = {c: v for c, v in self._codes.items() if v[1] > now}
            code = secrets.token_urlsafe(12)
            self._codes[code] = (uid, now + CODE_TTL)
            return {'ok': True, 'url': f"https://t.me/{self.state.get('bot_username', '')}?start={code}",
                    'expires_in': CODE_TTL}

    def unlink(self, uid):
        with self._lock:
            link = self.state['links'].pop(uid, None)
            self._save()
        if link:
            self._log(f'연결 끊음(사이트) {uid}')
            self.send(link['chat_id'], 'BibleClip 알림 연결을 끊었어요.', uid, '끊기 안내')
        return {'ok': True}

    def set_prefs(self, uid, prefs):
        with self._lock:
            link = self.state['links'].get(uid)
            if not link:
                return {'ok': False, 'error': 'not_linked'}
            for k in ('community', 'reading'):
                if isinstance(prefs.get(k), bool):
                    link[k] = prefs[k]
            self._save()
            self._log(f"설정 {uid}: 커뮤니티 {'켜짐' if link.get('community', True) else '꺼짐'} · "
                      f"통독 {'켜짐' if link.get('reading', True) else '꺼짐'}")
            return {'ok': True}

    # ---- 텔레그램에서 온 메시지 ----

    def handle_update(self, upd):
        msg = upd.get('message') or {}
        chat = msg.get('chat') or {}
        text = (msg.get('text') or '').strip()
        chat_id = chat.get('id')
        if not chat_id or chat.get('type') != 'private':
            return
        with self._lock:
            uid = next((u for u, l in self.state['links'].items() if l.get('chat_id') == chat_id), None)
            if text.startswith('/start'):
                code = text[6:].strip()
                hit = self._codes.pop(code, None) if code else None
                if hit and hit[1] > self._clock():
                    new_uid = hit[0]
                    for u in [u for u, l in self.state['links'].items() if l.get('chat_id') == chat_id]:
                        self.state['links'].pop(u)          # 한 대화는 한 계정에만
                    self.state['links'][new_uid] = {'chat_id': chat_id, 'community': True, 'reading': True}
                    self._save()
                    self._log(f'연결됨 {new_uid}')
                    name = self.names().get(new_uid, {}).get('name', new_uid)
                    self.send(chat_id, f'{name}님, BibleClip 알림을 연결했어요.\n'
                                       '· 커뮤니티에 새 글 · 댓글이 오면 알려 드려요.\n'
                                       '· 아침 8시 · 저녁 7시에 오늘의 통독을 알려 드려요.\n'
                                       '끄려면 사이트 홈에서, 그만 받으려면 /stop', new_uid, '연결 안내')
                    return
                self._log('연결 코드가 없거나 지남')
                self.send(chat_id, '연결 코드가 없거나 지났어요. 사이트 홈의 "텔레그램 연결"을 다시 눌러 주세요.',
                          uid or '연결 안 된 대화', '코드 안내')
                return
            if text == '/stop' and uid:
                self.state['links'].pop(uid, None)
                self._save()
                self._log(f'연결 끊음(/stop) {uid}')
                self.send(chat_id, 'BibleClip 알림을 그만 보낼게요. 다시 받으려면 사이트 홈에서 연결해 주세요.',
                          uid, '끊기 안내')
                return
            if uid:
                r = rp.reading_for(self.chapters, rp.today_kst(self._now()), self.start)
                self.send(chat_id, ('오늘의 통독: ' + r['label'] + '\n' + self._bible_href(r)) if r
                          else 'BibleClip 알림 봇이에요. 그만 받으려면 /stop', uid, '오늘의 통독 답장')
            else:
                self.send(chat_id, 'BibleClip 사이트 홈의 "텔레그램 연결"로 먼저 연결해 주세요.',
                          '연결 안 된 대화', '연결 안내')

    def poll_once(self, timeout=25):
        """텔레그램에 새 메시지를 묻는다(최대 timeout 초 기다림)."""
        r = self._api('getUpdates', {'offset': self.state.get('offset', 0), 'timeout': timeout,
                                     'allowed_updates': ['message']}, timeout=timeout + 10)
        if not r.get('ok'):
            if self._poll_ok:
                self._log(f"텔레그램 접속 실패: {r.get('description', '알 수 없음')} (다시 시도)")
            self._poll_ok = False
            return False
        if not self._poll_ok:
            self._log('텔레그램 접속 다시 됨')
        self._poll_ok = True
        for upd in r.get('result', []):
            with self._lock:
                self.state['offset'] = upd['update_id'] + 1
            try:
                self.handle_update(upd)
            except Exception as e:  # noqa: BLE001 — 메시지 하나 때문에 봇이 멈추지 않게
                self._log(f'받은 메시지 처리 실패: {type(e).__name__}')
        if r.get('result'):
            with self._lock:
                self._save()
        return True

    # ---- 커뮤니티 알림 ----

    def on_community(self, event):
        """community.py 가 부른다: {'kind': 'post'|'comment', 'author': 아이디, 'post_id': n}."""
        now = self._clock()
        to = []
        with self._lock:
            # 성경읽기 체크 글은 '통독 알림' 설정을, 나머지 글 · 댓글은 '커뮤니티 알림' 설정을 따른다.
            pref = 'reading' if event.get('reading_day') else 'community'
            for uid, link in self.state['links'].items():
                if uid == event.get('author') or not link.get(pref, True):
                    continue
                p = self._pending.setdefault(uid, {'first': now, 'posts': 0, 'comments': 0, 'ids': set(),
                                                   'reading': []})
                if event.get('reading_day'):      # 성경읽기 체크 글 → "○○님이 n일째 체크를 했어요"
                    p['reading'].append((event.get('author'), event['reading_day'], event.get('post_id')))
                else:
                    p['posts' if event.get('kind') == 'post' else 'comments'] += 1
                p['ids'].add(event.get('post_id'))
                to.append(uid)
        kind = ('성경읽기 체크' if event.get('reading_day') else
                '새 글' if event.get('kind') == 'post' else '새 댓글')
        self._log(f"대기 {kind} 글 #{event.get('post_id')} (쓴 사람 {event.get('author')}) → "
                  + (', '.join(to) + f' ({BATCH}초 뒤 묶어 보냄)' if to else '받을 사람 없음(상대가 연결 안 했거나 알림 끔)'))

    def flush_community(self, force=False):
        now = self._clock()
        with self._lock:
            due = [u for u, p in self._pending.items() if force or now - p['first'] >= BATCH]
            batches = [(u, self._pending.pop(u)) for u in due]
            links = dict(self.state['links'])
        for uid, p in batches:
            link = links.get(uid)
            if not link:
                continue
            ids = [i for i in p['ids'] if i]
            href = f'{self.site}/community#/p/{ids[0]}' if len(ids) == 1 else f'{self.site}/community'
            lines, whats = [], []
            names = self.names()
            for author, day, pid in p.get('reading', []):
                r = rp.reading_for(self.chapters, datetime.strptime(day, '%Y-%m-%d').date(), self.start)
                n = f"{r['day']}일째 " if r else ''
                who = names.get(author, {}).get('name', author)
                lines.append(f'✅ {who}님이 {n}성경읽기 체크를 했어요')
                whats.append(f'성경읽기 체크 {author} {day}')
            if p['posts'] or p['comments']:
                if p['posts'] == 1 and not p['comments'] and not lines:
                    lines.append('📖 BibleClip · 커뮤니티에 새 글이 있어요')
                elif p['comments'] == 1 and not p['posts'] and not lines:
                    lines.append('💬 BibleClip · 새 댓글이 있어요')
                else:
                    bits = ([f"새 글 {p['posts']}"] if p['posts'] else []) + \
                           ([f"새 댓글 {p['comments']}"] if p['comments'] else [])
                    lines.append('📖 BibleClip · ' + ' · '.join(bits))
                whats.append(' · '.join(([f"새 글 {p['posts']}"] if p['posts'] else []) +
                                        ([f"새 댓글 {p['comments']}"] if p['comments'] else [])))
            what = '커뮤니티(' + ' · '.join(whats) + ', 글 ' + ', '.join(f'#{i}' for i in sorted(ids)) + ')'
            self.send(link['chat_id'], '\n'.join(lines) + f'\n{href}', uid, what)

    # ---- 통독 알림 ----

    def _bible_href(self, r):
        book, chapter = r['first']
        return f'{self.site}/bible#go={book}.{chapter}'

    def _check_href(self, day):
        """그날 성경읽기 체크 글쓰기(커뮤니티 '성경읽기 체크', 범위가 미리 달림)."""
        return f'{self.site}/community#/new?reading={day.isoformat()}'

    def tick_reading(self):
        now = self._now().astimezone(rp.KST)
        for hour, kind in SLOTS:
            slot = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if not 0 <= (now - slot).total_seconds() < SLOT_WINDOW:
                continue
            key = slot.strftime('%Y-%m-%d %H')
            with self._lock:
                if self.state['sent'].get(key):
                    continue
                self.state['sent'] = {k: v for k, v in self.state['sent'].items() if k >= (now.date().isoformat())}
                self.state['sent'][key] = True
                self._save()
                links = dict(self.state['links'])
            today = now.date()
            r = rp.reading_for(self.chapters, today, self.start)
            if not r:
                continue
            to = [u for u, link in links.items() if link.get('reading', True)]
            done = self.check.done_on(today) if self.check else {}
            skipped = []
            if kind != 'morning':           # 저녁 · 밤 10시: 이미 체크한 사람에겐 안 보낸다
                skipped = [u for u in to if u in done]
                to = [u for u in to if u not in done]
            # 아침: 어제 체크가 비었으면 한 줄(자정이 지나면 그날은 '안 읽음').
            yesterday = today - timedelta(days=1)
            ymiss = set()
            if kind == 'morning' and self.check and yesterday >= self.start:
                ydone = self.check.done_on(yesterday)
                ymiss = {u for u in to if u not in ydone}
            what = f"성경읽기 {SLOT_NAMES[kind]}({r['day']}일째 {r['label']})"
            self._log(f'{what} 시작 — 받을 사람 {len(to)}명'
                      + (f" (이미 체크해서 뺌: {', '.join(skipped)})" if skipped else '')
                      + (f" (어제 체크 비어 있음: {', '.join(sorted(ymiss))})" if ymiss else ''))
            check = f'✍️ 성경읽기 체크: {self._check_href(today)}'
            for uid in to:
                if kind == 'morning':
                    text = f"☀️ 오늘의 성경읽기 ({r['day']}일째)\n{r['label']}\n📖 {self._bible_href(r)}\n{check}"
                    if uid in ymiss:
                        yr = rp.reading_for(self.chapters, yesterday, self.start)
                        text += (f"\n\n어제({yr['day']}일째 {yr['label']}) 성경읽기 체크가 비어 있어요."
                                 f"\n✍️ {self._check_href(yesterday)}")
                elif kind == 'evening':
                    text = f"🌙 오늘의 성경읽기 하셨나요? ({r['day']}일째 {r['label']})\n{check}"
                else:
                    text = f"🔔 아직 오늘 성경읽기 체크를 안 하셨어요 ({r['day']}일째 {r['label']})\n{check}"
                self.send(links[uid]['chat_id'], text, uid, what)

    # ---- 패치 내역 알림 ----

    def announce_changes(self):
        """아직 안 알린 패치 내역을 연결된 모두에게 한 번(알림 켜고 끄기와 상관없이). 연결된 사람이
        없거나 열쇠가 없으면 기다린다(나중에 연결되면 그때 보냄)."""
        with self._lock:
            done = set(self.state.get('announced', []))
            new = [c for c in self.changes if c['id'] not in done]
            links = dict(self.state['links'])
            if not new or not links or not self.state.get('token'):
                return
            self.state['announced'] = sorted(done | {c['id'] for c in new})
            self._save()
        parts = ['📢 BibleClip 업데이트']
        for c in new:                       # 새것부터
            parts.append(f"\n[{c.get('title', '')}] {c.get('date', '')}".rstrip())
            parts.extend('· ' + n for n in c.get('notes', []))
        text = '\n'.join(parts)
        if len(text) > MAX_TEXT:
            text = text[:MAX_TEXT - 1] + '…'
        what = '패치 안내(' + ', '.join(c['id'] for c in new) + ')'
        for uid, link in links.items():
            self.send(link['chat_id'], f'{text}\n\n{self.site}/', uid, what)

    # ---- 스레드 ----

    def run_forever(self, stop=None):
        backoff = 5
        while not (stop and stop.is_set()):
            try:
                self.announce_changes()
                self.tick_reading()
                self.flush_community()
                if self.state.get('token'):
                    ok = self.poll_once(timeout=20)
                    if not ok:
                        time.sleep(backoff)
                        backoff = min(backoff * 2, 300)
                    else:
                        backoff = 5
                else:
                    time.sleep(10)
            except Exception as e:  # noqa: BLE001 — 봇이 죽어도 사이트는 계속 돈다
                self._log(f'봇 오류: {type(e).__name__} — 30초 뒤 다시')
                time.sleep(30)

    def start_thread(self):
        self._log(f"봇 시작 — 열쇠 {'있음 @' + self.state.get('bot_username', '') if self.state.get('token') else '없음'}, "
                  f"연결 {len(self.state['links'])}명({', '.join(self.state['links']) or '-'})")
        t = threading.Thread(target=self.run_forever, name='telegram', daemon=True)
        t.start()
        return t
