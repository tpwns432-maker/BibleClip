"""웹판 커뮤니티 — 주제 · 글 · 댓글 · 공감 · 읽음 (docs/WEB_PLAN.md "커뮤니티").

저장은 데이터 폴더의 community.db(SQLite — Python 에 들어 있는 작은 데이터베이스, 파일 하나).
두 사람이 동시에 써도 연결 하나 + 잠금으로 차례차례 처리한다. 백업은 이 파일을 복사하면 된다.

화면(server/static/community.js)은 POST /capi/<동작> 으로 부른다(server/app.py). 여기 함수는
모두 "누가(uid) 부르는지"를 받아 권한(고치기 · 지우기는 쓴 사람만)과 '새 글' 표시를 정한다.
"""
import json
import re
import sqlite3
import threading
from datetime import datetime, timezone

from bibleclip.core.engine import Engine

DB_FILE = 'community.db'

TITLE_MAX, BODY_MAX, COMMENT_MAX = 200, 20000, 5000
TOPIC_NAME_MAX, TOPIC_DESC_MAX = 30, 200
SOURCE_KINDS = ('sermon', 'book')
SOURCE_FIELDS = {          # 감상 대상 칸과 최대 길이
    'sermon': {'title': 200, 'by': 60, 'date': 10, 'url': 500},
    'book': {'title': 200, 'by': 60, 'part': 100},
}
SORTS = ('activity', 'new', 'likes')
SNIPPET = 160

#: 처음 만들어 두는 주제(사용자 결정 2026-11-24).
SEED_TOPICS = (
    ('말씀', '들은 설교의 감상', 'sermon'),
    ('모임 서적', '모임에서 함께 읽는 책', 'book'),
    ('성경 묵상', '성경을 읽고 묵상한 것', ''),
    ('자유', '무엇이든', ''),
)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS topics(
  id INTEGER PRIMARY KEY, name TEXT NOT NULL UNIQUE, description TEXT NOT NULL DEFAULT '',
  source_kind TEXT NOT NULL DEFAULT '', position INTEGER NOT NULL DEFAULT 0,
  created_by TEXT NOT NULL, created_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS posts(
  id INTEGER PRIMARY KEY, topic_id INTEGER NOT NULL REFERENCES topics(id),
  author TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL,
  source_kind TEXT NOT NULL DEFAULT '', source_title TEXT NOT NULL DEFAULT '', source TEXT,
  verse TEXT, created_at TEXT NOT NULL, edited_at TEXT, activity_at TEXT NOT NULL,
  activity_seq INTEGER NOT NULL DEFAULT 0, deleted INTEGER NOT NULL DEFAULT 0,
  v_book INTEGER, v_chapter INTEGER);
CREATE INDEX IF NOT EXISTS posts_topic ON posts(topic_id, activity_at);
CREATE TABLE IF NOT EXISTS comments(
  id INTEGER PRIMARY KEY, post_id INTEGER NOT NULL REFERENCES posts(id),
  parent_id INTEGER REFERENCES comments(id), author TEXT NOT NULL, body TEXT NOT NULL,
  created_at TEXT NOT NULL, edited_at TEXT, deleted INTEGER NOT NULL DEFAULT 0);
CREATE INDEX IF NOT EXISTS comments_post ON comments(post_id, created_at);
CREATE TABLE IF NOT EXISTS likes(
  kind TEXT NOT NULL, target INTEGER NOT NULL, user TEXT NOT NULL, created_at TEXT NOT NULL,
  PRIMARY KEY(kind, target, user));
CREATE TABLE IF NOT EXISTS seen(
  user TEXT NOT NULL, post_id INTEGER NOT NULL, seen_at TEXT NOT NULL,
  last_cid INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(user, post_id));
"""


class CommunityError(Exception):
    """화면에 돌려줄 실패. code: notfound · forbidden · invalid · exists · notempty."""

    def __init__(self, code, detail=''):
        super().__init__(code)
        self.code, self.detail = code, detail


def _now():
    # 밀리초 · UTC · 같은 모양 → 문자열 비교가 곧 시간 비교.
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def _text(v, limit, field, required=False):
    s = v.strip() if isinstance(v, str) else ''
    s = s.replace('\r\n', '\n').replace('\r', '\n').replace('\x00', '')
    if required and not s:
        raise CommunityError('invalid', field + ' 비어 있음')
    if len(s) > limit:
        raise CommunityError('invalid', f'{field} {limit}자 넘음')
    return s


def _id(v, field='id'):
    if isinstance(v, bool) or not isinstance(v, int) or v <= 0:
        raise CommunityError('invalid', field)
    return v


def _int(v, default):
    return v if isinstance(v, int) and not isinstance(v, bool) else default


def clean_source(src):
    """감상 대상 {kind, title, by, date|part, url}. 없거나 비면 None. 칸 밖은 버린다."""
    if not isinstance(src, dict) or src.get('kind') not in SOURCE_KINDS:
        return None
    kind = src['kind']
    out = {'kind': kind}
    for k, limit in SOURCE_FIELDS[kind].items():
        out[k] = _text(src.get(k), limit, 'source.' + k)
    if not out['title']:
        return None
    if out.get('url') and not re.match(r'^https?://\S+$', out['url']):
        raise CommunityError('invalid', 'source.url')
    if out.get('date') and not re.match(r'^\d{4}-\d{2}-\d{2}$', out['date']):
        raise CommunityError('invalid', 'source.date')
    return out


def clean_verse(v):
    """글에 단 구절 범위 {book, chapter, verse, verse_end} — 한 장 안. 없으면 None.
    책 번호는 우리 번호(10..730)여야 하고, 보기 좋은 이름(label)을 붙여 돌려준다."""
    if v is None:
        return None
    if not isinstance(v, dict):
        raise CommunityError('invalid', 'verse')
    book = _id(v.get('book'), 'verse')
    chapter = _id(v.get('chapter'), 'verse')
    start = _id(v.get('verse'), 'verse')
    end = _id(v.get('verse_end', start), 'verse')
    canon = Engine._canon(book)
    if not canon or chapter > 150 or end > 176 or end < start:
        raise CommunityError('invalid', 'verse')
    label = f'{canon[1]} {chapter}:{start}' + (f'-{end}' if end > start else '')
    return {'book': book, 'chapter': chapter, 'verse': start, 'verse_end': end, 'label': label}


# ---- 구절 자동 링크 ----

_REF_RE = re.compile(
    r'([1-3]?\s?[가-힣A-Za-z]{1,14}\.?)\s?(\d{1,3})\s?(?::|[장편]\s?)'
    r'(\d{1,3}(?:\s?[-~,]\s?\d{1,3})*)(?:\s?절)?')


def _u16(text, i):
    """파이썬 글자 위치 → 브라우저(JS) 문자열 위치. 이모지 같은 글자는 JS 에선 2칸이다."""
    return len(text[:i].encode('utf-16-le')) // 2


def find_refs(text, parse):
    """글 속 성경 구절을 찾는다. parse = Library.parse_reference.
    [{s, e, book, chapter, verses, label}] — s · e 는 JS 문자열 위치."""
    out = []
    for m in _REF_RE.finditer(text or ''):
        book_tok = m.group(1)
        # (f-string 안에 역슬래시를 쓰면 Python 3.12 미만에서 문법 오류 — 서버는 3.10)
        verses = re.sub(r'\s', '', m.group(3))
        tail = f' {m.group(2)}:{verses}'
        # "말씀은요 3:16" 처럼 앞말이 붙어 있으면 뒤에서부터 줄여 가며 책 이름을 찾는다.
        for i in range(len(book_tok)):
            if book_tok[i].isspace():
                continue
            cand = book_tok[i:].strip()
            try:
                hits = parse(cand + tail)
            except Exception:
                hits = []
            if hits and hits[0][4]:
                book, short, _long, chapter, verses = hits[0]
                vs = sorted(set(int(v) for v in verses))
                start = m.start(1) + i
                label = f'{short} {chapter}:{vs[0]}' + (f'-{vs[-1]}' if len(vs) > 1 else '')
                out.append({'s': _u16(text, start), 'e': _u16(text, m.end()), 'book': book,
                            'chapter': chapter, 'verses': vs, 'label': label})
                break
    return out


class Community:
    def __init__(self, path, names=None, parse=None, verse_text=None, on_event=None):
        """path: community.db. names(): {uid: 보이는 이름}. parse: 구절 인식기(없으면 링크 없음).
        verse_text(uid, verse) → {version, verses: [{n, text}]}: 글에 단 구절의 본문(읽는 사람의 역본)."""
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        self._names = names or (lambda: {})
        self._parse = parse
        self._verse_text = verse_text
        self._on_event = on_event       # 새 글 · 댓글 알림(텔레그램 봇) — {'kind', 'author', 'post_id'}
        with self._lock, self._db:
            self._db.execute('PRAGMA journal_mode=WAL')
            self._db.execute('PRAGMA foreign_keys=ON')
            self._db.executescript(_SCHEMA)
            # 앞 버전에서 만든 파일에 새 칸을 붙인다(지우지 않고 더하기만).
            for table, col, decl in (('posts', 'activity_seq', 'INTEGER NOT NULL DEFAULT 0'),
                                     ('seen', 'last_cid', 'INTEGER NOT NULL DEFAULT 0'),
                                     ('posts', 'v_book', 'INTEGER'),
                                     ('posts', 'v_chapter', 'INTEGER')):
                cols = [r[1] for r in self._db.execute(f'PRAGMA table_info({table})')]
                if col not in cols:
                    self._db.execute(f'ALTER TABLE {table} ADD COLUMN {col} {decl}')
            self._db.execute('CREATE INDEX IF NOT EXISTS posts_verse ON posts(v_book, v_chapter)')
            if not self._db.execute("SELECT 1 FROM meta WHERE key='seeded'").fetchone():
                now = _now()
                for pos, (name, desc, kind) in enumerate(SEED_TOPICS):
                    self._db.execute(
                        'INSERT OR IGNORE INTO topics(name, description, source_kind, position,'
                        ' created_by, created_at) VALUES(?,?,?,?,?,?)',
                        (name, desc, kind, pos, '', now))
                self._db.execute("INSERT INTO meta VALUES('seeded', '1')")

    def close(self):
        self._db.close()

    # ---- 도움 ----

    def _q(self, sql, args=()):
        return self._db.execute(sql, args).fetchall()

    def _one(self, sql, args=()):
        return self._db.execute(sql, args).fetchone()

    def _who(self, uid):
        return {'id': uid, 'name': self._names().get(uid, {}).get('name', uid) if uid else ''}

    def _refs(self, text):
        return find_refs(text, self._parse) if self._parse else []

    def _likes(self, kind, target, uid):
        users = [r['user'] for r in self._q(
            'SELECT user FROM likes WHERE kind=? AND target=? ORDER BY rowid', (kind, target))]
        return {'likes': len(users), 'liked': uid in users,
                'likers': [self._who(u)['name'] for u in users]}

    # '읽음'은 시간이 아니라 **번호**로 잰다: 그 글에서 마지막으로 본 댓글 번호(last_cid).
    # 시간(밀리초)으로 비교하면 같은 순간에 생긴 상대 댓글을 '이미 봄'으로 셀 수 있다.
    def _seen(self, uid, post_id):
        """그 글을 본 적 없으면 None, 있으면 마지막으로 본 댓글 번호(없으면 0)."""
        r = self._one('SELECT last_cid FROM seen WHERE user=? AND post_id=?', (uid, post_id))
        return r['last_cid'] if r else None

    def _mark_seen(self, uid, post_id):
        last = self._one('SELECT COALESCE(MAX(id), 0) FROM comments WHERE post_id=?', (post_id,))[0]
        self._db.execute('INSERT INTO seen VALUES(?,?,?,?) ON CONFLICT(user, post_id)'
                         ' DO UPDATE SET seen_at=excluded.seen_at, last_cid=excluded.last_cid',
                         (uid, post_id, _now(), last))

    def _next_seq(self):
        """'최근 활동' 순번 — 글이 생기거나 댓글이 달릴 때마다 1씩 오른다(시간보다 확실한 순서)."""
        return self._one('SELECT COALESCE(MAX(activity_seq), 0) + 1 FROM posts')[0]

    def _post_row(self, post_id):
        r = self._one('SELECT * FROM posts WHERE id=?', (_id(post_id),))
        if not r:
            raise CommunityError('notfound')
        return r

    def _unread(self, uid, post):
        """(내가 아직 안 본 상대 글인가, 안 본 상대 댓글 수)."""
        seen = self._seen(uid, post['id'])
        is_new = post['author'] != uid and seen is None and not post['deleted']
        n = self._one('SELECT COUNT(*) FROM comments WHERE post_id=? AND author<>? AND deleted=0'
                      ' AND id>?', (post['id'], uid, seen or 0))[0]
        return is_new, n

    # ---- 주제 ----

    def topics(self, uid):
        with self._lock:
            out = []
            for t in self._q('SELECT * FROM topics ORDER BY position, id'):
                posts = self._q('SELECT * FROM posts WHERE topic_id=?', (t['id'],))
                unread = 0
                for p in posts:
                    is_new, n = self._unread(uid, p)
                    unread += int(is_new) + n
                out.append({'id': t['id'], 'name': t['name'], 'description': t['description'],
                            'source_kind': t['source_kind'],
                            'posts': sum(1 for p in posts if not p['deleted']), 'unread': unread})
            return out

    def home(self, uid):
        """홈 화면: 주제별 새 글 수 + 최근 글 몇 개."""
        topics = self.topics(uid)
        return {'unread': sum(t['unread'] for t in topics), 'topics': topics,
                'recent': self.posts(uid, {'sort': 'activity', 'limit': 5})['posts']}

    def topic_save(self, uid, a):
        name = _text(a.get('name'), TOPIC_NAME_MAX, 'name', required=True)
        desc = _text(a.get('description'), TOPIC_DESC_MAX, 'description')
        kind = a.get('source_kind') if a.get('source_kind') in SOURCE_KINDS else ''
        with self._lock, self._db:
            clash = self._one('SELECT id FROM topics WHERE name=?', (name,))
            if a.get('id') is not None:
                tid = _id(a['id'])
                if not self._one('SELECT 1 FROM topics WHERE id=?', (tid,)):
                    raise CommunityError('notfound')
                if clash and clash['id'] != tid:
                    raise CommunityError('exists')
                self._db.execute('UPDATE topics SET name=?, description=?, source_kind=? WHERE id=?',
                                 (name, desc, kind, tid))
            else:
                if clash:
                    raise CommunityError('exists')
                pos = self._one('SELECT COALESCE(MAX(position), -1) + 1 FROM topics')[0]
                tid = self._db.execute(
                    'INSERT INTO topics(name, description, source_kind, position, created_by,'
                    ' created_at) VALUES(?,?,?,?,?,?)', (name, desc, kind, pos, uid, _now())).lastrowid
        return {'id': tid}

    def topic_delete(self, uid, a):
        tid = _id(a.get('id'))
        with self._lock, self._db:
            if not self._one('SELECT 1 FROM topics WHERE id=?', (tid,)):
                raise CommunityError('notfound')
            if self._one('SELECT 1 FROM posts WHERE topic_id=? LIMIT 1', (tid,)):
                raise CommunityError('notempty')
            self._db.execute('DELETE FROM topics WHERE id=?', (tid,))
        return {'ok': True}

    # ---- 글 ----

    def _post_summary(self, uid, p, topic_names):
        is_new, new_comments = self._unread(uid, p)
        comments = self._one('SELECT COUNT(*) FROM comments WHERE post_id=? AND deleted=0',
                             (p['id'],))[0]
        body = '' if p['deleted'] else p['body']
        snippet = ' '.join(body.split())
        return {
            'id': p['id'], 'topic': {'id': p['topic_id'], 'name': topic_names.get(p['topic_id'], '')},
            'author': self._who(p['author']), 'title': '' if p['deleted'] else p['title'],
            'snippet': snippet[:SNIPPET] + ('…' if len(snippet) > SNIPPET else ''),
            'source': None if p['deleted'] or not p['source'] else json.loads(p['source']),
            'verse': None if p['deleted'] or not p['verse'] else json.loads(p['verse']),
            'created_at': p['created_at'], 'edited_at': p['edited_at'],
            'activity_at': p['activity_at'], 'deleted': bool(p['deleted']),
            'comments': comments, 'is_new': is_new, 'new_comments': new_comments,
            'mine': p['author'] == uid, **self._likes('post', p['id'], uid),
        }

    def posts(self, uid, a):
        """글 목록. a: {topic_id?, sort, source_kind?, source_title?, offset, limit}."""
        sort = a.get('sort') if a.get('sort') in SORTS else 'activity'
        limit = min(max(_int(a.get('limit'), 30), 1), 100)
        offset = max(_int(a.get('offset'), 0), 0)
        where, args = ['1=1'], []
        if a.get('topic_id') is not None:
            where.append('p.topic_id=?')
            args.append(_id(a['topic_id'], 'topic_id'))
        if a.get('source_kind') in SOURCE_KINDS:
            where.append('p.source_kind=?')
            args.append(a['source_kind'])
            if isinstance(a.get('source_title'), str) and a['source_title'].strip():
                where.append('p.source_title=?')
                args.append(a['source_title'].strip().casefold())
        order = {'activity': 'p.activity_seq DESC, p.id DESC', 'new': 'p.id DESC',
                 'likes': 'likes DESC, p.activity_seq DESC, p.id DESC'}[sort]
        with self._lock:
            names = {r['id']: r['name'] for r in self._q('SELECT id, name FROM topics')}
            rows = self._q(
                "SELECT p.*, (SELECT COUNT(*) FROM likes l WHERE l.kind='post' AND l.target=p.id)"
                f" AS likes FROM posts p WHERE {' AND '.join(where)} ORDER BY {order}"
                ' LIMIT ? OFFSET ?', (*args, limit + 1, offset))
            items = [self._post_summary(uid, p, names) for p in rows[:limit]]
        return {'posts': items, 'more': len(rows) > limit}

    def post(self, uid, a):
        """글 하나 + 댓글 전부(평평한 목록, parent 로 나무를 만든다). 연 사람은 '읽음'이 된다."""
        with self._lock, self._db:
            p = self._post_row(a.get('id'))
            names = {r['id']: r['name'] for r in self._q('SELECT id, name FROM topics')}
            out = self._post_summary(uid, p, names)
            out['body'] = '' if p['deleted'] else p['body']
            out['refs'] = self._refs(out['body'])
            out['verse_text'] = None
            if out['verse'] and self._verse_text:
                try:
                    out['verse_text'] = self._verse_text(uid, out['verse'])
                except Exception:
                    out['verse_text'] = None
            seen = self._seen(uid, p['id'])
            comments = []
            for c in self._q('SELECT * FROM comments WHERE post_id=? ORDER BY id',
                             (p['id'],)):
                body = '' if c['deleted'] else c['body']
                comments.append({
                    'id': c['id'], 'parent_id': c['parent_id'], 'author': self._who(c['author']),
                    'body': body, 'refs': self._refs(body), 'created_at': c['created_at'],
                    'edited_at': c['edited_at'], 'deleted': bool(c['deleted']),
                    'mine': c['author'] == uid,
                    'is_new': (c['author'] != uid and not c['deleted']
                               and (seen is None or c['id'] > seen)),
                    **self._likes('comment', c['id'], uid)})
            out['comment_list'] = comments
            self._mark_seen(uid, p['id'])
        return out

    def post_save(self, uid, a):
        title = _text(a.get('title'), TITLE_MAX, 'title', required=True)
        body = _text(a.get('body'), BODY_MAX, 'body', required=True)
        source = clean_source(a.get('source'))
        skind = source['kind'] if source else ''
        stitle = source['title'].casefold() if source else ''
        sjson = json.dumps(source, ensure_ascii=False) if source else None
        tid = _id(a.get('topic_id'), 'topic_id')
        created = False
        has_verse = 'verse' in a
        verse = clean_verse(a.get('verse')) if has_verse else None
        now = _now()
        with self._lock, self._db:
            if not self._one('SELECT 1 FROM topics WHERE id=?', (tid,)):
                raise CommunityError('notfound', 'topic')
            if a.get('id') is not None:
                p = self._post_row(a['id'])
                if p['author'] != uid:
                    raise CommunityError('forbidden')
                if p['deleted']:
                    raise CommunityError('notfound')
                if not has_verse:      # 고칠 때 구절을 안 보내면 그대로 둔다
                    verse = json.loads(p['verse']) if p['verse'] else None
                self._db.execute(
                    'UPDATE posts SET topic_id=?, title=?, body=?, source_kind=?, source_title=?,'
                    ' source=?, verse=?, v_book=?, v_chapter=?, edited_at=? WHERE id=?',
                    (tid, title, body, skind, stitle, sjson, *self._verse_cols(verse), now, p['id']))
                pid = p['id']
            else:
                pid = self._db.execute(
                    'INSERT INTO posts(topic_id, author, title, body, source_kind, source_title,'
                    ' source, verse, v_book, v_chapter, created_at, activity_at, activity_seq)'
                    ' VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)',
                    (tid, uid, title, body, skind, stitle, sjson, *self._verse_cols(verse),
                     now, now, self._next_seq())).lastrowid
                created = True
            self._mark_seen(uid, pid)
        if a.get('id') is None and created:
            self._emit('post', uid, pid)
        return {'id': pid}

    def post_delete(self, uid, a):
        with self._lock, self._db:
            p = self._post_row(a.get('id'))
            if p['author'] != uid:
                raise CommunityError('forbidden')
            if self._one('SELECT 1 FROM comments WHERE post_id=? LIMIT 1', (p['id'],)):
                # 댓글은 상대의 글이기도 하다 — 글만 비우고 자리는 남긴다.
                self._db.execute("UPDATE posts SET deleted=1, title='', body='', source=NULL,"
                                 " source_kind='', source_title='', verse=NULL, v_book=NULL,"
                                 " v_chapter=NULL WHERE id=?", (p['id'],))
            else:
                self._db.execute("DELETE FROM likes WHERE kind='post' AND target=?", (p['id'],))
                self._db.execute('DELETE FROM seen WHERE post_id=?', (p['id'],))
                self._db.execute('DELETE FROM posts WHERE id=?', (p['id'],))
        return {'ok': True}

    @staticmethod
    def _verse_cols(verse):
        if not verse:
            return None, None, None
        return json.dumps(verse, ensure_ascii=False), verse['book'], verse['chapter']

    def verse_posts(self, uid, a):
        """성경 한 장에 달린 글(지운 글 빼고) — 성경 화면의 절 표시용. 구절 순."""
        book, chapter = _id(a.get('book'), 'book'), _id(a.get('chapter'), 'chapter')
        with self._lock:
            names = {r['id']: r['name'] for r in self._q('SELECT id, name FROM topics')}
            rows = self._q('SELECT * FROM posts WHERE v_book=? AND v_chapter=? AND deleted=0'
                           ' ORDER BY id', (book, chapter))
            items = [self._post_summary(uid, p, names) for p in rows]
        items.sort(key=lambda p: (p['verse']['verse'], p['verse']['verse_end'], p['id']))
        return {'posts': items}

    def verse_preview(self, uid, a):
        """글쓰기 화면에서 고른 구절을 확인 · 미리 보기(이름표 + 읽는 사람 역본의 본문)."""
        v = clean_verse(a.get('verse'))
        if not v:
            raise CommunityError('invalid', 'verse')
        text = None
        if self._verse_text:
            try:
                text = self._verse_text(uid, v)
            except Exception:
                text = None
        return {'verse': v, 'verse_text': text}

    def default_topic(self, uid=None):
        """'함께 쓰기'가 고를 주제: 이름이 '성경 묵상'인 주제, 없으면 첫 주제."""
        with self._lock:
            r = (self._one("SELECT id FROM topics WHERE name='성경 묵상'")
                 or self._one('SELECT id FROM topics ORDER BY position, id LIMIT 1'))
        return {'id': r['id'] if r else None}

    # ---- 댓글 ----

    def comment_save(self, uid, a):
        body = _text(a.get('body'), COMMENT_MAX, 'body', required=True)
        now = _now()
        with self._lock, self._db:
            if a.get('id') is not None:
                c = self._one('SELECT * FROM comments WHERE id=?', (_id(a['id']),))
                if not c or c['deleted']:
                    raise CommunityError('notfound')
                if c['author'] != uid:
                    raise CommunityError('forbidden')
                self._db.execute('UPDATE comments SET body=?, edited_at=? WHERE id=?',
                                 (body, now, c['id']))
                return {'id': c['id']}
            p = self._post_row(a.get('post_id'))
            if p['deleted']:
                raise CommunityError('notfound')
            parent = a.get('parent_id')
            if parent is not None:
                pc = self._one('SELECT post_id FROM comments WHERE id=?', (_id(parent, 'parent_id'),))
                if not pc or pc['post_id'] != p['id']:
                    raise CommunityError('notfound', 'parent')
            cid = self._db.execute(
                'INSERT INTO comments(post_id, parent_id, author, body, created_at)'
                ' VALUES(?,?,?,?,?)', (p['id'], parent, uid, body, now)).lastrowid
            self._db.execute('UPDATE posts SET activity_at=?, activity_seq=? WHERE id=?',
                             (now, self._next_seq(), p['id']))
            self._mark_seen(uid, p['id'])
        self._emit('comment', uid, p['id'])
        return {'id': cid}

    def comment_delete(self, uid, a):
        with self._lock, self._db:
            c = self._one('SELECT * FROM comments WHERE id=?', (_id(a.get('id')),))
            if not c:
                raise CommunityError('notfound')
            if c['author'] != uid:
                raise CommunityError('forbidden')
            if self._one('SELECT 1 FROM comments WHERE parent_id=? LIMIT 1', (c['id'],)):
                self._db.execute("UPDATE comments SET deleted=1, body='' WHERE id=?", (c['id'],))
            else:
                self._db.execute("DELETE FROM likes WHERE kind='comment' AND target=?", (c['id'],))
                self._db.execute('DELETE FROM comments WHERE id=?', (c['id'],))
        return {'ok': True}

    def _emit(self, kind, author, post_id):
        if self._on_event:
            try:
                self._on_event({'kind': kind, 'author': author, 'post_id': post_id})
            except Exception:       # noqa: BLE001 — 알림이 실패해도 글쓰기는 된다
                pass

    # ---- 공감 ----

    def like(self, uid, a):
        kind = a.get('kind')
        if kind not in ('post', 'comment'):
            raise CommunityError('invalid', 'kind')
        target = _id(a.get('id'))
        table = 'posts' if kind == 'post' else 'comments'
        with self._lock, self._db:
            row = self._one(f'SELECT deleted FROM {table} WHERE id=?', (target,))
            if not row or row['deleted']:
                raise CommunityError('notfound')
            if self._one('SELECT 1 FROM likes WHERE kind=? AND target=? AND user=?',
                         (kind, target, uid)):
                self._db.execute('DELETE FROM likes WHERE kind=? AND target=? AND user=?',
                                 (kind, target, uid))
            else:
                self._db.execute('INSERT INTO likes VALUES(?,?,?,?)', (kind, target, uid, _now()))
            return self._likes(kind, target, uid)

    #: 화면이 부를 수 있는 동작.
    ACTIONS = ('home', 'topics', 'topic_save', 'topic_delete', 'posts', 'post', 'post_save',
               'post_delete', 'comment_save', 'comment_delete', 'like', 'verse_posts',
               'verse_preview', 'default_topic')

    def call(self, uid, action, args):
        if action not in self.ACTIONS:
            raise CommunityError('notfound', action)
        if not isinstance(args, dict):
            raise CommunityError('invalid', 'args')
        fn = getattr(self, action)
        return fn(uid) if action in ('home', 'topics', 'default_topic') else fn(uid, args)
