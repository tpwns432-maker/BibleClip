"""웹판 서버 — 화면(web/)을 내주고, 화면의 기능 호출을 WebApi 로 넘긴다.

    GET  /                → web/index.html (+ 웹용 연결 JS · CSS 끼워 넣음)
    GET  /<파일>          → web/ 의 파일 그대로
    GET  /_web/<파일>     → server/static/ (bridge.js · web.css)
    POST /api/<기능>      → {"args": [...]} → {"value": ...}

web/ 는 데스크톱 · 폰과 같은 파일이다. 폰판(MainActivity.kt)처럼 index.html 을 내줄 때
연결 JS 를 맨 앞 <script> 앞에, 웹용 CSS 를 </head> 앞에 끼운다 → web/ 를 고치지 않는다.
"""
import os
import re

from flask import Flask, Response, abort, jsonify, request, send_from_directory

from bibleclip.config import get_resource_dir

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '[::1]'})
_HOST_RE = re.compile(r'^(\[[^\]]+\]|[^:]+)(?::\d+)?$')


def web_dir():
    return os.path.join(get_resource_dir(), 'web')


def index_html():
    with open(os.path.join(web_dir(), 'index.html'), encoding='utf-8') as f:
        html = f.read()
    html = html.replace('</head>', '<link rel="stylesheet" href="_web/web.css">\n</head>', 1)
    i = html.find('<script')
    if i >= 0:
        html = html[:i] + '<script src="_web/bridge.js"></script>\n' + html[i:]
    return html


def _host_name(host):
    m = _HOST_RE.match(host or '')
    return m.group(1).lower() if m else ''


def create_app(api, allowed_hosts=LOOPBACK_HOSTS):
    """api: WebApi. allowed_hosts: 주소창에 올 수 있는 호스트 이름(None = 검사 안 함).
    호스트 검사는 다른 사이트가 이 서버 주소를 자기 이름으로 바꿔 끼우는 공격(DNS
    rebinding)을 막는다."""
    app = Flask(__name__, static_folder=None)
    app.json.sort_keys = False      # 역본 순서 등 dict 순서를 그대로
    app.json.ensure_ascii = False

    @app.before_request
    def _check_host():
        if allowed_hosts is not None and _host_name(request.host) not in allowed_hosts:
            abort(403)

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault('Cache-Control', 'no-store')
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'same-origin'
        return resp

    @app.get('/')
    @app.get('/index.html')
    def index():
        return Response(index_html(), mimetype='text/html')

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(get_resource_dir(), 'icon.ico', max_age=86400)

    @app.get('/_web/<path:name>')
    def web_static(name):
        return send_from_directory(STATIC_DIR, name, max_age=0)

    @app.post('/api/<name>')
    def call(name):
        # 다른 사이트의 폼 · 스크립트는 이 머리글을 붙여 보낼 수 없다(브라우저가 막음).
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        body = request.get_json(silent=True)
        args = body.get('args', []) if isinstance(body, dict) else None
        if not isinstance(args, list):
            abort(400)
        try:
            value = api.call(name, args)
        except TypeError as e:          # 인자 개수 · 모양이 틀림
            return jsonify(error=str(e)), 400
        except Exception as e:          # noqa: BLE001 — 화면에 실패로 알린다
            app.logger.exception('api %s', name)
            return jsonify(error=type(e).__name__), 500
        return jsonify(value=value)

    @app.get('/<path:name>')
    def files(name):
        return send_from_directory(web_dir(), name, max_age=0)

    return app
