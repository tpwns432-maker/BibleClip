"""웹판 계정 — 두 사람만 쓴다(docs/WEB_PLAN.md "계정 · 보안"). 회원가입은 없다.

<데이터 폴더>/users.json
    {"users": {"<아이디>": {"name": "보이는 이름", "hash": "scrypt$…", "sv": 1}}}

- 비밀번호는 원문을 저장하지 않는다. scrypt(일부러 느리고 메모리를 많이 쓰는 해시)로 바꾼 값만.
- sv(세션 판) 는 비밀번호를 바꾸면 1 오른다 → 예전 로그인(쿠키)이 모두 풀린다.
- 계정은 서버에서 명령으로 만든다: python -m bibleclip.server.accounts --data <폴더> add <아이디>
"""
import argparse
import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import sys
import threading
import time

USERS_FILE = 'users.json'
SECRET_FILE = 'secret_key'
ID_RE = re.compile(r'^[a-z0-9][a-z0-9_-]{1,31}$')
MIN_PASSWORD = 8
NAME_MAX = 30
_N, _R, _P = 2 ** 14, 8, 1        # scrypt 비용: 한 번에 약 16MB · 수십 ms


def hash_password(password):
    salt = secrets.token_bytes(16)
    h = hashlib.scrypt(password.encode('utf-8'), salt=salt, n=_N, r=_R, p=_P, dklen=32)
    return f'scrypt${_N}${_R}${_P}${salt.hex()}${h.hex()}'


def check_password(password, stored):
    try:
        algo, n, r, p, salt, h = str(stored).split('$')
        if algo != 'scrypt':
            return False
        want = bytes.fromhex(h)
        got = hashlib.scrypt(str(password).encode('utf-8'), salt=bytes.fromhex(salt),
                             n=int(n), r=int(r), p=int(p), dklen=len(want))
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(got, want)


_DUMMY = hash_password(secrets.token_hex(8))   # 없는 아이디도 같은 시간이 걸리게


def _write_private(path, text):
    """남이 못 읽게(리눅스 권한 600) 통째로 바꿔 쓴다 — 쓰다 끊겨도 반쪽 파일이 남지 않는다."""
    tmp = path + '.tmp'
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(text)
    os.replace(tmp, path)


def secret_key(data_dir):
    """쿠키 서명 열쇠. 처음 한 번 만들어 데이터 폴더에 둔다(저장소에는 절대 없음)."""
    path = os.path.join(data_dir, SECRET_FILE)
    try:
        with open(path, encoding='utf-8') as f:
            key = f.read().strip()
        if len(key) >= 32:
            return key
    except OSError:
        pass
    key = secrets.token_hex(32)
    _write_private(path, key)
    return key


class Accounts:
    """users.json 읽기 · 쓰기. 서버가 켜져 있는 동안 명령으로 바꿔도 다음 요청부터 반영된다."""

    def __init__(self, data_dir):
        self.path = os.path.join(data_dir, USERS_FILE)
        self._lock = threading.Lock()
        self._mtime = None
        self._users = {}

    def _refresh(self):
        try:
            m = os.path.getmtime(self.path)
        except OSError:
            self._users, self._mtime = {}, None
            return
        if m == self._mtime:
            return
        try:
            with open(self.path, encoding='utf-8') as f:
                d = json.load(f)
            users = d.get('users') if isinstance(d, dict) else None
            self._users = {k: v for k, v in (users or {}).items()
                           if ID_RE.match(k) and isinstance(v, dict) and v.get('hash')}
        except (OSError, ValueError):
            self._users = {}
        self._mtime = m

    def _save(self):
        _write_private(self.path, json.dumps({'users': self._users}, ensure_ascii=False, indent=2))
        self._mtime = None

    def users(self):
        with self._lock:
            self._refresh()
            return {k: {'name': v.get('name') or k, 'sv': int(v.get('sv') or 1)}
                    for k, v in self._users.items()}

    def get(self, uid):
        return self.users().get(uid)

    def verify(self, uid, password):
        """맞으면 {'name', 'sv'}, 틀리면 None."""
        with self._lock:
            self._refresh()
            u = self._users.get(uid)
        if not check_password(password, u['hash'] if u else _DUMMY) or not u:
            return None
        return {'name': u.get('name') or uid, 'sv': int(u.get('sv') or 1)}

    def add(self, uid, name, password):
        if not ID_RE.match(uid or ''):
            raise ValueError('아이디는 영문 소문자 · 숫자 · _ · - 로 2~32자')
        if len(password) < MIN_PASSWORD:
            raise ValueError(f'비밀번호는 {MIN_PASSWORD}자 이상')
        with self._lock:
            self._refresh()
            if uid in self._users:
                raise ValueError('이미 있는 아이디')
            self._users[uid] = {'name': name or uid, 'hash': hash_password(password), 'sv': 1}
            self._save()

    def set_name(self, uid, name):
        """화면에 보이는 이름 바꾸기(아이디는 그대로). 앞뒤 공백 · 줄바꿈 등 보이지 않는 글자는 뺀다."""
        name = ''.join(ch for ch in ' '.join(str(name or '').split()) if ch.isprintable())
        if not name or len(name) > NAME_MAX:
            raise ValueError(f'이름은 1~{NAME_MAX}자')
        with self._lock:
            self._refresh()
            u = self._users.get(uid)
            if not u:
                raise ValueError('없는 아이디')
            u['name'] = name
            self._save()
        return name

    def set_password(self, uid, password):
        if len(password) < MIN_PASSWORD:
            raise ValueError(f'비밀번호는 {MIN_PASSWORD}자 이상')
        with self._lock:
            self._refresh()
            u = self._users.get(uid)
            if not u:
                raise ValueError('없는 아이디')
            u['hash'] = hash_password(password)
            u['sv'] = int(u.get('sv') or 1) + 1     # 예전 로그인 모두 풀기
            self._save()

    def remove(self, uid):
        with self._lock:
            self._refresh()
            if self._users.pop(uid, None) is None:
                raise ValueError('없는 아이디')
            self._save()


class Throttle:
    """로그인 실패가 잦으면 잠시 막는다(남이 비밀번호를 하나씩 대입해 보는 것을 늦춘다).
    같은 아이디 또는 같은 주소에서 15분 안에 5번 틀리면 15분 동안 거절."""

    LIMIT, WINDOW = 5, 15 * 60

    def __init__(self, clock=time.monotonic):
        self._fails = {}
        self._clock = clock
        self._lock = threading.Lock()

    def _recent(self, key, now):
        xs = [t for t in self._fails.get(key, ()) if now - t < self.WINDOW]
        self._fails[key] = xs
        return xs

    def blocked(self, *keys):
        now = self._clock()
        with self._lock:
            return any(len(self._recent(k, now)) >= self.LIMIT for k in keys)

    def fail(self, *keys):
        now = self._clock()
        with self._lock:
            for k in keys:
                self._recent(k, now).append(now)

    def clear(self, *keys):
        with self._lock:
            for k in keys:
                self._fails.pop(k, None)


# ---- 명령: 계정 만들기 · 비밀번호 바꾸기 · 지우기 · 목록 ----

def _ask_password():
    while True:
        a = getpass.getpass('비밀번호(화면에 안 보임): ')
        if len(a) < MIN_PASSWORD:
            print(f'{MIN_PASSWORD}자 이상으로 해 주세요.')
            continue
        if getpass.getpass('한 번 더: ') != a:
            print('두 번 입력한 값이 다릅니다.')
            continue
        return a


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m bibleclip.server.accounts',
                                description='BibleClip 웹판 계정 관리')
    p.add_argument('--data', required=True, help='서버의 데이터 폴더')
    sub = p.add_subparsers(dest='cmd', required=True)
    a = sub.add_parser('add', help='계정 만들기')
    a.add_argument('id', help='아이디(영문 소문자 · 숫자)')
    a.add_argument('--name', help='화면에 보일 이름(예: 세준)')
    w = sub.add_parser('passwd', help='비밀번호 바꾸기(예전 로그인은 모두 풀림)')
    w.add_argument('id')
    r = sub.add_parser('remove', help='계정 지우기(그 사람의 글 폴더는 남긴다)')
    r.add_argument('id')
    sub.add_parser('list', help='계정 목록')
    args = p.parse_args(argv)

    os.makedirs(args.data, exist_ok=True)
    acc = Accounts(args.data)
    try:
        return _run(args, acc)
    except (EOFError, KeyboardInterrupt):
        print('\n입력이 끊겨 그만둡니다.', file=sys.stderr)
        return 1


def _run(args, acc):
    try:
        if args.cmd == 'add':
            acc.add(args.id, args.name or args.id, _ask_password())
            print(f'만들었습니다: {args.id}')
        elif args.cmd == 'passwd':
            if not acc.get(args.id):
                raise ValueError('없는 아이디')
            acc.set_password(args.id, _ask_password())
            print(f'바꿨습니다: {args.id}')
        elif args.cmd == 'remove':
            acc.remove(args.id)
            print(f'지웠습니다: {args.id}')
        else:
            for uid, u in acc.users().items():
                print(f'{uid}\t{u["name"]}')
    except ValueError as e:
        print(f'안 됩니다: {e}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
