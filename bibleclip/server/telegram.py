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
"""
import json
import os
import secrets
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime

from bibleclip.server import readingplan as rp

STATE_FILE = 'telegram.json'
CODE_TTL = 10 * 60          # 연결 코드 유효 시간
BATCH = 60                  # 상대가 연달아 쓰면 1분 안의 것을 한 번에 알린다
SLOTS = ((8, 'morning'), (19, 'evening'))   # 통독 알림 시각(한국 시간)
SLOT_WINDOW = 30 * 60       # 그 시각부터 30분 안에만 보낸다(서버가 꺼져 있다 켜져도 몰아서 안 보냄)
API = 'https://api.telegram.org'


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
                 http=_urllib_post, clock=time.time, now=None):
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

    def send(self, chat_id, text):
        return self._api('sendMessage', {'chat_id': chat_id, 'text': text,
                                         'disable_web_page_preview': True}).get('ok', False)

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
                return {'ok': False, 'error': 'rejected'}
            self.state['bot_username'] = me['result'].get('username', '')
            if old != token:
                self.state['offset'] = 0
            self._save()
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
            self.send(link['chat_id'], 'BibleClip 알림 연결을 끊었어요.')
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
                    name = self.names().get(new_uid, {}).get('name', new_uid)
                    self.send(chat_id, f'{name}님, BibleClip 알림을 연결했어요.\n'
                                       '· 커뮤니티에 새 글 · 댓글이 오면 알려 드려요.\n'
                                       '· 아침 8시 · 저녁 7시에 오늘의 통독을 알려 드려요.\n'
                                       '끄려면 사이트 홈에서, 그만 받으려면 /stop')
                    return
                self.send(chat_id, '연결 코드가 없거나 지났어요. 사이트 홈의 "텔레그램 연결"을 다시 눌러 주세요.')
                return
            if text == '/stop' and uid:
                self.state['links'].pop(uid, None)
                self._save()
                self.send(chat_id, 'BibleClip 알림을 그만 보낼게요. 다시 받으려면 사이트 홈에서 연결해 주세요.')
                return
            if uid:
                r = rp.reading_for(self.chapters, rp.today_kst(self._now()), self.start)
                self.send(chat_id, ('오늘의 통독: ' + r['label'] + '\n' + self._bible_href(r)) if r
                          else 'BibleClip 알림 봇이에요. 그만 받으려면 /stop')
            else:
                self.send(chat_id, 'BibleClip 사이트 홈의 "텔레그램 연결"로 먼저 연결해 주세요.')

    def poll_once(self, timeout=25):
        """텔레그램에 새 메시지를 묻는다(최대 timeout 초 기다림)."""
        r = self._api('getUpdates', {'offset': self.state.get('offset', 0), 'timeout': timeout,
                                     'allowed_updates': ['message']}, timeout=timeout + 10)
        if not r.get('ok'):
            return False
        for upd in r.get('result', []):
            with self._lock:
                self.state['offset'] = upd['update_id'] + 1
            try:
                self.handle_update(upd)
            except Exception:       # noqa: BLE001 — 메시지 하나 때문에 봇이 멈추지 않게
                pass
        if r.get('result'):
            with self._lock:
                self._save()
        return True

    # ---- 커뮤니티 알림 ----

    def on_community(self, event):
        """community.py 가 부른다: {'kind': 'post'|'comment', 'author': 아이디, 'post_id': n}."""
        now = self._clock()
        with self._lock:
            for uid, link in self.state['links'].items():
                if uid == event.get('author') or not link.get('community', True):
                    continue
                p = self._pending.setdefault(uid, {'first': now, 'posts': 0, 'comments': 0, 'ids': set()})
                p['posts' if event.get('kind') == 'post' else 'comments'] += 1
                p['ids'].add(event.get('post_id'))

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
            if p['posts'] and not p['comments'] and p['posts'] == 1:
                text = '📖 BibleClip · 커뮤니티에 새 글이 있어요'
            elif p['comments'] and not p['posts'] and p['comments'] == 1:
                text = '💬 BibleClip · 새 댓글이 있어요'
            else:
                bits = ([f"새 글 {p['posts']}"] if p['posts'] else []) + \
                       ([f"새 댓글 {p['comments']}"] if p['comments'] else [])
                text = '📖 BibleClip · ' + ' · '.join(bits)
            self.send(link['chat_id'], f'{text}\n{href}')

    # ---- 통독 알림 ----

    def _bible_href(self, r):
        book, chapter = r['first']
        return f'{self.site}/bible#go={book}.{chapter}'

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
            r = rp.reading_for(self.chapters, now.date(), self.start)
            if not r:
                continue
            head = (f"☀️ 오늘의 통독 ({r['day']}일째)" if kind == 'morning'
                    else '🌙 오늘의 통독 다 읽으셨나요?')
            text = f"{head}\n{r['label']}\n{self._bible_href(r)}"
            for link in links.values():
                if link.get('reading', True):
                    self.send(link['chat_id'], text)

    # ---- 스레드 ----

    def run_forever(self, stop=None):
        backoff = 5
        while not (stop and stop.is_set()):
            try:
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
            except Exception:       # noqa: BLE001 — 봇이 죽어도 사이트는 계속 돈다
                time.sleep(30)

    def start_thread(self):
        t = threading.Thread(target=self.run_forever, name='telegram', daemon=True)
        t.start()
        return t
