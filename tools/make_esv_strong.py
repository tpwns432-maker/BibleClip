"""사용자 ESV 에 Strong 번호를 붙인다 → KJV+ 형식(`단어<S>번호</S>`) ESV+.SQLite3.

    python -X utf8 tools/make_esv_strong.py <ESV.SQLite3> [출력 경로]     # 기본 출력 bible_versions/ESV+.SQLite3
    python -X utf8 tools/make_esv_strong.py --eval                        # 정확도 검증(KJV+ 를 시험지로)
    python -X utf8 tools/make_esv_strong.py --derive-map                  # KJV+ → BSB 번호 환산표 다시 뽑기

⚠️ ESV 는 저작권 자료 — 입력 · 결과 파일 모두 git · 릴리스에 넣지 않는다(`bible_versions/*` 규칙으로 git 밖).
   이 스크립트와 아래 환산표는 공개 자료(BSB=CC0, KJV+=PD)에서 나온 것이라 저장소에 둔다.

방법 — 절마다 원어 번호 집합은 이미 안다(그 절의 BSB ∪ KJV+ 번호). ESV 단어를 그 몇 개 후보 중 하나
(또는 '없음')에 배정하는 문제로 푼다.
  1. 어휘 t(단어|번호): BSB · KJV+ 의 태그된 구절(지도) + ESV 절(비지도)을 함께 IBM Model 1 EM.
     → ESV 고유 표현(steadfast love→2617, fathered→3205)도 ESV 자체에서 배운다.
  2. 위치: ESV 단어의 절 안 상대 위치 ↔ 그 번호가 BSB 영어에서 나온 상대 위치 (영어끼리라 어순이 비슷).
  3. 같은 단어: ESV 와 BSB(·KJV) 를 difflib 로 맞물려 같은 어간이면 그 구절 번호에 가산.
  4. 배정(앵커): 번호마다 가장 잘 맞는 단어를 먼저 잡고(번호는 BSB 출현 횟수만큼, 단어엔 번호 하나),
     남은 단어는 사후확률 0.5 이상일 때만. 'children of Israel' 에서 3478 이 Israel 을 먼저 잡는다.
  5. 기능어(the, of, your …)는 BSB/KJV+ 에서 그 말 혼자 그 번호를 3번 이상 받았을 때만 태그
     (for→3588 · not→3808 은 되고, the→776 은 안 됨). 안 붙은 말은 다음 태그 구절에 묶여 보인다.
  6. KJV+ 는 활용형 번호(μου 3450, ἐστί 2076 …)를 쓰고 BSB 는 원형 번호(ἐγώ 1473, εἰμί 1510)를 쓴다
     → KJV+ 번호를 KJV_TO_BSB 로 BSB 체계에 맞춘 뒤 쓴다. 결과 번호는 BSB 체계.

검증(--eval) — ESV 엔 정답지가 없으므로, 태그를 지운 KJV 를 **BSB 만으로** 태깅해 KJV+ 원래 태그와
비교한다. KJV(고어 · TR 사본)는 ESV 보다 BSB 에서 훨씬 멀어서 ESV 정확도의 보수적 하한이다.
2026-11-25 실측: 내용어 정밀도 88%(확신≥0.7 은 90%) · 번호 재현율 94% (KJV+ 가 태그를 빠뜨린 자리는
판정 불가로 빼고 셈).
"""
import difflib
import math
import os
import re
import shutil
import sqlite3
import sys
import time
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BSB = os.path.join(ROOT, 'bible_versions', 'BSB.SQLite3')
KJVP = os.path.join(ROOT, 'bible_versions', 'KJV+.SQLite3')
DEFAULT_OUT = os.path.join(ROOT, 'bible_versions', 'ESV+.SQLite3')

# KJV+ 활용형 번호 → BSB 원형 번호. --derive-map 으로 뽑은 61쌍(2026-11-25) 중
# H6240(-teen)→H8147(둘) 은 'fourteen' 에서 틀려 뺐고, G4571(σέ)→G3957 은 잡음이라 G4771 로 고쳤다.
# G4675(σου)는 BSB 가 한 번도 안 쓰는 번호인데 정렬 잡음으로 기준(50%)을 못 넘어 손으로 더했다.
KJV_TO_BSB = {
    'H1928': 'H1909', 'H2425': 'H2421', 'H3169': 'H2396', 'H3212': 'H1980', 'H3240': 'H5117',
    'H7125': 'H7122', 'G1302': 'G1223', 'G1488': 'G1510', 'G1499': 'G1487', 'G1508': 'G1487',
    'G1511': 'G1510', 'G1526': 'G1510', 'G1536': 'G5100', 'G1691': 'G1473', 'G1698': 'G1473',
    'G1700': 'G1473', 'G2070': 'G1510', 'G2071': 'G1510', 'G2075': 'G1510', 'G2076': 'G1510',
    'G2077': 'G1510', 'G2248': 'G1473', 'G2249': 'G1473', 'G2252': 'G1510', 'G2254': 'G1473',
    'G2257': 'G1473', 'G2258': 'G1510', 'G2396': 'G2400', 'G3165': 'G1473', 'G3187': 'G3173',
    'G3362': 'G1437', 'G3363': 'G2443', 'G3391': 'G1520', 'G3397': 'G3398', 'G3415': 'G3403',
    'G3427': 'G1473', 'G3450': 'G1473', 'G3700': 'G3708', 'G4055': 'G4053', 'G4056': 'G4057',
    'G4280': 'G4302', 'G4483': 'G2046', 'G4571': 'G4771', 'G4671': 'G4771', 'G4675': 'G4771',
    'G5023': 'G3778', 'G5025': 'G3778', 'G5026': 'G3778', 'G5124': 'G3778', 'G5125': 'G3778',
    'G5126': 'G3778', 'G5127': 'G3778', 'G5128': 'G3778', 'G5129': 'G3778', 'G5130': 'G3778',
    'G5209': 'G4771', 'G5213': 'G4771', 'G5216': 'G4771', 'G5224': 'G5225', 'G5600': 'G1510',
    'G5607': 'G1510',
}

WORD = re.compile(r"[A-Za-z]+(?:['’][A-Za-z]+)*")
S_TAG = re.compile(r'<S>(\d+)</S>')
NOTE = re.compile(r'<f>.*?</f>|<n>.*?</n>', re.S)   # 각주 · 해설: 본문 아님
ANY_TAG = re.compile(r'<[^>]*>')
OTHER_TAG = re.compile(r'<(?!/?S>)[^>]*>')

STOP = set((
    'the a an of to and in that for with is was be are were he she it they them his her their its i you we '
    'me my your our us him this these those on by from at as or but not shall will have has had thee thou thy '
    'thine ye unto hath hast shalt wilt art doth dost upon into who which what all so then there when let also even'
).split())
NULL = -1
G_OFF = 100000  # 번호 키: 구약(히브리어) = 번호, 신약(헬라어) = 100000 + 번호
NT_FIRST_BOOK = 470


# ── 글 다루기 ────────────────────────────────────────────────

def stem(w):
    """가벼운 영어 어간(loved/loves/loving → lov). 기능어는 그대로 — 어간을 떼면 these→thes 로 목록을 빠져나간다."""
    w = w.lower().replace('’', "'")
    if w in STOP:
        return w
    if w.endswith("'s"):
        w = w[:-2]
    elif w.endswith("s'"):
        w = w[:-1]
    if len(w) <= 3:
        return w
    for suf in ('ings', 'ing', 'eth', 'edst', 'est', 'ed', 'ies', 'es', 's', 'ly'):
        if w.endswith(suf) and len(w) - len(suf) >= 3:
            base = w[:-len(suf)]
            if suf == 'ies':
                base += 'y'
            if len(base) >= 4 and base[-1] == base[-2] and base[-1] not in 'lsz':
                base = base[:-1]
            if base.endswith('e') and len(base) > 4:
                base = base[:-1]
            return base
    if w.endswith('e') and len(w) > 4:
        return w[:-1]
    return w


def load(path):
    con = sqlite3.connect(path)
    try:
        return {(int(b), int(c), int(v)): t or ''
                for b, c, v, t in con.execute('select book_number, chapter, verse, text from verses')}
    finally:
        con.close()


def segments(tagged):
    """'In the beginning<S>7225</S> God<S>430</S>…' → [([단어], [번호])].
    글 없이 태그만 있는 조각(KJV+ 'created<S>1254</S> <S>853</S>')은 앞 조각 번호에 더한다."""
    t = OTHER_TAG.sub('', NOTE.sub('', tagged))
    segs, pos = [], 0
    for m in S_TAG.finditer(t):
        words = WORD.findall(t[pos:m.start()])
        if words or not segs:
            segs.append((words, [int(m.group(1))]))
        else:
            segs[-1][1].append(int(m.group(1)))
        pos = m.end()
    tail = WORD.findall(t[pos:])
    if tail:
        segs.append((tail, []))
    return segs


def plain_words(raw):
    """태그 · 각주 밖의 단어와 그 끝 위치(원문 기준) — 태그를 원문 표기 그대로 끼워 넣기 위해."""
    mask = bytearray(len(raw))
    for rx in (NOTE, ANY_TAG):
        for m in rx.finditer(raw):
            mask[m.start():m.end()] = b'\1' * (m.end() - m.start())
    return [(m.group(0), m.end()) for m in WORD.finditer(raw) if not mask[m.start()]]


def key_of(code, verse_key):
    return code if verse_key[0] < NT_FIRST_BOOK else G_OFF + code


def convert_kjv(segs_by_verse, table=KJV_TO_BSB):
    """KJV+ 번호를 BSB 체계로."""
    def num(s):
        return int(s[1:]) + (G_OFF if s[0] == 'G' else 0)
    cm = {num(a): num(b) for a, b in table.items()}
    out = {}
    for k, segs in segs_by_verse.items():
        out[k] = [(ws, [cm.get(key_of(c, k), key_of(c, k)) % G_OFF for c in cs]) for ws, cs in segs]
    return out


# ── 정렬 ─────────────────────────────────────────────────────

class Target:
    """정렬할 절 하나: 단어 열 + 후보 번호(위치 · 상한 · 같은 단어 맞물림)."""
    __slots__ = ('key', 'words', 'stems', 'cands', 'pos', 'cap', 'match')

    def __init__(self, key, words, ref_segs, alt_segs=()):
        """ref_segs: 주 참조(BSB). alt_segs: 보조 참조(KJV+) — 주 참조에 없는 번호와 같은 단어 맞물림에만."""
        self.key, self.words = key, words
        self.stems = [stem(w) for w in words]
        self.pos, self.cap = defaultdict(list), {}
        self.match = [None] * len(words)
        for r, segs in enumerate((ref_segs, alt_segs)):
            known = set(self.pos) if r else set()
            ref_stems, ref_codes, cnt = [], [], Counter()
            for ws, codes in segs:
                ks = [key_of(c, key) for c in codes]
                cnt.update(ks)
                for w in ws:
                    ref_stems.append(stem(w))
                    ref_codes.append(ks)
            n = max(len(ref_stems), 1)
            for j, ks in enumerate(ref_codes):
                for k in ks:
                    if k not in known:
                        self.pos[k].append((j + 0.5) / n)
            for k, c in cnt.items():
                if k not in known:
                    self.cap[k] = c
                    self.pos.setdefault(k, [])
            sm = difflib.SequenceMatcher(None, self.stems, ref_stems, autojunk=False)
            for a, b, size in sm.get_matching_blocks():
                for d in range(size):
                    if self.stems[a + d] not in STOP and ref_codes[b + d]:
                        self.match[a + d] = (self.match[a + d] or set()) | set(ref_codes[b + d])
        self.cands = list(self.pos)

    def factors(self, i, kpos=6.0, bonus=8.0):
        r = (i + 0.5) / max(len(self.words), 1)
        m = self.match[i]
        out = {}
        for k in self.cands:
            ps = self.pos[k]
            f = math.exp(-kpos * min(abs(r - p) for p in ps)) if ps else 0.35
            if m is not None and k in m:
                f *= bonus
            out[k] = f
        return out


NULL_W = 0.5 * 0.35   # '없음' 후보의 사전 가중


def supervised(*segs_by_verse):
    """태그된 조각들 → [(어간들, 번호 키들)]."""
    sup = []
    for src in segs_by_verse:
        for k, segs in src.items():
            for ws, codes in segs:
                if ws and codes:
                    sup.append(([stem(w) for w in ws], [key_of(c, k) for c in codes]))
    return sup


def train(sup, targets, iters=5, log=print):
    """IBM Model 1 EM. 지도 조각은 그 조각 번호 + NULL 안에서, 목표 절은 절 후보 + NULL 안에서 나눈다."""
    cnt = defaultdict(lambda: defaultdict(float))
    for stems, keys in sup:
        ks = keys + [NULL]
        for w in stems:
            for k in ks:
                cnt[k][w] += 1.0 / len(ks)
    for tg in targets:
        ks = tg.cands + [NULL]
        for w in tg.stems:
            for k in ks:
                cnt[k][w] += 1.0 / len(ks)
    t = _normalize(cnt)
    fcache = [[tg.factors(i) for i in range(len(tg.words))] for tg in targets]
    for it in range(iters):
        cnt = defaultdict(lambda: defaultdict(float))
        tn = t[NULL]
        for stems, keys in sup:
            for w in stems:
                ps = [(k, t[k].get(w, 1e-9)) for k in keys]
                ps.append((NULL, 0.5 * tn.get(w, 1e-9)))
                z = sum(p for _, p in ps)
                for k, p in ps:
                    cnt[k][w] += p / z
        for tg, fs in zip(targets, fcache):
            for i, w in enumerate(tg.stems):
                f = fs[i]
                ps = [(k, t[k].get(w, 1e-9) * f[k]) for k in tg.cands]
                ps.append((NULL, NULL_W * tn.get(w, 1e-9)))
                z = sum(p for _, p in ps)
                for k, p in ps:
                    cnt[k][w] += p / z
        t = _normalize(cnt)
        log(f'  EM {it + 1}/{iters}')
    return t


def _normalize(cnt):
    t = {}
    for k, ws in cnt.items():
        z = sum(ws.values())
        t[k] = {w: c / z for w, c in ws.items()}
    return t


def stop_allow(sup, min_count=3):
    """기능어로만 된 조각('For<S>1063</S>', 'shall not<S>3808</S>')에서 그 번호를 받은 (어간, 번호)."""
    c = Counter()
    for stems, keys in sup:
        if stems and all(w in STOP for w in stems):
            for w in stems:
                for k in keys:
                    c[w, k] += 1
    return frozenset(wk for wk, n in c.items() if n >= min_count)


def decode(t, tg, allow, min_post=0.5, anchor_min=0.15):
    """단어마다 (번호 키 | NULL, 사후확률). 앵커 → 나머지 순."""
    tn = t.get(NULL, {})
    n = len(tg.stems)
    post, nullp = [], []
    for i, w in enumerate(tg.stems):
        f = tg.factors(i)
        sc = {k: t.get(k, {}).get(w, 1e-9) * f[k] for k in tg.cands}
        np_ = NULL_W * tn.get(w, 1e-9)
        z = sum(sc.values()) + np_
        post.append({k: v / z for k, v in sc.items()})
        nullp.append(np_ / z)

    def ok(i, k):
        return tg.stems[i] not in STOP or (tg.stems[i], k) in allow

    out = [(NULL, 0.0)] * n
    used = Counter()
    for p, i, k in sorted(((post[i][k], i, k) for i in range(n) for k in tg.cands if ok(i, k)), reverse=True):
        if p < anchor_min:
            break
        if out[i][0] == NULL and used[k] < tg.cap[k]:
            out[i] = (k, p)
            used[k] += 1
    for i in range(n):
        if out[i][0] == NULL and post[i]:
            k, p = max(post[i].items(), key=lambda kv: kv[1])
            if ok(i, k) and p >= min_post and nullp[i] < p:
                out[i] = (k, p)
    return out


def render(raw, words, pred):
    """원문 표기를 살린 채 단어 끝에 '<S>번호</S>'. 같은 번호가 이어진 무리는 마지막 단어 뒤에 한 번."""
    parts, last = [], 0
    for j, ((_, end), (k, _)) in enumerate(zip(words, pred)):
        if k == NULL or (j + 1 < len(pred) and pred[j + 1][0] == k):
            continue
        parts.append(raw[last:end])
        parts.append(f'<S>{k % G_OFF}</S>')
        last = end
    parts.append(raw[last:])
    return ''.join(parts)


# ── 명령 ─────────────────────────────────────────────────────

def build(esv_path, out_path, log=print):
    t0 = time.time()
    bsb_segs = {k: segments(v) for k, v in load(BSB).items()}
    kjv_segs = convert_kjv({k: segments(v) for k, v in load(KJVP).items()})
    esv = load(esv_path)
    sup = supervised(bsb_segs, kjv_segs)
    targets, words = [], {}
    for k, raw in esv.items():
        ws = plain_words(raw)
        if ws and (k in bsb_segs or k in kjv_segs):
            words[k] = ws
            targets.append(Target(k, [w for w, _ in ws], bsb_segs.get(k, []), kjv_segs.get(k, [])))
    log(f'준비 {time.time() - t0:.0f}s · 태그 조각 {len(sup):,} · ESV 절 {len(targets):,}')
    t = train(sup, targets, log=log)
    allow = stop_allow(sup)
    new, st = {}, Counter()
    for tg in targets:
        pred = decode(t, tg, allow)
        new[tg.key] = render(esv[tg.key], words[tg.key], pred)
        for w, (k, _) in zip(tg.stems, pred):
            c = 'stop' if w in STOP else 'content'
            st[c] += 1
            st[c + '+'] += k != NULL
    tmp = out_path + '.tmp'
    shutil.copyfile(esv_path, tmp)
    con = sqlite3.connect(tmp)
    try:
        con.executemany('update verses set text=? where book_number=? and chapter=? and verse=?',
                        [(v, *k) for k, v in new.items()])
        con.execute("insert or replace into info(name, value) values('strong_numbers', 'true')")
        desc = (con.execute("select value from info where name='description'").fetchone() or ['ESV'])[0]
        con.execute("insert or replace into info(name, value) values('description', ?)",
                    (desc + " — Strong's numbers aligned from BSB/KJV+ (personal use)",))
        con.commit()
    finally:
        con.close()
    os.replace(tmp, out_path)
    log(f"내용어 태그 {st['content+'] / st['content']:.1%} · 기능어 태그 {st['stop+'] / st['stop']:.1%}")
    log(f'→ {out_path} ({time.time() - t0:.0f}s)')


def _kjv_eval_setup(log=print):
    """BSB 만으로 KJV 를 태깅할 준비: (지도 조각, 목표 절, KJV+ 원래 조각)."""
    bsb, kjv = load(BSB), load(KJVP)
    keys = sorted(k for k in kjv if k in bsb)
    bsb_segs = {k: segments(bsb[k]) for k in keys}
    kjv_segs = {k: segments(kjv[k]) for k in keys}
    targets = [Target(k, [w for ws, _ in kjv_segs[k] for w in ws], bsb_segs[k]) for k in keys]
    sup = supervised(bsb_segs)
    t = train(sup, targets, log=log)
    return sup, targets, kjv_segs, t


def evaluate(log=print):
    sup, targets, kjv_segs, t = _kjv_eval_setup(log)
    allow = stop_allow(sup)
    st = Counter()
    for tg in targets:
        segs = kjv_segs[tg.key]
        gold = [{key_of(c, tg.key) for c in cs} for ws, cs in segs for _ in ws]
        verse = set().union(*gold) if gold else set()
        pred = decode(t, tg, allow)
        for w, (k, p), g in zip(tg.stems, pred, gold):
            if k == NULL or w in STOP:
                continue
            # 다른 단어에 붙은 번호면 오답, KJV+ 절 어디에도 없으면 판정 불가(KJV+ 가 빠뜨린 자리)
            r = 'ok' if k in g else 'bad' if k in verse else 'unknown'
            st[r] += 1
            if p >= 0.7:
                st[r + '_hi'] += 1
        i = 0
        for ws, cs in segs:
            got = {pred[j][0] for j in range(i, i + len(ws))}
            for c in cs:
                kk = key_of(c, tg.key)
                if kk in tg.pos:
                    st['pairs'] += 1
                    st['found'] += kk in got
            i += len(ws)
    log(f"내용어 정밀도 {st['ok'] / (st['ok'] + st['bad']):.1%} "
        f"(확신≥0.7: {st['ok_hi'] / (st['ok_hi'] + st['bad_hi']):.1%}) · 판정 불가 {st['unknown']:,} · "
        f"번호 재현율 {st['found'] / st['pairs']:.1%}")
    return st


def derive_map(log=print):
    """KJV+ 번호 c 가 붙은 KJV 단어를 BSB 만으로 태깅했을 때 주로 받는 번호 b.
    c 가 BSB 에 거의 안 쓰이는(활용형) 번호이고 b 가 절반 이상일 때만."""
    sup, targets, kjv_segs, t = _kjv_eval_setup(log)
    allow = stop_allow(sup)
    bfreq, kfreq, pair = Counter(), Counter(), defaultdict(Counter)
    for stems, keys in sup:
        bfreq.update(keys)
    for tg in targets:
        gold = [[key_of(c, tg.key) for c in cs] for ws, cs in kjv_segs[tg.key] for _ in ws]
        for ws, cs in kjv_segs[tg.key]:
            kfreq.update(key_of(c, tg.key) for c in cs)
        for (k, _), g in zip(decode(t, tg, allow), gold):
            if k != NULL and len(g) == 1:
                pair[g[0]][k] += 1
    lab = lambda x: ('G' if x >= G_OFF else 'H') + str(x % G_OFF)  # noqa: E731
    out = {}
    for c, ctr in pair.items():
        b, n = ctr.most_common(1)[0]
        if b != c and kfreq[c] >= 10 and bfreq[c] < 0.1 * kfreq[c] and n / sum(ctr.values()) >= 0.5:
            out[lab(c)] = lab(b)
    for c in sorted(out, key=lambda x: -kfreq[int(x[1:]) + (G_OFF if x[0] == 'G' else 0)]):
        log(f'  {c} → {out[c]}')
    log(f'{len(out)}쌍 — 검토해서 KJV_TO_BSB 에 반영')
    return out


def main(argv):
    if '--eval' in argv:
        evaluate()
    elif '--derive-map' in argv:
        derive_map()
    elif argv:
        build(argv[0], argv[1] if len(argv) > 1 else DEFAULT_OUT)
    else:
        print(__doc__)
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
