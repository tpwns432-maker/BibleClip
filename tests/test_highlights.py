"""Headless test for the 형광펜 store (bibleclip.highlights.Highlights).

Run with:  python -X utf8 tests/test_highlights.py

Never touches userdata/user_highlights.json — every Highlights instance gets its
_save stubbed and starts from an empty dict, so the test is hermetic.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bibleclip.highlights import COLORS, MAX_RANGES, Highlights, _norm


def fresh():
    h = Highlights()
    h._save = lambda: True
    h.data = {}
    return h


def test_norm_sanitizes():
    # Junk in, nothing out.
    assert _norm(None) == []
    assert _norm(['nope', 42, {}]) == []
    assert _norm([{'s': 5, 'e': 5}]) == []          # empty span
    assert _norm([{'s': 3, 'e': 1}]) == []          # inverted
    assert _norm([{'s': -1, 'e': 4}]) == []         # negative offset
    assert _norm([{'s': 'a', 'e': 'b'}]) == []      # non-numeric

    # An unknown color falls back to the first pen rather than reaching the DOM.
    assert _norm([{'s': 0, 'e': 2, 'c': 'rainbow'}])[0]['c'] == COLORS[0]
    # Every stored range carries a timestamp even if the caller omitted one.
    assert _norm([{'s': 0, 'e': 2}])[0]['ts']
    print("_norm drops junk / clamps color OK")


def test_norm_sorts_and_deoverlaps():
    # The renderer walks ranges in one pass, so the store must hand back a
    # sorted, non-overlapping list no matter what order it arrives in.
    out = _norm([
        {'s': 10, 'e': 14, 'c': 'g'},
        {'s': 0, 'e': 4, 'c': 'y'},
    ])
    assert [(r['s'], r['e']) for r in out] == [(0, 4), (10, 14)], out

    # Overlap: the earlier range wins, the later one is trimmed. Its snippet no
    # longer describes the trimmed span, so it's cleared (the front-end re-fills
    # it on the next write).
    out = _norm([{'s': 0, 'e': 6, 'c': 'y', 't': 'abcdef'},
                 {'s': 3, 'e': 9, 'c': 'g', 't': 'defghi'}])
    assert [(r['s'], r['e']) for r in out] == [(0, 6), (6, 9)], out
    assert out[1]['t'] == '', out[1]
    # Fully swallowed → dropped entirely.
    out = _norm([{'s': 0, 'e': 9, 'c': 'y'}, {'s': 2, 'e': 5, 'c': 'g'}])
    assert [(r['s'], r['e']) for r in out] == [(0, 9)], out
    print("_norm sorts + de-overlaps OK")


def test_norm_caps():
    out = _norm([{'s': i * 2, 'e': i * 2 + 1} for i in range(MAX_RANGES + 40)])
    assert len(out) == MAX_RANGES, len(out)
    long_t = _norm([{'s': 0, 'e': 2, 't': 'x' * 5000}])[0]['t']
    assert len(long_t) == 400, len(long_t)
    print(f"_norm caps at {MAX_RANGES} ranges / 400-char snippet OK")


def test_crud_and_version_isolation():
    h = fresh()
    assert h.get(10, 1, 1, '개역개정') == []

    h.set_verse(10, 1, 1, '개역개정',
                [{'s': 4, 'e': 7, 't': '천지를', 'c': 'y'}])
    got = h.get(10, 1, 1, '개역개정')
    assert len(got) == 1 and got[0]['t'] == '천지를' and got[0]['c'] == 'y', got

    # ★ 역본 격리 — 같은 절이라도 다른 역본은 자기 것만 본다. 이게 깨지면 개역개정에
    # 칠한 형광펜이 KJV 셀의 엉뚱한 문자 위치에 찍힌다.
    assert h.get(10, 1, 1, 'KJV') == []
    h.set_verse(10, 1, 1, 'KJV', [{'s': 0, 'e': 3, 't': 'In ', 'c': 'b'}])
    assert len(h.get(10, 1, 1, '개역개정')) == 1
    assert h.get(10, 1, 1, 'KJV')[0]['c'] == 'b'

    # An empty list deletes the entry rather than storing [].
    assert h.set_verse(10, 1, 1, 'KJV', []) == []
    assert '10:1:1:KJV' not in h.data, h.data

    h.clear_verse(10, 1, 1, '개역개정')
    assert h.get(10, 1, 1, '개역개정') == []
    print("CRUD + per-version isolation OK")


def test_for_chapter():
    h = fresh()
    h.set_verse(10, 1, 1, '개역개정', [{'s': 0, 'e': 2, 'c': 'y'}])
    h.set_verse(10, 1, 3, '개역개정', [{'s': 1, 'e': 4, 'c': 'g'}])
    h.set_verse(10, 1, 1, 'KJV', [{'s': 0, 'e': 2, 'c': 'b'}])
    h.set_verse(10, 2, 1, '개역개정', [{'s': 0, 'e': 2, 'c': 'p'}])   # 다른 장
    h.set_verse(20, 1, 1, '개역개정', [{'s': 0, 'e': 2, 'c': 'p'}])   # 다른 책

    ch = h.for_chapter(10, 1, '개역개정')
    assert sorted(ch) == [1, 3], ch          # int verse keys, this chapter only
    assert ch[3][0]['c'] == 'g'
    assert sorted(h.for_chapter(10, 1, 'KJV')) == [1]
    assert h.for_chapter(10, 1, 'NIV') == {}

    # 장 경계: 1장 조회가 11·12장을 prefix 로 빨아들이면 안 된다.
    h.set_verse(10, 11, 5, '개역개정', [{'s': 0, 'e': 2, 'c': 'y'}])
    assert sorted(h.for_chapter(10, 1, '개역개정')) == [1, 3], h.for_chapter(10, 1, '개역개정')
    print("for_chapter scoping (chapter/book/version boundaries) OK")


def test_version_name_with_colon():
    # The key is book:chapter:verse:version, so a ':' inside the version name
    # must not shift the field split (split(':', 3) keeps the tail intact).
    h = fresh()
    h.set_verse(10, 1, 1, 'odd:name', [{'s': 0, 'e': 2, 'c': 'y'}])
    assert sorted(h.for_chapter(10, 1, 'odd:name')) == [1]
    assert h.for_chapter(10, 1, 'odd') == {}
    assert h.all()[0]['version'] == 'odd:name', h.all()
    print("version names containing ':' survive the key split OK")


def test_all_ordering():
    h = fresh()
    h.set_verse(470, 3, 16, '개역개정', [{'s': 0, 'e': 2, 'c': 'y'}])
    h.set_verse(10, 1, 1, '개역개정', [{'s': 5, 'e': 7, 'c': 'g'},
                                       {'s': 0, 'e': 2, 'c': 'y'}])
    flat = h.all()
    assert len(flat) == 3, flat
    # canonical bible order, then version, then offset within the verse
    assert [(f['book'], f['verse'], f['s']) for f in flat] == \
        [(10, 1, 0), (10, 1, 5), (470, 16, 0)], flat
    print("all() bible-order flattening OK")


def test_corrupt_file_is_fail_soft(tmpdir):
    # A corrupt or hostile store must degrade to "no highlights", never raise —
    # Library.__init__ constructs this at boot, so an exception here is fatal.
    import bibleclip.highlights as hlmod

    real_dir = hlmod.get_userdata_dir
    hlmod.get_userdata_dir = lambda: tmpdir
    try:
        path = os.path.join(tmpdir, hlmod.HIGHLIGHTS_FILE)

        for label, blob in [
            ('truncated json', '{"10:1:1:개역개정": [{"s": 0,'),
            ('not an object', '["nope"]'),
            ('empty file', ''),
            ('binary junk', '\x00\x01\x02'),
        ]:
            with open(path, 'w', encoding='utf-8') as f:
                f.write(blob)
            assert Highlights().data == {}, label

        # A well-formed file with one poisoned entry keeps the good entries and
        # drops the bad one — _load is the gate that guarantees for_chapter only
        # ever hands the renderer lists.
        with open(path, 'w', encoding='utf-8') as f:
            f.write('{"10:1:1:개역개정": "not-a-list",'
                    ' "10:1:2:개역개정": [{"s": 0, "e": 2, "c": "y"}]}')
        h = Highlights()
        assert '10:1:1:개역개정' not in h.data, h.data
        assert sorted(h.for_chapter(10, 1, '개역개정')) == [2], h.for_chapter(10, 1, '개역개정')

        # An unwritable path must not raise either — the highlight just doesn't
        # persist (the screen already shows it; fail-soft like notes.py).
        os.remove(path)
        os.mkdir(path)          # a directory where the file should be
        h2 = Highlights()
        assert h2.data == {}
        assert h2.set_verse(10, 1, 1, '개역개정', [{'s': 0, 'e': 2, 'c': 'y'}])
    finally:
        hlmod.get_userdata_dir = real_dir
    print("fail-soft on corrupt file / unwritable path OK")


if __name__ == '__main__':
    test_norm_sanitizes()
    test_norm_sorts_and_deoverlaps()
    test_norm_caps()
    test_crud_and_version_isolation()
    test_for_chapter()
    test_version_name_with_colon()
    test_all_ordering()
    with tempfile.TemporaryDirectory() as td:
        test_corrupt_file_is_fail_soft(td)
    print("\nALL HIGHLIGHT TESTS PASSED")
