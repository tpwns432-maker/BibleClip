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

    # 13) v1.0.5 Phase 1 — 한국어 정규화기(조사 제거) + KRV 역색인 빌더. 순수 파이썬,
    #     형태소기/사전 불필요. 색인·검색어가 같은 tokenize 를 공유(대칭).
    from bibleclip import korean
    assert korean.tokenize('태초에 하나님이 천지를 창조하시니라') == \
        ['태초', '하나님', '천지', '창조하시니라'], \
        korean.tokenize('태초에 하나님이 천지를 창조하시니라')
    assert korean.strip_particle('하나님이') == '하나님'
    assert korean.strip_particle('천지를') == '천지'        # 합성어 보존
    assert korean.strip_particle('창조하시니라') == '창조하시니라'  # 어미는 안 뗌
    assert korean.tokenize('그 또한 하나님') == ['하나님']   # 불용어 제외
    print("korean.tokenize/strip_particle OK")

    if 'KRV' in lib.dbs:
        inv = lib.dbs['KRV'].inverted_index()
        assert inv and isinstance(inv, dict), "inverted index empty"
        # 창 1:1 = (10,1,1) 이 핵심 원형 토큰들에 색인되어야 한다
        for tok in ('태초', '하나님', '천지'):
            assert (10, 1, 1) in inv.get(tok, set()), f"'{tok}' 색인에 창1:1 누락"
        both = inv['하나님'] & inv['천지']           # AND 교집합
        assert (10, 1, 1) in both, "AND(하나님&천지) 교집합에 창1:1 누락"
        # 어간 부분일치(Phase 2 예고): 창1:1 은 '창조'가 아니라 '창조하시니라'로만 색인됨
        # → 정확 매칭 '창조'로는 창1:1 미발견(Phase 2 부분일치가 회수할 대상)
        assert (10, 1, 1) in inv.get('창조하시니라', set())
        assert (10, 1, 1) not in inv.get('창조', set())
        print(f"KRV 역색인 OK — 고유키 {len(inv)}개, '하나님' {len(inv['하나님'])}절, "
              f"하나님&천지 {len(both)}절")

        # 14) v1.0.5 Phase 3 — 스코어링: smart_search 결과가 점수 내림차순 정렬 +
        #     밀집도/길이 반영(같은 매칭수면 인접·짧은 절이 상위).
        db = lib.dbs['KRV']
        toks = korean.tokenize('하나님 천지')
        rows = db.smart_search('하나님 천지', mode='and')
        scores = [db._score((b, c, v), toks) for b, c, v, t in rows]
        assert scores == sorted(scores, reverse=True), "결과가 점수 내림차순이 아님"
        # 밀집도+길이 단위검증: 같은 2단어 매칭이라도 인접·짧은 절 > 멀고·긴 절
        db._verse_tokens[(0, 0, 1)] = ['하나님', '천지']                 # 인접·짧음
        db._verse_tokens[(0, 0, 2)] = ['하나님'] + ['x'] * 8 + ['천지']   # 멀고·김
        hi = db._score((0, 0, 1), toks)
        lo = db._score((0, 0, 2), toks)
        assert hi > lo, (hi, lo)
        assert any((b, c, v) == (10, 1, 1) for b, c, v, t in rows[:5]), "창1:1 상위권 아님"
        print(f"스코어링 OK — 정렬 단조감소, 밀집/길이 {hi:.1f}>{lo:.1f}, 창1:1 상위권")
    else:
        print("(KRV 없음 — 역색인/스코어링 검증 스킵)")

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
        # 다중 키워드(스페이스로 엮은 3단어) 검색이 죽지 않고 결과를 내는지 — 소장님
        # 실창에서 "태초 말씀 하나님" 류가 크래시한 회귀 가드. exact 를 빗나가
        # 형태소 AND 경로를 타며, 세 단어를 모두 품은 요 1:1(book 500)을 찾아야 함.
        mw = lib.search(version, '태초 말씀 하나님')
        assert any(b == 500 and c == 1 and v == 1 for (b, c, v, t) in mw), \
            f"multi-keyword '태초 말씀 하나님' should reach 요 1:1 ({len(mw)} hits)"
        print(f"   multi-keyword '태초 말씀 하나님' -> {len(mw)} hits incl 요 1:1 OK")
    else:
        assert morph.tokenize_keywords('아무 문장') == []
        print("(kiwipiepy absent — morpheme search no-ops, trigram fallback) OK")

    alias_check(lib)
    settings_persist_check()

    print("\nALL CORE CHECKS PASSED ✅")


def settings_persist_check():
    """Settings must survive a save → reload round-trip (v1.1.4 fix). load_settings
    only accepts keys present in DEFAULT_SETTINGS and used to clamp the font to 30,
    so a big font + reading_font/ui_lang/auto_copy_top_result silently reverted on
    restart. Redirects the settings file to a temp path so the real one is safe."""
    import tempfile
    import bibleclip.core.library as libmod
    from bibleclip.core.library import Library

    orig_base, orig_file = libmod.BASE_DIR, libmod.SETTINGS_FILE
    libmod.BASE_DIR = tempfile.mkdtemp()
    libmod.SETTINGS_FILE = 'test_settings.json'
    try:
        # the previously-dropped keys must exist in the defaults now
        for k in ('ui_lang', 'reading_font', 'auto_copy_top_result'):
            assert k in Library.DEFAULT_SETTINGS, k
        lib = Library()
        lib.settings['viewer_font_size'] = 80          # big-screen / 방송 송출
        lib.settings['reading_font'] = 'MyBroadcastFont'
        lib.settings['ui_lang'] = 'en'
        lib.settings['auto_copy_top_result'] = True
        lib.save_settings()
        r = Library().settings                          # fresh load from disk
        assert r['viewer_font_size'] == 80, r['viewer_font_size']
        assert r['reading_font'] == 'MyBroadcastFont', r['reading_font']
        assert r['ui_lang'] == 'en', r['ui_lang']
        assert r['auto_copy_top_result'] is True, r['auto_copy_top_result']
        # clamp matches set_font_size (8–400), not the stale 30
        lib2 = Library()
        lib2.settings['viewer_font_size'] = 9999
        lib2.save_settings()
        assert Library().settings['viewer_font_size'] == 400
        print("settings persistence (font80/reading_font/ui_lang/auto_copy; clamp=400) OK")
    finally:
        libmod.BASE_DIR, libmod.SETTINGS_FILE = orig_base, orig_file


def alias_check(lib):
    """User alias overrides (v1.0.7 약칭 UI 백엔드 + 파서 확장).

    Redirects the override file to a temp path so the user's real
    bible_versions/aliases_override.json is never touched."""
    import tempfile
    from bibleclip.core.engine import Engine

    def tup(refs):
        if not refs:
            return None
        b, _, _, c, vs = refs[0]
        return (b, c, vs[0] if vs else None)

    # ---- regression: parser unchanged when no alias is registered ----
    # A leading digit before a Korean book is dropped (old behavior) UNLESS the
    # token is a registered alias — so these must be untouched by the new path.
    assert tup(lib.parse_reference('창 1:1')) == (10, 1, 1)
    assert tup(lib.parse_reference('1요 5:4')) == (500, 5, 4)   # unreg → 요 5:4
    assert tup(lib.parse_reference('요15:4')) == (500, 15, 4)   # trailing digit kept as chapter
    assert tup(lib.parse_reference('1 John 5:4')) == (690, 5, 4)  # built-in numbered book

    tmp = os.path.join(tempfile.mkdtemp(), 'aliases_override.json')
    lib._alias_overrides_path = lambda: tmp

    # ---- number-rule validation ----
    assert lib.add_alias_override('1요', 690)['ok'] is True       # leading digit OK
    assert lib.add_alias_override('창조기', 10)['ok'] is True       # custom Korean OK
    assert lib.add_alias_override('요1', 500)['ok'] is False       # trailing digit rejected
    assert lib.add_alias_override('벧1', 670)['ok'] is False       # trailing digit rejected
    assert lib.add_alias_override('1요2', 690)['ok'] is False      # middle digit rejected
    assert lib.add_alias_override('   ', 10)['ok'] is False        # empty rejected
    assert lib.add_alias_override('테스트', 99999)['ok'] is False    # invalid book rejected
    print("alias validation (앞숫자만 허용·중간/끝 숫자 거부) OK")

    # ---- registered aliases now parse (book_aliases rebuilt) ----
    assert tup(lib.parse_reference('1요 5:4')) == (690, 5, 4), lib.parse_reference('1요 5:4')
    assert tup(lib.parse_reference('1요 1장 4절')) == (690, 1, 4)
    assert tup(lib.parse_reference('창조기 1:1')) == (10, 1, 1)
    aliases = {a['alias'] for a in lib.list_alias_overrides()}
    assert aliases == {'1요', '창조기'}, aliases
    print(f"alias parse: 1요→요한1서, 창조기→창세기 OK ({sorted(aliases)})")

    # ---- delete reverts to old behavior ----
    assert lib.remove_alias_override('1요')['ok'] is True
    assert tup(lib.parse_reference('1요 5:4')) == (500, 5, 4)  # back to 요 5:4
    assert lib.remove_alias_override('없는약칭')['ok'] is False

    # ---- _canon memoization sanity ----
    assert Engine._canon(10)[1] == '창' and Engine._canon(99999) is None
    print("alias delete + _canon memoize OK")


if __name__ == '__main__':
    main()
    sys.stdout.flush()
    os._exit(0)
