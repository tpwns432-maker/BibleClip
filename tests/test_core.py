"""Headless smoke test for the UI-agnostic core (bibleclip.core.library.Library).

Run with:  python -X utf8 tests/test_core.py

No test framework needed. This NEVER calls save_settings (which would write the
user's real settings file) — it only reads. Exits via os._exit(0) to avoid any
interpreter-shutdown side effects.
"""
import os
import sys

# Make the repo root importable when run as `python tests/test_core.py`.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bibleclip.core.library import Library


def main():
    lib = Library()
    assert lib.dbs, "no bible databases loaded — run from the repo root"
    print(f"loaded versions: {sorted(lib.dbs)}")

    # 1) reference parsing: 창 1:1 -> book 10 (창세기), chapter 1, verse [1]
    refs = lib.parse_reference('창 1:1')
    assert refs, "창 1:1 did not parse"
    book_num, short, long_, chapter, verses = refs[0]
    assert book_num == 10 and chapter == 1 and verses == [1], refs[0]
    print(f"parse_reference('창 1:1') -> {refs[0]}")

    # 2) chapter fetch (prefer KRV, else first loaded version)
    version = 'KRV' if 'KRV' in lib.dbs else sorted(lib.dbs)[0]
    chap = lib.get_chapter(version, 10, 1)
    assert chap and chap[0][0] == 1 and chap[0][1].strip(), chap[:1]
    print(f"get_chapter({version!r},10,1) -> {len(chap)} verses; v1: {chap[0][1][:24]}…")

    # 3) build_output: a real reference yields a 'reference' result with text
    out = lib.build_output('요 3:16')
    assert out and out['kind'] == 'reference' and out['text'].strip(), out
    print(f"build_output('요 3:16') -> kind=reference, n_parts={out['n_parts']}")
    print(f"   text: {out['text'][:48]}…")

    # 4) build_output: '#keyword' is a keyword query
    kw = lib.build_output('#사랑')
    assert kw and kw['kind'] == 'keyword' and kw['keyword'] == '사랑', kw
    print(f"build_output('#사랑') -> {kw}")

    # 5) build_output: garbage yields None
    assert lib.build_output('점심 뭐먹지') is None
    print("build_output('점심 뭐먹지') -> None")

    # 6) search returns hits
    hits = lib.search(version, '태초')
    assert hits, "search('태초') returned nothing"
    print(f"search({version!r},'태초') -> {len(hits)} hits; first: {hits[0][:3]}")

    # 7) Strong's lexicon lookup (only if original-language data is present)
    if lib.lexicon_ko:
        entry = lib.lookup_strong('H3068')
        assert entry, "lookup_strong('H3068') returned nothing"
        print(f"lookup_strong('H3068') -> {len(entry)} chars of markup")
        inter = lib.interlinear(10, 1)
        assert inter and inter[0][1], "interlinear(10,1) empty"
        print(f"interlinear(10,1) -> {len(inter)} verses; "
              f"v1 first word/code: {inter[0][1][0]}")
    else:
        print("(original_lang data absent — skipping lexicon/interlinear checks)")

    # 8) discontinuous comma references (6차 작업 1): "요 1:1-2,4-6" merges to a
    #    single sorted verse set with no gaps lost.
    refs = lib.parse_reference('요 1:1-2,4-6')
    assert refs and refs[0][4] == [1, 2, 4, 5, 6], refs
    print(f"parse_reference('요 1:1-2,4-6') -> verses {refs[0][4]}")
    assert lib.parse_reference('요 1:2,9')[0][4] == [2, 9]

    # 9) inline output inserts ' // ' between non-consecutive verse groups, and
    #    NOT between consecutive verses (6차 작업 2).
    saved_mode = lib.settings['output_mode']
    saved_hdr = lib.settings['show_version_header']
    lib.settings['output_mode'] = 'inline'
    lib.settings['show_version_header'] = False
    try:
        gap = lib.build_output('요 1:1-2,4')
        assert gap and ' // ' in gap['text'], gap
        cont = lib.build_output('요 1:1-3')
        assert cont and ' // ' not in cont['text'], cont
    finally:
        lib.settings['output_mode'] = saved_mode
        lib.settings['show_version_header'] = saved_hdr
    print("inline output: '요 1:1-2,4' has ' // ', '요 1:1-3' does not")

    # 10) reverse Strong's search (7차 Phase 2 원어 엔진): the tagged KRV finds
    #     verses by Strong's code, with tag-stripped clean text. H7225(레쉬트) is
    #     the first word of 창 1:1.
    if lib.bethlehem_strongs:
        ss = lib.search_strong('H7225')
        assert any(h['book_num'] == 10 and h['chapter'] == 1 and h['verse'] == 1
                   for h in ss), f"H7225 should hit 창 1:1 ({len(ss)} hits)"
        assert ss and '<W' not in ss[0]['text'], "clean text must have no <W..> tags"
        print(f"search_strong('H7225') -> {len(ss)} verses incl 창 1:1; clean text OK")
    else:
        print("(개역한글S absent — skipping reverse Strong's search check)")

    # 11) business guard (Phase 1): user config defaults to permissive (premium),
    #     and the usage ping is fail-open (url=None → instant no-op, never raises).
    from bibleclip.userconfig import load_user_config, is_premium
    assert load_user_config().get('is_premium') is True
    assert is_premium() is True and lib.is_premium is True
    from bibleclip.usage import ping_usage_async
    ping_usage_async(url=None)  # must not raise / not touch the network
    print("business guard: is_premium default True; usage ping fail-open OK")

    # 12) Kiwi 형태소 검색 (9차 Phase 2): tokenize_keywords strips 조사/어미 and
    #     keeps content morphemes; a query whose words are non-contiguous (so the
    #     exact substring pass misses) is still recovered by the morpheme-AND
    #     pass. Fail-soft — when kiwipiepy is absent we assert the no-op contract
    #     and trigram remains the fallback.
    from bibleclip import morph
    if morph.available():
        toks = morph.tokenize_keywords('태초에 하나님이 천지를')
        assert '태초' in toks and '하나님' in toks and '천지' in toks, toks
        assert '에' not in toks and '이' not in toks and '를' not in toks, toks
        # '하나님 창조' is not a contiguous (despaced) substring of 창 1:1, so the
        # exact pass fails; morpheme AND (["하나님","창조"]) still reaches it.
        mh = lib.search(version, '하나님 창조')
        assert any(b == 10 and c == 1 and v == 1 for (b, c, v, t) in mh), \
            f"morpheme search should reach 창 1:1 ({len(mh)} hits)"
        print(f"kiwi tokenize '태초에 하나님이 천지를' -> {toks}")
        print(f"   morpheme search '하나님 창조' -> {len(mh)} hits incl 창 1:1 OK")
    else:
        assert morph.tokenize_keywords('아무 문장') == []
        print("(kiwipiepy absent — morpheme search no-ops, trigram fallback) OK")

    print("\nALL CORE CHECKS PASSED ✅")


if __name__ == '__main__':
    main()
    sys.stdout.flush()
    os._exit(0)
