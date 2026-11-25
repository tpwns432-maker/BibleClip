"""영한 끊어 읽기(bibleclip/core/study.py) + 동봉 BSB(Strong) 테스트.

    python -X utf8 tests/test_study.py

저장소에 있는 것만 쓴다: BSB.SQLite3(CC0) · KJV+ · KRV · 개역한글S. 개역개정S 는 저작권 자료라 없다.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bibleclip.core.study import _match, align_units, align_verse, chunk_text, ends_clause, korean_units, korean_words  # noqa: E402


def unit():
    # 어절 얹기: 형태소 조각이 실제 어절로 모인다.
    words, occ = korean_words('태초에 하나님이 천지를 창조하시니라',
                              [('태초에', 'H7225'), ('하나님이', 'H430'), ('천', 'H8064'), ('지를', 'H776'),
                               ('창조하시니라', 'H1254')])
    assert words == ['태초에', '하나님이', '천지를', '창조하시니라']
    assert occ == [('H7225', 0), ('H430', 1), ('H8064', 2), ('H776', 2), ('H1254', 3)]
    # 본문과 어긋나는 조각은 건너뛴다.
    assert korean_words('가 나', [('없음', 'H1'), ('나', 'H2')])[1] == [('H2', 1)]

    en = [('In the beginning', 'H7225'), ('God', 'H430'), ('created', 'H1254'),
          ('the heavens', 'H8064'), ('and', 'H853'), ('the earth.', 'H776')]
    ko = '태초에 하나님이 천지를 창조하시니라'
    pieces = [('태초에', 'H7225'), ('하나님이', 'H430'), ('천', 'H8064'), ('지를', 'H776'), ('창조하시니라', 'H1254')]
    # Strong 조각 단위: 천 / 지를 이 따로 짝.
    assert align_verse(en, ko, pieces) == [('In the beginning', '태초에'), ('God', '하나님이'),
                                           ('created', '창조하시니라'), ('the heavens', '천'), ('and the earth.', '지를')]
    # 덩어리에는 조각마다 번호(화면이 눌러 사전을 띄운다).
    ch = align_units(en, ko, pieces)
    assert ch[3] == {'en': [['the heavens', 'H8064']], 'ko': [['천', 'H8064', 0]]}, ch[3]
    assert ch[4]['en'] == [['and', 'H853'], ['the earth.', 'H776']]
    assert align_verse(en, ko, pieces, fine=False) == [
        ('In the beginning God created the heavens and the earth.', '태초에 하나님이 천지를 창조하시니라')]

    # 창 1:2 — 어절 '공허하며' 가 공허(H922) + 하며(H1961 = was) 로 나뉘어 각자 짝(어절로 묶으면 was 가 공허를 가져갔다).
    en = [('Now the earth', 'H776'), ('was', 'H1961'), ('formless', 'H8414'), ('and void,', 'H922')]
    ko = '땅이 혼돈하고 공허하며'
    pieces = [('땅이', 'H776'), ('혼돈하고', 'H8414'), ('공허', 'H922'), ('하며', 'H1961')]
    assert align_verse(en, ko, pieces) == [('Now the earth', '땅이'), ('was', '하며'), ('formless', '혼돈하고'),
                                           ('and void,', '공허')]
    assert align_verse(en, ko, pieces, fine=False) == [('Now the earth was formless and void,', '땅이 혼돈하고 공허하며')]

    # 조각 · 띄어쓰기: 조각 안 띄어쓰기는 그대로, 덮이지 않은 글자도 조각.
    us = korean_units('오만한 자들의 자리에', [('오만한 자', 'H3887'), ('자리에', 'H4186')])
    assert [(u['t'], u['c']) for u in us] == [('오만한 자', 'H3887'), ('들의', None), ('자리에', 'H4186')], us
    # 같은 번호 개수가 다르면 위치가 가까운 쪽(영어 'surface' 2번 ↔ 한국어 '면' 1번 → 뒤쪽).
    assert _match([0.43, 0.86], [0.77]) == [(1, 0)] and _match([0.1], [0.2, 0.9]) == [(0, 0)]
    assert _match([0.1, 0.5], [0.2, 0.6]) == [(0, 0), (1, 1)]

    # 같은 번호는 차례대로(말씀 3번).
    en = [('In the beginning', 'G746'), ('was', 'G1510'), ('the Word,', 'G3056'), ('and', 'G2532'),
          ('the Word', 'G3056'), ('was with', 'G1510'), ('God,', 'G2316'), ('and', 'G2532'),
          ('the Word', 'G3056'), ('was God.', 'G2316')]
    ko = '태초에 말씀이 계시니라 이 말씀이 하나님과 함께 계셨으니 이 말씀은 곧 하나님이시니라'
    pieces = [('태초에', 'G746'), ('말씀이', 'G3056'), ('계시니라', 'G1510'), ('이', 'G3588'), ('말씀이', 'G3056'),
              ('하나님과', 'G2316'), ('함께 계셨으니', 'G1510'), ('이', 'G3588'), ('말씀은', 'G3056'),
              ('곧 하나님이시니라', 'G2316')]
    out = align_verse(en, ko, pieces, fine=False)
    assert [k for _, k in out] == ['태초에 말씀이 계시니라', '이 말씀이 하나님과 함께 계셨으니',
                                   '이 말씀은 곧 하나님이시니라'], out

    # KJV+ 식(문장부호가 다음 구절 앞) — 구절 모드에서 쉼표에서 끊긴다.
    en = [('the world', 'G2889'), (', that', 'G5620'), ('he gave', 'G1325')]
    out = align_verse(en, '세상을 주셨으니', [('세상을', 'G2889'), ('주셨으니', 'G1325')], fine=False)
    assert out == [('the world,', '세상을'), ('that he gave', '주셨으니')], out
    assert ends_clause('Son,') and ends_clause('light,”') and not ends_clause('Son')
    # 빈 입력.
    assert align_verse([], '가', []) == []
    print('unit: ok')


def real():
    from bibleclip.core.library import Library
    from bibleclip.webui.api import Api
    lib = Library()
    bsb = lib.dbs.get('BSB')
    assert bsb is not None, 'bible_versions/BSB.SQLite3 가 저장소에 있어야 한다(tools/make_bsb.py)'
    assert bsb.has_strongs and bsb.language == 'en'
    # 화면 본문은 태그 없이, 원전 분해는 번호와 함께.
    assert dict(lib.get_chapter('BSB', 10, 1))[1] == 'In the beginning God created the heavens and the earth.'
    inter = dict(lib.interlinear(500, 3, 'BSB'))[16]
    assert inter[:4] == [('For', 'G1063'), ('God', 'G2316'), ('so', 'G3779'), ('loved', 'G25')], inter[:4]
    n = bsb.conn.execute('SELECT COUNT(*) FROM verses').fetchone()[0]
    assert n > 31000, n
    assert bsb.conn.execute("SELECT COUNT(*) FROM verses WHERE text LIKE '%[%'").fetchone()[0] == 0

    src = lib.study_sources()
    assert src['en'][0]['name'] == 'BSB' and 'KJV+' in [x['name'] for x in src['en']]
    assert 'KRV' in [x['name'] for x in src['ko']]

    txt = lambda row: [list(chunk_text(c)) for c in row['chunks']]  # noqa: E731
    ch = lib.study_chapter(10, 1, ko='KRV')
    assert ch[0]['n'] == 1 and txt(ch[0]) == [['In the beginning', '태초에'], ['God', '하나님이'],
                                             ['created', '창조하시니라'], ['the heavens', '천'],
                                             ['and the earth.', '지를']], ch[0]
    assert txt(ch[1])[1] == ['was', '하고'] and txt(ch[1])[2] == ['formless', '혼돈']   # 개역한글S: 혼돈<H8414> 하고<H1961>
    john = lib.study_chapter(500, 3, ko='KRV', fine=False)[15]
    assert txt(john) == [
        ['For God so loved the world that He gave His one and only Son,',
         '하나님이 세상을 이처럼 사랑하사 독생자를 주셨으니'],
        ['that everyone who believes in Him shall not perish but have eternal life.',
         '이는 저를 믿는 자마다 멸망치 않고 영생을 얻게 하려 하심이니라']], john
    # 없는 이름이면 첫 후보로.
    assert txt(lib.study_chapter(10, 1, en='없음', ko='없음')[0])[0][0] == 'In the beginning'

    # 장 전체 품질: 한국어가 빈 덩어리가 드물어야 한다(측정값 ~1%).
    total = empty = 0
    for b, c in ((10, 1), (230, 23), (500, 3), (520, 8), (470, 5), (290, 53)):
        for row in lib.study_chapter(b, c, ko='KRV'):
            total += len(row['chunks'])
            empty += sum(1 for k in row['chunks'] if not k['ko'])
    assert total > 200 and empty / total < 0.01, (empty, total)   # 성경 전체 측정값 0.01%

    api = Api(lib)
    init = api.get_initial()
    assert init['study_sources']['en'][0]['name'] == 'BSB'
    assert 'BSB' in [s['name'] for s in init['interlin_sources']]
    r = api.get_study(10, 1, 'BSB', 'KRV', 'phrase')
    assert txt(r[0]) == [['In the beginning God created the heavens and the earth.', '태초에 하나님이 천지를 창조하시니라']]
    # 웹판 허용 목록.
    from bibleclip.server.webapi import ALLOWED
    assert 'get_study' in ALLOWED
    print(f'real: ok (빈 덩어리 {empty}/{total})')


if __name__ == '__main__':
    unit()
    real()
    print('test_study: ok')
