"""웹판 서버 실행.

    python -m bibleclip.server --data <데이터 폴더> [--port 8765]

1단계(docs/WEB_PLAN.md): 이 컴퓨터에서만 열린다(127.0.0.1). 로그인은 2단계에서 붙는다.
"""
import argparse
import os
import threading

from bibleclip.config import DATA_DIR_ENV  # config 의 다른 값은 아래에서, 데이터 폴더를 정한 뒤


def main(argv=None):
    p = argparse.ArgumentParser(prog='python -m bibleclip.server',
                                description='BibleClip 웹판 서버')
    p.add_argument('--data', required=True,
                   help='데이터 폴더(설정 · 노트 · 형광펜 · 추가 역본). 없으면 만든다.')
    p.add_argument('--host', default='127.0.0.1')
    p.add_argument('--port', type=int, default=8765)
    a = p.parse_args(argv)
    if a.host not in ('127.0.0.1', 'localhost', '::1'):
        p.error('지금은 이 컴퓨터(127.0.0.1)에서만 연다 — 로그인이 붙는 2단계 전까지.')

    os.environ[DATA_DIR_ENV] = a.data
    # config 는 가져올 때 데이터 폴더(BASE_DIR)를 정한다 — 그래서 환경 변수를 정한 뒤 가져온다.
    import importlib
    import bibleclip.config as config
    importlib.reload(config)
    os.makedirs(os.path.join(config.BASE_DIR, config.BIBLE_DIR), exist_ok=True)

    from waitress import serve
    from bibleclip.core.library import Library
    from bibleclip.server.app import create_app
    from bibleclip.server.webapi import WebApi
    from bibleclip.webui import api as api_mod

    api_mod.pyperclip = None    # 서버 컴퓨터의 클립보드는 건드리지 않는다(복사는 브라우저가)

    lib = Library()

    def _warm_index():          # 첫 검색 지연을 숨긴다(데스크톱 webui.app 과 같음)
        try:
            db = lib.dbs.get(lib.primary_version())
            if db is not None and not db.is_english:
                db.inverted_index()
        except Exception:
            pass
    threading.Thread(target=_warm_index, daemon=True).start()

    app = create_app(WebApi(lib))
    print(f'BibleClip 웹판: http://127.0.0.1:{a.port}/   (데이터: {config.BASE_DIR})', flush=True)
    serve(app, host=a.host, port=a.port, threads=8)   # 첫 화면이 파일을 한꺼번에 받는다


if __name__ == '__main__':
    main()
