"""영한 뜻풀이(bibleclip/core/enko.py + original_lang/enko_dict.sqlite) 테스트.

    python -X utf8 tests/test_enko.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bibleclip.core.enko import EnKoDict, content_words, lemmas  # noqa: E402


def unit():
    # 원형 후보: 불규칙 → 복수 → 그대로 → 과거 → 그 밖.
    assert lemmas('was')[0] == 'be' and lemmas('said')[0] == 'say'
    assert lemmas('heavens')[0] == 'heaven' and lemmas('offerings')[0] == 'offering'
    assert lemmas('cried')[:2] == ['cried', 'cry']
    assert lemmas('wicked')[0] == 'wicked'            # -ed 낱말을 깎지 않는다(wick 아님)
    assert lemmas('righteous') == ['righteous']       # -ous 는 복수 아님
    assert 'di' not in lemmas('died') and 'die' in lemmas('died')   # 세 글자 미만 원형 없음
    assert lemmas('offering')[0] == 'offering'        # -ing 명사는 그대로 먼저
    # 구절의 머리말: 작은 낱말을 빼고 뒤에서부터.
    assert content_words('My covenant') == ['covenant']
    assert content_words('the heavens and the earth.')[0] == 'earth'
    # 파일이 없으면 조용히 None.
    assert EnKoDict(os.path.join(ROOT, 'nope.sqlite')).lookup('God') is None
    print('unit: ok')


def real():
    path = os.path.join(ROOT, 'original_lang', 'enko_dict.sqlite')
    d = EnKoDict(path)
    assert d.available, 'original_lang/enko_dict.sqlite 가 저장소에 있어야 한다(tools/make_enko.py)'
    assert 'kengdic' in d.info.get('general_source', '') and 'MPL' in d.info.get('license', '')

    def bible(q):
        r = d.lookup(q)
        return r and [k for k, _ in r['bible']]

    # 성경 속 번역(BSB ↔ 개역한글 낱말장)
    assert bible('My covenant')[0] == '언약'
    assert bible('the priest')[0] == '제사장'
    assert bible('the prophets')[0] == '선지자'
    assert bible('grace')[0] == '은혜'
    assert bible('offerings')[0] == '번제'
    assert bible('Moses')[0] == '모세'
    assert '하늘' in bible('the heavens')
    assert bible('wicked')[0] == '악인'
    # 일반 뜻(kengdic)
    r = d.lookup('righteous')
    assert r['word'] == 'righteous' and '의로운' in r['general']
    r = d.lookup('was')
    assert r['word'] == 'be' and r['bible'] == []      # be 동사는 낱말장 숫자 없이 일반 뜻만
    assert d.lookup('cried')['word'] == 'cry'
    assert d.lookup('xyzzyq') is None

    # 앱 경로: Api.lookup_english · get_initial.enko · 웹판 허용 목록
    from bibleclip.core.library import Library
    from bibleclip.webui.api import Api
    from bibleclip.server.webapi import ALLOWED
    api = Api(Library())
    assert api.get_initial()['enko'] is True
    assert api.lookup_english('My covenant')['bible'][0][0] == '언약'
    assert 'lookup_english' in ALLOWED
    print('real: ok')


if __name__ == '__main__':
    unit()
    real()
    print('test_enko: ok')
