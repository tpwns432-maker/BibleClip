"""영어공부 의미 덩어리 표(core/study_chunks.py) — 짝 맞추기 규칙 · 표 읽고 쓰기 · 앱 연결.

python -X utf8 tests/test_study_chunks.py"""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from bibleclip.core.study_chunks import StudyChunks, align_chunks, glued_flags, write_table  # noqa: E402


def txt(chunks):
    return [(' '.join(w for w, _ in c['en']), ''.join((' ' if g else '') + t for t, _, g in c['ko']).strip())
            for c in chunks]


def zeros(e, k, v=0.0):
    return [[v] * k for _ in range(e)]


def unit():
    # 원어 번호는 강제: 모델 유사도가 엉뚱해도(영 ↔ hovering 높음) 번호가 같은 구절 머리말과 짝.
    en = [['the', 'H7307', 0], ['Spirit', 'H7307', 0], ['was', 'H7363', 1], ['hovering', 'H7363', 1]]
    ko = [['영은', 'H7307', 0], ['운행하시니라', 'H7363', 1]]
    cos = zeros(4, 2)
    cos[3][0] = 0.9
    out = align_chunks(en, ko, '영은 운행하시니라', [0, 2], cos, zeros(4, 2))
    assert txt(out) == [('the Spirit', '영은'), ('was hovering', '운행하시니라')], out
    # 영어 번호는 구절 머리말에만(누른 낱말의 사전), 한국어 조각은 번호 그대로.
    assert out[0]['en'] == [['the', None], ['Spirit', 'H7307']] and out[0]['ko'] == [['영은', 'H7307', 0]]

    # 앞 조각에 붙은 조각(띄어쓰기 없음)은 늘 앞 조각을 따른다: 시기+와 → 한 덩어리, 앞 띄움 0.
    en = [['jealousy', 'G2205', 0], ['and', 'G2532', 1], ['strife', 'G2052', 2]]
    ko = [['시기', 'G2205', 0], ['와', 'G2532', 0], ['다툼이', 'G2052', 1]]
    out = align_chunks(en, ko, '시기와 다툼이', [0, 1], zeros(3, 3), zeros(3, 3))
    assert txt(out) == [('jealousy', '시기와'), ('and strife', '다툼이')], out
    assert out[0]['ko'] == [['시기', 'G2205', 0], ['와', 'G2532', 0]]
    assert glued_flags('시기와 다툼이', ko) == [False, True, False]

    # 같은 번호가 여러 번이고 개수가 같으면 차례대로(heart 둘 ↔ 마음 둘). 짝 없는 '또'는 앞 조각을 따른다.
    en = [['heart', 'H3820', 0], ['and', None, 1], ['heart', 'H3820', 2]]
    ko = [['마음을', 'H3820', 0], ['또', None, 1], ['마음을', 'H3820', 2]]
    out = align_chunks(en, ko, '마음을 또 마음을', [0, 1], zeros(3, 3), zeros(3, 3))
    assert txt(out) == [('heart', '마음을 또'), ('and heart', '마음을')], out

    # 한국어가 빈 영어 덩어리는 다음 덩어리에 합친다(Moses / went out ↔ 다시 나가니).
    en = [['Moses', 'H4872', 0], ['went', 'H3318', 1], ['out', 'H3318', 1]]
    ko = [['다시', None, 0], ['나가니', 'H3318', 1]]
    out = align_chunks(en, ko, '다시 나가니', [0, 1], zeros(3, 2), zeros(3, 2))
    assert txt(out) == [('Moses went out', '다시 나가니')], out

    # 번호 없는 조각은 모델 짝(유사도 0.5 이상) — 아니면 이웃을 따른다.
    en = [['In', None, 0], ['the', None, 0], ['beginning', 'H7225', 0], ['God', 'H430', 1]]
    ko = [['태초에', None, 0], ['하나님이', 'H430', 1]]
    cos = zeros(4, 2)
    cos[2][0] = 0.8
    dot = zeros(4, 2, -5.0)
    dot[2][0] = 10.0
    out = align_chunks(en, ko, '태초에 하나님이', [0, 3], cos, dot)
    assert txt(out) == [('In the beginning', '태초에'), ('God', '하나님이')], out

    # 한국어가 없으면 영어 통째로 한 덩어리, 영어가 없으면 빈 목록.
    assert txt(align_chunks(en, [], '', [0, 3], [], [])) == [('In the beginning God', '')]
    assert align_chunks([], ko, '태초에 하나님이', [], [], []) == []

    # 표 쓰고 읽기.
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 't.sqlite')
        write_table(p, {'en': 'BSB', 'ko': 'KRV'}, {(10, 1): {1: out, 2: []}})
        t = StudyChunks(p)
        assert t.available and t.info['en'] == 'BSB'
        assert t.chapter(10, 1) == {1: out, 2: []} and t.chapter(10, 2) is None
        t._con.close()
    assert not StudyChunks(os.path.join(ROOT, '없는파일.sqlite')).available
    print('unit: ok')


def real():
    from bibleclip.core.library import Library
    from bibleclip.webui.api import Api
    lib = Library()
    api = Api(lib)
    if lib.study_table('BSB', 'KRV') is None:
        print('real: 건너뜀(original_lang/study_chunks_BSB_KRV.sqlite 없음)')
        return
    # 기본(mode 없음) = 의미 덩어리 표.
    r = api.get_study(10, 1, 'BSB', 'KRV')
    assert r[0]['n'] == 1 and len(r) == 31, len(r)
    first = txt(r[0]['chunks'])
    assert first[0] == ('In the beginning', '태초에'), first
    assert any('created' in e for e, _ in first) and all(k for _, k in first), first
    # 표는 성경 전체(31,000절 넘게) — 계시록 끝 장까지.
    assert len(api.get_study(730, 22, 'BSB', 'KRV')) == 21
    # 다른 영어 역본(KJV+)은 표가 없어 낱말 단위로.
    assert lib.study_table('KJV+', 'KRV') is None
    kj = api.get_study(10, 1, 'KJV+', 'KRV')
    assert kj and kj[0]['chunks'], kj[:1]
    # 낱말 · 구절 모드는 그대로 남는다(API).
    assert txt(api.get_study(10, 1, 'BSB', 'KRV', 'phrase')[0]['chunks']) == [
        ('In the beginning God created the heavens and the earth.', '태초에 하나님이 천지를 창조하시니라')]
    info = lib.study_table('BSB', 'KRV').info
    assert int(info['verses']) > 31000, info
    print(f'real: ok ({info["verses"]}절, {info["made"]})')


if __name__ == '__main__':
    unit()
    real()
    print('test_study_chunks: ok')
