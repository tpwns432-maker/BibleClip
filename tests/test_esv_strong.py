"""ESV Strong 정렬 도구(tools/make_esv_strong.py) 테스트.

    python -X utf8 tests/test_esv_strong.py

ESV 는 저작권 자료라 저장소에 없다 → 공개 자료(BSB=CC0 · KJV+=PD)만 쓴다. 종단 시험은 태그를 지운
KJV 를 BSB 로 태깅해 본다(도구의 --eval 과 같은 방식, 창세기 1장만이라 몇 초).
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'tools'))

import make_esv_strong as m  # noqa: E402


def unit():
    # 어간: 활용형은 모으고, 기능어는 그대로(these 가 thes 로 바뀌면 기능어 목록을 빠져나간다).
    assert m.stem('loved') == m.stem('loves') == m.stem('loving')
    assert [m.stem(w) for w in ('these', 'those', 'there', 'this')] == ['these', 'those', 'there', 'this']
    assert m.stem("God’s") == m.stem('God')

    # 조각: 글 없는 태그는 앞 조각에 붙고, 각주 · 해설은 본문이 아니다.
    segs = m.segments('God<S>430</S> created<S>1254</S> <S>853</S> the heaven<S>8064</S><n>note words</n>.')
    assert segs == [(['God'], [430]), (['created'], [1254, 853]), (['the', 'heaven'], [8064])]

    # 단어 위치: 태그 · 각주 안 글자는 단어가 아니다.
    raw = '<pb/><J>In the<f>ⓐ</f> beginning God created</J>'
    words = m.plain_words(raw)
    assert [w for w, _ in words] == ['In', 'the', 'beginning', 'God', 'created']

    # 그리기: 원래 표기 보존, 같은 번호가 이어진 무리는 마지막 단어 뒤에 한 번, 신약 번호도 숫자만.
    pred = [(7225, 1), (m.NULL, 0), (7225, 1), (430, 1), (1254, 1)]
    assert m.render(raw, words, pred) == \
        '<pb/><J>In<S>7225</S> the<f>ⓐ</f> beginning<S>7225</S> God<S>430</S> created<S>1254</S></J>'
    pred = [(m.NULL, 0)] * 2 + [(7225, 1)] * 1 + [(m.NULL, 0)] + [(m.G_OFF + 2316, 1)]
    assert m.render(raw, words, pred).endswith('beginning<S>7225</S> God created<S>2316</S></J>')

    # KJV+ 활용형 번호 → BSB 원형 번호(신약만; 구약 같은 숫자는 그대로).
    conv = m.convert_kjv({(500, 1, 1): [(['my'], [3450]), (['is'], [2076])],
                          (10, 1, 1): [(['x'], [3450])]})
    assert conv[(500, 1, 1)] == [(['my'], [1473]), (['is'], [1510])]
    assert conv[(10, 1, 1)] == [(['x'], [3450])]

    # 기능어 허용표: 혼자 그 번호를 받은 말만.
    sup = [(['for'], [3588])] * 3 + [(['the', 'land'], [776])] * 9
    allow = m.stop_allow(sup)
    assert ('for', 3588) in allow and ('the', 776) not in allow


def end_to_end():
    bsb, kjv = m.load(m.BSB), m.load(m.KJVP)
    keys = [k for k in bsb if k[0] == 10 and k[1] == 1]
    bsb_segs = {k: m.segments(bsb[k]) for k in keys}
    targets = [m.Target(k, [w for ws, _ in m.segments(kjv[k]) for w in ws], bsb_segs[k]) for k in keys]
    sup = m.supervised(bsb_segs)
    t = m.train(sup, targets, iters=3, log=lambda *_: None)
    allow = m.stop_allow(sup)
    got = {}
    for tg in targets:
        for w, (k, _) in zip(tg.words, m.decode(t, tg, allow)):
            got.setdefault((tg.key[2], w), k)
    # 창 1:1 In the beginning God created the heaven and the earth.
    assert got[(1, 'God')] == 430 and got[(1, 'created')] == 1254 and got[(1, 'earth')] == 776
    assert got[(1, 'beginning')] == 7225 and got[(1, 'heaven')] == 8064
    assert got[(1, 'the')] == m.NULL          # 관사는 앞 · 뒤 구절에 묶인다
    # 창 1:3 And God said, Let there be light: and there was light.
    assert got[(3, 'said')] == 559 and got[(3, 'light')] == 216
    # 창 1:2 KJV 'moved' ↔ BSB 'hovering' — 같은 단어가 아니어도 위치 · 남은 번호로 맞춘다.
    assert got[(2, 'moved')] == 7363


if __name__ == '__main__':
    unit()
    end_to_end()
    print('ok')
