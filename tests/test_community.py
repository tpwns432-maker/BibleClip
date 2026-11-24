"""웹판 커뮤니티 테스트 (docs/WEB_PLAN.md "커뮤니티").

    python -X utf8 tests/test_community.py

임시 폴더의 community.db 로 주제 · 글 · 댓글 · 공감 · 새 글 표시 · 권한 · 구절 링크를 확인하고,
서버 경로(POST /capi/<동작>)가 로그인 · 머리글 · 오류 코드를 지키는지 본다.
"""
import os
import shutil
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

DATA = tempfile.mkdtemp(prefix='bibleclip-community-')
os.environ['BIBLECLIP_DATA_DIR'] = DATA

from bibleclip.core.engine import Engine  # noqa: E402
from bibleclip.server.community import (  # noqa: E402
    Community, CommunityError, SEED_TOPICS, clean_source, clean_verse, find_refs)

A, B = 'alice', 'bob'
PSALMS = Engine.parse_reference('시 23:1')[0][0]
NAMES = {A: {'name': '앨리스'}, B: {'name': '밥'}}


def err(code, fn, *args):
    try:
        fn(*args)
    except CommunityError as e:
        assert e.code == code, (code, e.code, e.detail)
        return
    raise AssertionError(f'{code} 이어야 한다: {fn.__name__}{args[1:]}')


def check_store():
    c = Community(os.path.join(DATA, 'c.db'), names=lambda: NAMES, parse=Engine.parse_reference)

    # 처음 주제 4개(사용자 결정), 순서 · 감상 종류.
    ts = c.topics(A)
    assert [t['name'] for t in ts] == [n for n, _, _ in SEED_TOPICS] == ['말씀', '모임 서적', '성경 묵상', '자유']
    assert [t['source_kind'] for t in ts] == ['sermon', 'book', '', '']
    sermon, book, medit, free = (t['id'] for t in ts)
    # 다시 열어도 주제가 또 생기지 않는다.
    c.close()
    c = Community(os.path.join(DATA, 'c.db'), names=lambda: NAMES, parse=Engine.parse_reference)
    assert len(c.topics(A)) == 4

    # 주제: 만들기 · 이름 겹침 · 고치기 · 글 있으면 못 지움.
    tid = c.topic_save(B, {'name': '찬양', 'description': '좋은 찬양'})['id']
    err('exists', c.topic_save, A, {'name': '찬양'})
    err('exists', c.topic_save, A, {'id': tid, 'name': '자유'})
    err('invalid', c.topic_save, A, {'name': '  '})
    err('invalid', c.topic_save, A, {'name': 'x' * 31})
    c.topic_save(A, {'id': tid, 'name': '찬양 나눔', 'source_kind': 'nope'})
    t = [t for t in c.topics(A) if t['id'] == tid][0]
    assert t['name'] == '찬양 나눔' and t['source_kind'] == ''
    err('notfound', c.topic_delete, A, {'id': 999})

    # 글: 검사.
    err('invalid', c.post_save, A, {'topic_id': free, 'title': ' ', 'body': 'b'})
    err('invalid', c.post_save, A, {'topic_id': free, 'title': 't', 'body': 'x' * 20001})
    err('notfound', c.post_save, A, {'topic_id': 999, 'title': 't', 'body': 'b'})
    err('invalid', c.post_save, A, {'topic_id': 'x', 'title': 't', 'body': 'b'})
    err('invalid', c.post_save, A, {'topic_id': sermon, 'title': 't', 'body': 'b',
                                    'source': {'kind': 'sermon', 'title': 's', 'url': 'javascript:alert(1)'}})
    err('invalid', c.post_save, A, {'topic_id': sermon, 'title': 't', 'body': 'b',
                                    'source': {'kind': 'sermon', 'title': 's', 'date': '어제'}})
    # 감상 대상: 칸 밖은 버리고, 제목이 없으면 없는 것.
    assert clean_source({'kind': 'book', 'title': ' 고백록 ', 'by': '아우구스티누스', 'evil': '<x>'}) == \
        {'kind': 'book', 'title': '고백록', 'by': '아우구스티누스', 'part': ''}
    assert clean_source({'kind': 'book', 'title': ''}) is None
    assert clean_source({'kind': 'movie', 'title': 'x'}) is None

    # 앨리스가 글 → 밥에게 '새 글'. 앨리스 자신에겐 아님.
    body = '오늘은 요 3:16 과 😀 롬 8:28 을 읽었다 <script>alert(1)</script>'
    p1 = c.post_save(A, {'topic_id': sermon, 'title': '주일 설교', 'body': body,
                         'source': {'kind': 'sermon', 'title': '빛과 소금', 'by': '김목사',
                                    'date': '2026-11-22', 'url': 'https://example.com/v'}})['id']
    assert [t['unread'] for t in c.topics(B) if t['id'] == sermon] == [1]
    assert all(t['unread'] == 0 for t in c.topics(A))
    lst = c.posts(B, {'topic_id': sermon})['posts']
    assert lst[0]['is_new'] and lst[0]['author'] == {'id': A, 'name': '앨리스'}
    assert lst[0]['source']['title'] == '빛과 소금' and not lst[0]['mine']
    assert c.home(B)['unread'] == 1 and c.home(B)['recent'][0]['id'] == p1

    # 밥이 열면 읽음. 본문은 쓴 그대로(HTML 해석은 화면이 하지 않는다), 구절은 위치와 함께.
    p = c.post(B, {'id': p1})
    assert p['body'] == body and p['is_new'] is True       # 연 순간엔 아직 '새'(그 다음부터 아님)
    labels = [r['label'] for r in p['refs']]
    assert labels == ['요 3:16', '롬 8:28'], labels
    js = body.encode('utf-16-le')                            # JS 문자열 위치(이모지 = 2칸)
    assert [js[r['s'] * 2:r['e'] * 2].decode('utf-16-le') for r in p['refs']] == ['요 3:16', '롬 8:28']
    assert not c.posts(B, {'topic_id': sermon})['posts'][0]['is_new']
    assert c.home(B)['unread'] == 0

    # 댓글 · 답글 · 새 댓글.
    c1 = c.comment_save(B, {'post_id': p1, 'body': '아멘'})['id']
    c2 = c.comment_save(A, {'post_id': p1, 'parent_id': c1, 'body': '감사'})['id']
    c3 = c.comment_save(B, {'post_id': p1, 'parent_id': c2, 'body': '창1:1 도'})['id']
    # 댓글을 쓰면 그 글을 본 것 → 내가 쓰기 전 상대 댓글은 '새'가 아니다.
    assert c.posts(A, {})['posts'][0]['new_comments'] == 1      # 밥의 c3 하나
    assert c.posts(B, {})['posts'][0]['new_comments'] == 0
    view = c.post(A, {'id': p1})
    cl = {x['id']: x for x in view['comment_list']}
    assert not cl[c1]['is_new'] and not cl[c2]['is_new'] and cl[c3]['is_new']
    assert cl[c3]['parent_id'] == c2
    assert cl[c3]['refs'][0]['label'] == '창 1:1' and cl[c2]['mine']
    assert c.posts(A, {})['posts'][0]['new_comments'] == 0
    err('invalid', c.comment_save, A, {'post_id': p1, 'body': ''})
    err('notfound', c.comment_save, A, {'post_id': 999, 'body': 'x'})

    # 다른 글의 댓글에 답글 달기는 안 된다.
    p2 = c.post_save(B, {'topic_id': book, 'title': '고백록 1권', 'body': '읽었다',
                         'source': {'kind': 'book', 'title': '고백록', 'by': '아우구스티누스'}})['id']
    err('notfound', c.comment_save, A, {'post_id': p2, 'parent_id': c1, 'body': 'x'})

    # 권한: 남의 글 · 댓글은 못 고치고 못 지운다.
    err('forbidden', c.post_save, B, {'id': p1, 'topic_id': sermon, 'title': 'x', 'body': 'x'})
    err('forbidden', c.post_delete, B, {'id': p1})
    err('forbidden', c.comment_save, A, {'id': c1, 'body': 'x'})
    err('forbidden', c.comment_delete, A, {'id': c1})
    c.comment_save(B, {'id': c1, 'body': '아멘!'})
    assert [x for x in c.post(A, {'id': p1})['comment_list'] if x['id'] == c1][0]['edited_at']

    # 공감: 켜고 끄기, 누가 했는지.
    r = c.like(B, {'kind': 'post', 'id': p1})
    assert r == {'likes': 1, 'liked': True, 'likers': ['밥']}
    assert c.like(A, {'kind': 'post', 'id': p1})['likers'] == ['밥', '앨리스']
    assert c.like(B, {'kind': 'post', 'id': p1}) == {'likes': 1, 'liked': False, 'likers': ['앨리스']}
    assert c.like(A, {'kind': 'comment', 'id': c1})['liked']
    err('invalid', c.like, A, {'kind': 'topic', 'id': 1})
    err('notfound', c.like, A, {'kind': 'post', 'id': 999})

    # 정렬: 공감순 · 새 글순 · 최근 활동순(댓글이 달리면 위로).
    assert [p['id'] for p in c.posts(A, {'sort': 'likes'})['posts']][:1] == [p1]
    assert [p['id'] for p in c.posts(A, {'sort': 'new'})['posts']][:2] == [p2, p1]
    c.comment_save(A, {'post_id': p1, 'body': '하나 더'})
    assert [p['id'] for p in c.posts(A, {'sort': 'activity'})['posts']][:2] == [p1, p2]
    assert len(c.posts(A, {'limit': 1})['posts']) == 1 and c.posts(A, {'limit': 1})['more']
    assert c.posts(A, {'limit': 'x', 'offset': None})['posts']          # 틀린 숫자는 기본값

    # 같은 책 모아 보기(대소문자 · 앞뒤 공백 무시).
    p3 = c.post_save(A, {'topic_id': free, 'title': '다시 고백록', 'body': '...',
                         'source': {'kind': 'book', 'title': ' 고백록'}})['id']
    got = [p['id'] for p in c.posts(A, {'source_kind': 'book', 'source_title': '고백록 '})['posts']]
    assert sorted(got) == sorted([p2, p3]), got
    assert c.posts(A, {'source_kind': 'sermon', 'source_title': '고백록'})['posts'] == []

    # 지우기: 댓글 있는 글은 자리만 남고 댓글은 유지, 없는 글은 아예 사라진다.
    c.post_delete(A, {'id': p1})
    d = c.post(B, {'id': p1})
    assert d['deleted'] and d['title'] == '' and d['body'] == '' and d['source'] is None
    assert len(d['comment_list']) == 4
    err('notfound', c.comment_save, B, {'post_id': p1, 'body': 'x'})
    err('notfound', c.like, B, {'kind': 'post', 'id': p1})
    c.post_delete(A, {'id': p3})
    err('notfound', c.post, A, {'id': p3})
    # 답글이 달린 댓글은 '지운 댓글', 끝 댓글은 사라진다.
    c.comment_delete(A, {'id': c2})
    c.comment_delete(B, {'id': c3})
    left = {x['id']: x for x in c.post(B, {'id': p1})['comment_list']}
    assert left[c2]['deleted'] and left[c2]['body'] == '' and c3 not in left
    # 글이 있는 주제는 못 지우고, 빈 주제는 지운다.
    err('notempty', c.topic_delete, A, {'id': book})
    c.topic_delete(A, {'id': tid})
    assert tid not in [t['id'] for t in c.topics(A)]
    c.close()


def check_refs():
    p = Engine.parse_reference
    labels = lambda t: [r['label'] for r in find_refs(t, p)]   # noqa: E731
    assert labels('요한복음 3:16-18 과 창1:1, 롬 8:28') == ['요 3:16-18', '창 1:1', '롬 8:28']
    assert labels('말씀은요 3:16') == ['요 3:16']                 # 앞말이 붙어도
    assert labels('요한복음 3장 16절을 읽고') == ['요 3:16']
    assert labels('시편 23편 1절') == ['시 23:1']
    assert labels('고전 13:4~7') == ['고전 13:4-7']
    assert labels('John 3:16 and 1 John 4:8') == ['요 3:16', '요일 4:8']
    assert labels('at 3:30 meet, 3:16만, 오늘 23편 1절') == []    # 책 이름이 없으면 링크 아님


def check_verse():
    """성경 화면의 "함께 쓰기": 구절 범위가 달린 글, 장 표시, 미리 보기, 본문 인용."""
    def quote(uid, v):
        return {'version': uid, 'verses': [{'n': n, 'text': f't{n}'}
                                           for n in range(v['verse'], v['verse_end'] + 1)]}
    c = Community(os.path.join(DATA, 'v.db'), names=lambda: NAMES, verse_text=quote)
    med = c.default_topic()['id']
    assert [t['name'] for t in c.topics(A) if t['id'] == med] == ['성경 묵상']

    v = {'book': 500, 'chapter': 3, 'verse': 16, 'verse_end': 18}
    assert clean_verse(v) == dict(v, label='요 3:16-18')
    assert clean_verse({'book': 500, 'chapter': 3, 'verse': 16})['label'] == '요 3:16'
    assert clean_verse(None) is None
    for bad in ({'book': 999, 'chapter': 1, 'verse': 1}, {'book': 500, 'chapter': 3, 'verse': 18, 'verse_end': 16},
                {'book': 500, 'chapter': 0, 'verse': 1}, {'book': True, 'chapter': 1, 'verse': 1},
                {'book': 500, 'chapter': 3, 'verse': '16'}, 'x'):
        err('invalid', clean_verse, bad)

    p = c.post_save(A, {'topic_id': med, 'title': '독생자', 'body': '묵상', 'verse': v})['id']
    view = c.post(B, {'id': p})
    assert view['verse']['label'] == '요 3:16-18'
    assert view['verse_text']['version'] == B                     # 읽는 사람의 역본으로 인용
    assert [x['n'] for x in view['verse_text']['verses']] == [16, 17, 18]
    assert c.posts(B, {'topic_id': med})['posts'][0]['verse']['label'] == '요 3:16-18'

    # 장 표시: 그 장의 글만, 구절 순.
    p0 = c.post_save(B, {'topic_id': med, 'title': '앞 절', 'body': 'x',
                         'verse': {'book': 500, 'chapter': 3, 'verse': 1}})['id']
    assert [x['id'] for x in c.verse_posts(A, {'book': 500, 'chapter': 3})['posts']] == [p0, p]
    assert c.verse_posts(A, {'book': 500, 'chapter': 4})['posts'] == []
    assert c.verse_posts(A, {'book': 500, 'chapter': 3})['posts'][0]['is_new']     # 밥의 새 글
    err('invalid', c.verse_posts, A, {'book': 'x', 'chapter': 3})

    # 고칠 때 구절을 안 보내면 그대로, None 이면 뗀다.
    c.post_save(A, {'id': p, 'topic_id': med, 'title': '독생자2', 'body': '묵상'})
    assert c.post(A, {'id': p})['verse']['verse_end'] == 18
    c.post_save(B, {'id': p0, 'topic_id': med, 'title': '앞 절', 'body': 'x', 'verse': None})
    assert c.post(B, {'id': p0})['verse'] is None
    assert [x['id'] for x in c.verse_posts(A, {'book': 500, 'chapter': 3})['posts']] == [p]

    # 미리 보기.
    pv = c.verse_preview(A, {'verse': {'book': PSALMS, 'chapter': 23, 'verse': 1, 'verse_end': 6}})
    assert pv['verse']['label'] == '시 23:1-6' and len(pv['verse_text']['verses']) == 6
    err('invalid', c.verse_preview, A, {'verse': None})

    # 지운 글(댓글 있음 → 자리만)은 장 표시에서 빠진다.
    c.comment_save(B, {'post_id': p, 'body': '아멘'})
    c.post_delete(A, {'id': p})
    assert c.verse_posts(A, {'book': 500, 'chapter': 3})['posts'] == []
    assert c.post(A, {'id': p})['verse'] is None
    c.close()


def check_routes():
    from bibleclip.core.library import Library
    from bibleclip.server.accounts import Accounts, Throttle
    from bibleclip.server.app import create_app
    from bibleclip.server.webapi import WebHub
    acc = Accounts(DATA)
    acc.add(A, '앨리스', 'alice-pass-1')
    acc.add(B, '밥', 'bob-pass-22')
    com = Community(os.path.join(DATA, 'r.db'), names=acc.users, parse=Engine.parse_reference)
    app = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle(), com)
    H = {'X-BibleClip': '1'}
    anon = app.test_client()
    assert anon.post('/capi/topics', json={}, headers=H).status_code == 401
    a = app.test_client()
    a.post('/login', data={'id': A, 'password': 'alice-pass-1'})
    assert a.post('/capi/topics', json={}).status_code == 403              # 머리글 없음
    assert a.post('/capi/topics', data='x', headers=H).status_code == 400
    assert a.post('/capi/nope', json={}, headers=H).status_code == 404
    topics = a.post('/capi/topics', json={}, headers=H).get_json()['value']
    tid = topics[0]['id']
    r = a.post('/capi/post_save', json={'topic_id': tid, 'title': '제목', 'body': '요 1:1'}, headers=H)
    pid = r.get_json()['value']['id']
    r = a.post('/capi/post_save', json={'topic_id': tid, 'title': '', 'body': 'x'}, headers=H)
    assert r.status_code == 400 and r.get_json()['error'] == 'invalid'
    b = app.test_client()
    b.post('/login', data={'id': B, 'password': 'bob-pass-22'})
    assert b.post('/capi/home', json={}, headers=H).get_json()['value']['unread'] == 1
    r = b.post('/capi/post_delete', json={'id': pid}, headers=H)
    assert r.status_code == 403 and r.get_json()['error'] == 'forbidden'
    v = b.post('/capi/post', json={'id': pid}, headers=H).get_json()['value']
    assert v['refs'][0]['label'] == '요 1:1' and v['author']['name'] == '앨리스'
    assert b.post('/capi/post', json={'id': 9999}, headers=H).status_code == 404
    # 커뮤니티 없이 만든 앱(시험용)은 /capi 가 없다.
    app2 = create_app(WebHub(Library(), DATA), acc, 'k' * 64, Throttle())
    c2 = app2.test_client()
    c2.post('/login', data={'id': A, 'password': 'alice-pass-1'})
    assert c2.post('/capi/topics', json={}, headers=H).status_code == 404
    com.close()


if __name__ == '__main__':
    code = 0
    try:
        check_refs()
        check_store()
        check_verse()
        check_routes()
        print('test_community: ok')
    except Exception:
        import traceback
        traceback.print_exc()
        code = 1
    finally:
        shutil.rmtree(DATA, ignore_errors=True)
    sys.stdout.flush()
    os._exit(code)
