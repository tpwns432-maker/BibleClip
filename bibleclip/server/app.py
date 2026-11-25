"""웹판 서버 — 로그인한 사람에게 화면(web/)을 내주고, 화면의 기능 호출을 그 사람의 WebApi 로 넘긴다.

    GET  /login · POST /login   로그인(이것과 favicon 만 로그인 없이 열린다)
    POST /logout                로그아웃
    POST /account/password      내 비밀번호 바꾸기
    POST /account/name          내 이름(화면에 보이는 것) 바꾸기
    GET  /auth/me               지금 로그인한 사람 {id, name, 테마}
    GET  /                      홈(성경 · 커뮤니티) — server/static/home.html
    GET  /bible                 성경 = web/index.html (+ 웹용 연결 JS · CSS 끼워 넣음)
    GET  /community             커뮤니티 — server/static/community.html
    POST /capi/<동작>            커뮤니티 {..} → {"value": ...} (server/community.py)
    GET  /tg/status · POST /tg/token · /tg/link · /tg/unlink · /tg/prefs   텔레그램 알림(server/telegram.py)
    GET  /rc/status · /rc/day?date=   성경읽기 체크(server/readingcheck.py)
    GET  /<파일>                web/ 의 파일 그대로
    GET  /_web/<파일>           server/static/ (bridge.js · web.css)
    POST /api/<기능>            {"args": [...]} → {"value": ...}

web/ 는 데스크톱 · 폰과 같은 파일이다. 폰판(MainActivity.kt)처럼 index.html 을 내줄 때
연결 JS 를 맨 앞 <script> 앞에, 웹용 CSS 를 </head> 앞에 끼운다 → web/ 를 고치지 않는다.
"""
import html as _html
import os
import re
from datetime import timedelta
from urllib.parse import urlsplit

from flask import (Flask, Response, abort, g, jsonify, redirect, request, send_from_directory,
                   session)
from werkzeug.middleware.proxy_fix import ProxyFix

from bibleclip.config import get_resource_dir
from bibleclip.server.community import CommunityError

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static')
# 휴대폰 화면은 안드로이드 앱의 것을 그대로 쓴다(같은 web/ 위에 얹는 CSS · JS).
ANDROID_DIR = ('android', 'app', 'src', 'main', 'assets', 'android')
ANDROID_FILES = frozenset({'mobile.css', 'mobile.js'})
# 휴대폰 = 손가락 화면이면서 짧은 변이 600px 미만(태블릿은 PC 모양). bridge.js 와 같은 기준.
PHONE_MEDIA = ('(pointer: coarse) and (max-device-width: 600px), '
               '(pointer: coarse) and (max-device-height: 600px)')
LOOPBACK_HOSTS = frozenset({'127.0.0.1', 'localhost', '[::1]'})
_HOST_RE = re.compile(r'^(\[[^\]]+\]|[^:]+)(?::\d+)?$')
_PUBLIC = frozenset({'/login', '/favicon.ico'})
_PAGES = frozenset({'/', '/bible', '/community', '/index.html'})   # 로그인 전이면 로그인 화면으로


def web_dir():
    return os.path.join(get_resource_dir(), 'web')


def index_html():
    with open(os.path.join(web_dir(), 'index.html'), encoding='utf-8') as f:
        html = f.read()
    html = html.replace('</head>', f'<link rel="stylesheet" id="bc-phone-css" href="_android/mobile.css" '
                        f'media="{PHONE_MEDIA}">\n<link rel="stylesheet" href="_web/web.css">\n</head>', 1)
    i = html.find('<script')
    if i >= 0:
        html = html[:i] + '<script src="_web/bridge.js"></script>\n' + html[i:]
    return html


def static_page(name):
    with open(os.path.join(STATIC_DIR, name), encoding='utf-8') as f:
        return Response(f.read(), mimetype='text/html')


def login_html(error=''):
    with open(os.path.join(STATIC_DIR, 'login.html'), encoding='utf-8') as f:
        page = f.read()
    msg = f'<p class="err" role="alert">{_html.escape(error)}</p>' if error else ''
    return page.replace('<!--ERROR-->', msg)


def _host_name(host):
    m = _HOST_RE.match(host or '')
    return m.group(1).lower() if m else ''


def create_app(hub, accounts, secret_key, throttle, community=None,
               allowed_hosts=LOOPBACK_HOSTS, secure_cookie=False, extra_hosts=(),
               behind_proxy=False, telegram=None, reading_check=None):
    """hub: WebHub(사람별 WebApi). accounts: Accounts. throttle: 로그인 실패 제한.
    community: Community(없으면 커뮤니티 기능 없음 — 시험용).
    allowed_hosts: 주소창에 올 수 있는 호스트 이름(None = 검사 안 함) — 다른 사이트가 이 서버
    주소를 자기 이름으로 바꿔 끼우는 공격(DNS rebinding)을 막는다.
    secure_cookie: https 로만 쿠키를 보낸다(서버 설치 때 켠다).
    extra_hosts: 이 컴퓨터 말고 들어올 주소 이름(예: Tailscale 의 bibleclip.xxx.ts.net).
    behind_proxy: 앞에서 받아 넘겨주는 프로그램(Tailscale serve)이 붙여 준 '원래 접속한 사람 주소 ·
    https 여부'를 믿는다. 앱은 127.0.0.1 에만 열려 있어 그 프로그램만 이 머리글을 붙일 수 있다."""
    extra = frozenset(h.strip().lower() for h in extra_hosts if h and h.strip())
    if allowed_hosts is not None:
        allowed_hosts = frozenset(allowed_hosts) | extra
    app = Flask(__name__, static_folder=None)
    if behind_proxy:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)
    app.secret_key = secret_key
    app.config.update(
        SESSION_COOKIE_NAME='bibleclip_session',
        SESSION_COOKIE_HTTPONLY=True,          # 페이지 스크립트가 쿠키를 못 읽는다
        SESSION_COOKIE_SAMESITE='Lax',         # 다른 사이트에서 보낸 요청엔 쿠키가 안 붙는다
        SESSION_COOKIE_SECURE=bool(secure_cookie),
        PERMANENT_SESSION_LIFETIME=timedelta(days=30),
        MAX_CONTENT_LENGTH=2 * 1024 * 1024,
    )
    app.json.sort_keys = False      # 역본 순서 등 dict 순서를 그대로
    app.json.ensure_ascii = False

    def current_user():
        uid = session.get('uid')
        u = accounts.get(uid) if uid else None
        if not u or u['sv'] != session.get('sv'):
            return None
        return uid, u

    @app.before_request
    def _guard():
        if allowed_hosts is not None and _host_name(request.host) not in allowed_hosts:
            abort(403)
        if request.path in _PUBLIC:
            return None
        me = current_user()
        if me is None:
            session.clear()
            if request.method == 'GET' and request.path in _PAGES:
                return redirect('login')
            return jsonify(error='login'), 401
        g.uid, g.user = me
        return None

    @app.after_request
    def _headers(resp):
        resp.headers.setdefault('Cache-Control', 'no-store')
        resp.headers['X-Content-Type-Options'] = 'nosniff'
        resp.headers['Referrer-Policy'] = 'same-origin'
        resp.headers['X-Frame-Options'] = 'DENY'
        return resp

    # ---- 로그인 ----

    @app.get('/login')
    def login_page():
        if current_user():
            return redirect('./')
        return Response(login_html(), mimetype='text/html')

    @app.post('/login')
    def login():
        # 다른 사이트의 폼이 이 서버로 로그인시키는 것을 막는다(브라우저가 Origin 을 붙인다).
        origin = request.headers.get('Origin')
        if origin:
            o = urlsplit(origin).netloc
            # 앞 프로그램이 호스트 이름을 127.0.0.1 로 바꿔 넘겨도, 정해 둔 주소에서 온 것이면 받는다.
            if o != request.host and _host_name(o) not in extra:
                abort(403)
        uid = (request.form.get('id') or '').strip().lower()
        pw = request.form.get('password') or ''
        keys = ('id:' + uid, 'ip:' + (request.remote_addr or ''))
        if throttle.blocked(*keys):
            return Response(login_html('여러 번 틀려서 잠시 막혔습니다. 15분 뒤에 다시 해 주세요.'),
                            status=429, mimetype='text/html')
        u = accounts.verify(uid, pw)
        if not u:
            throttle.fail(*keys)
            return Response(login_html('아이디나 비밀번호가 맞지 않습니다.'),
                            status=401, mimetype='text/html')
        throttle.clear(*keys)
        session.clear()
        session.permanent = True
        session['uid'], session['sv'] = uid, u['sv']
        return redirect('./', code=303)

    @app.post('/logout')
    def logout():
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        session.clear()
        return jsonify(ok=True)

    @app.post('/account/name')
    def change_name():
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        body = request.get_json(silent=True) or {}
        try:
            name = accounts.set_name(g.uid, body.get('name'))
        except ValueError as e:
            return jsonify(error='invalid', detail=str(e)), 400
        return jsonify(ok=True, name=name)

    @app.post('/account/password')
    def change_password():
        """지금 비밀번호를 확인하고 새 비밀번호로. 다른 기기의 로그인은 풀리고 이 기기는 유지."""
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        body = request.get_json(silent=True) or {}
        cur, new = str(body.get('current') or ''), str(body.get('new') or '')
        keys = ('id:' + g.uid, 'ip:' + (request.remote_addr or ''))
        if throttle.blocked(*keys):
            return jsonify(error='blocked'), 429
        if not accounts.verify(g.uid, cur):
            throttle.fail(*keys)
            return jsonify(error='wrong'), 403
        try:
            accounts.set_password(g.uid, new)
        except ValueError as e:
            return jsonify(error='invalid', detail=str(e)), 400
        session['sv'] = accounts.get(g.uid)['sv']
        return jsonify(ok=True)

    @app.get('/auth/me')
    def me():
        # 홈 · 커뮤니티도 그 사람의 색 테마로 그린다(성경 화면 설정과 같은 값).
        s = hub.api_for(g.uid, g.user['name']).lib.settings
        return jsonify(id=g.uid, name=g.user['name'], theme=s.get('theme') or '',
                       dark_mode=bool(s.get('dark_mode')), custom_theme=s.get('custom_theme'))

    # ---- 화면 · 기능 ----

    @app.get('/favicon.ico')
    def favicon():
        return send_from_directory(get_resource_dir(), 'icon.ico', max_age=86400)

    @app.get('/')
    def home():
        return static_page('home.html')

    @app.get('/bible')
    def bible():
        return Response(index_html(), mimetype='text/html')

    @app.get('/index.html')
    def old_index():
        return redirect('bible')

    @app.get('/community')
    def community_page():
        return static_page('community.html')

    @app.post('/capi/<action>')
    def capi(action):
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        body = request.get_json(silent=True)
        if not isinstance(body, dict):
            abort(400)
        if action == 'partner_highlights':
            return jsonify(value=partner_highlights(body))
        if community is None:
            abort(404)
        try:
            value = community.call(g.uid, action, body)
        except CommunityError as e:
            status = {'notfound': 404, 'forbidden': 403}.get(e.code, 400)
            return jsonify(error=e.code, detail=e.detail), status
        return jsonify(value=value)

    @app.get('/_android/<name>')
    def android_static(name):
        if name not in ANDROID_FILES:
            abort(404)
        return send_from_directory(os.path.join(get_resource_dir(), *ANDROID_DIR), name, max_age=0)

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
        api = hub.api_for(g.uid, g.user['name'])
        try:
            value = api.call(name, args)
        except TypeError as e:          # 인자 개수 · 모양이 틀림
            return jsonify(error=str(e)), 400
        except Exception as e:          # noqa: BLE001 — 화면에 실패로 알린다
            app.logger.exception('api %s', name)
            return jsonify(error=type(e).__name__), 500
        return jsonify(value=value)

    # ---- 텔레그램 알림(로그인한 사람 자기 것만) ----

    def _tg():
        if telegram is None:
            abort(404)
        return telegram

    def _tg_post():
        if request.headers.get('X-BibleClip') != '1':
            abort(403)
        body = request.get_json(silent=True)
        return body if isinstance(body, dict) else {}

    # ---- 성경읽기 체크 ----

    @app.get('/rc/status')
    def rc_status():
        if reading_check is None:
            abort(404)
        return jsonify(reading_check.status(g.uid))

    @app.get('/rc/day')
    def rc_day():
        if reading_check is None:
            abort(404)
        info = reading_check.info_iso(request.args.get('date', ''))
        if not info:
            abort(404)
        return jsonify(info)

    @app.get('/tg/status')
    def tg_status():
        return jsonify(_tg().status(g.uid))

    @app.post('/tg/token')
    def tg_token():
        bot = _tg()
        return jsonify(bot.set_token(str(_tg_post().get('token') or '')))

    @app.post('/tg/link')
    def tg_link():
        bot = _tg()
        _tg_post()
        return jsonify(bot.link_url(g.uid))

    @app.post('/tg/unlink')
    def tg_unlink():
        bot = _tg()
        _tg_post()
        return jsonify(bot.unlink(g.uid))

    @app.post('/tg/prefs')
    def tg_prefs():
        bot = _tg()
        return jsonify(bot.set_prefs(g.uid, _tg_post()))

    def partner_highlights(a):
        """성경 한 장에서 상대가 칠한 형광펜(bridge.js 가 밑줄로 그린다)."""
        try:
            book, chapter = int(a.get('book')), int(a.get('chapter'))
        except (TypeError, ValueError):
            abort(400)
        versions = [str(v) for v in (a.get('versions') or []) if isinstance(v, str)][:8]
        others = [(k, u['name']) for k, u in accounts.users().items() if k != g.uid]
        return hub.partner_highlights(g.uid, others, book, chapter, versions)

    @app.get('/<path:name>')
    def files(name):
        return send_from_directory(web_dir(), name, max_age=0)

    return app
