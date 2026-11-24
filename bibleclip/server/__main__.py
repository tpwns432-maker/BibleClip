"""웹판 서버 실행.

    python -m bibleclip.server.accounts --data <데이터 폴더> add <아이디> --name <이름>   # 계정(처음 한 번)
    python -m bibleclip.server --data <데이터 폴더> [--port 8765]

데이터 폴더(docs/WEB_PLAN.md):
    users.json         계정(비밀번호는 해시만)          secret_key   로그인 쿠키 서명 열쇠
    users/<아이디>/     그 사람의 설정 · 노트 · 형광펜     bible_versions/  서버 주인이 넣는 역본
    community.db       커뮤니티(주제 · 글 · 댓글 · 공감 · 읽음)
앱은 이 컴퓨터(127.0.0.1)에만 열린다. 다른 기기는 Tailscale serve 가 https 로 받아 넘겨준다:
    --allow-host <주소> --behind-proxy --secure-cookie   (deploy/tailscale.sh 가 정해 준다)
"""
import argparse
import os
import threading

from bibleclip.config import DATA_DIR_ENV  # config 의 다른 값은 아래에서, 데이터 폴더를 정한 뒤


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m bibleclip.server',
                                description='BibleClip 웹판 서버')
    p.add_argument('--data', required=True,
                   help='데이터 폴더(계정 · 사람별 설정 · 노트 · 형광펜 · 추가 역본). 없으면 만든다.')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    p.add_argument('--secure-cookie', action='store_true',
                   help='로그인 쿠키를 https 로만 보낸다(https 로 접속할 때 켠다)')
    p.add_argument('--allow-host', action='append', default=[], metavar='NAME',
                   help='이 컴퓨터 말고 들어올 주소 이름(예: bibleclip.xxx.ts.net). 여러 번 쓸 수 있다.')
    p.add_argument('--behind-proxy', action='store_true',
                   help='Tailscale serve 같은 앞 프로그램이 넘겨준 접속 정보를 믿는다')
    a = p.parse_args(argv)
    if a.host not in ('127.0.0.1', 'localhost', '::1'):
        p.error('앱은 이 컴퓨터(127.0.0.1)에서만 연다. 다른 기기는 Tailscale serve 로 들어온다'
                '(docs/WEB_SETUP.md).')

    os.environ[DATA_DIR_ENV] = a.data
    # config 는 가져올 때 데이터 폴더(BASE_DIR)를 정한다 — 그래서 환경 변수를 정한 뒤 다시 읽는다.
    import importlib
    import bibleclip.config as config
    importlib.reload(config)
    data = config.BASE_DIR
    os.makedirs(os.path.join(data, config.BIBLE_DIR), exist_ok=True)

    from bibleclip.server.accounts import Accounts, Throttle, secret_key
    accounts = Accounts(data)
    if not accounts.users():
        p.exit(2, '계정이 아직 없습니다. 먼저 만들어 주세요:\n'
                  f'  python -m bibleclip.server.accounts --data "{a.data}" add <아이디> --name <이름>\n')

    from waitress import serve
    from bibleclip.core.library import Library
    from bibleclip.server.app import create_app
    from bibleclip.server.community import DB_FILE, Community
    from bibleclip.server.webapi import WebHub
    from bibleclip.webui import api as api_mod

    api_mod.pyperclip = None    # 서버 컴퓨터의 클립보드는 건드리지 않는다(복사는 브라우저가)

    engine = Library()          # 역본 · 원어를 한 번만 읽는다. 사람별 Library 가 나눠 쓴다.

    def _warm_index():          # 첫 검색 지연을 숨긴다(데스크톱 webui.app 과 같음)
        try:
            for name in ('KRV', engine.primary_version()):
                db = engine.dbs.get(name)
                if db is not None and not db.is_english:
                    db.inverted_index()
        except Exception:
            pass
    threading.Thread(target=_warm_index, daemon=True).start()

    hub = WebHub(engine, data)

    def parse(text):            # 글 속 구절 찾기 — 사용자 약칭까지(엔진은 hub 잠금 안에서)
        with hub._lock:
            return engine.parse_reference(text)
    community = Community(os.path.join(data, DB_FILE), names=accounts.users, parse=parse,
                          verse_text=hub.verse_text)

    app = create_app(hub, accounts, secret_key(data), Throttle(), community,
                     secure_cookie=a.secure_cookie, extra_hosts=a.allow_host,
                     behind_proxy=a.behind_proxy)
    print(f'BibleClip 웹판: http://127.0.0.1:{a.port}/   (데이터: {data})', flush=True)
    serve(app, host=a.host, port=a.port, threads=8)   # 첫 화면이 파일을 한꺼번에 받는다


if __name__ == '__main__':
    main()
