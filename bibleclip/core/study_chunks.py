"""영어공부 '의미 덩어리' 표 — 읽기(앱) · 짝 맞추기 계산(생성기 tools/make_study_chunks.py 가 씀).

표 = 성경 전체를 이 PC 에서 미리 계산한 결과(SQLite, 장마다 zlib JSON). 계산에는 spaCy(영어 구문 분석)와
LaBSE(다국어 낱말 유사도)가 들지만, 그 결과만 동봉하므로 앱은 표준 라이브러리만 쓴다.

    info(key, value)              — en · ko 역본 이름, 만든 날, 방법
    chunks(book, chapter, data)   — data = zlib(JSON {절: [덩어리…]})
    덩어리 = {'en': [[낱말, 번호|None]…], 'ko': [[조각, 번호|None, 앞 띄움 0/1]…]} (study.align_units 와 같은 꼴)

짝 맞추기(align_chunks): 영어 덩어리 경계(starts)와 낱말×조각 유사도(cos · dot)를 받아
 1 한국어 조각에 원어 번호가 있고 그 번호가 영어에도 있으면 그 번호의 영어 구절 머리말과 짝(강제).
   같은 번호가 여러 번이면 개수가 같을 때 차례대로, 다르면 위치가 가까운 것끼리.
 2 번호 없는 조각은 모델 짝(양방향 softmax, 유사도 0.5 이상).
 3 짝 없는 조각은 같은 어절의 짝 있는 조각 → 앞 조각 → 뒤 조각을 따른다. 앞 조각에 붙은 조각(띄어쓰기
   없음: 자기 주인+의 집에)은 늘 앞 조각을 따른다.
 4 한국어가 빈 영어 덩어리는 다음(끝이면 앞) 덩어리에 합친다.
"""
import json
import math
import os
import sqlite3
import zlib

from bibleclip.core.study import _is_content, _match

MODEL_TH = 0.5
ORPHAN_TH = 0.35      # 짝 없는 어절도 모델이 이만큼 확신하면 그 영어 쪽으로
LEFTOVER_NEAREST = False   # 같은 번호가 한국어에 더 많을 때 남는 조각: False = 모델에 맡김


class StudyChunks:
    """미리 계산한 의미 덩어리 표 하나(영어 역본 × 한국어 역본)."""

    def __init__(self, path):
        self.path = path
        self.info = {}
        self.available = False
        self._con = None
        if path and os.path.isfile(path):
            try:
                self._con = sqlite3.connect(f'file:{path}?mode=ro', uri=True, check_same_thread=False)
                self.info = dict(self._con.execute('SELECT key, value FROM info').fetchall())
                self.available = True
            except sqlite3.Error:
                self._con = None

    def chapter(self, book, chapter):
        """{절: [덩어리…]} 또는 None(그 장이 표에 없음)."""
        if not self.available:
            return None
        row = self._con.execute('SELECT data FROM chunks WHERE book=? AND chapter=?',
                                (int(book), int(chapter))).fetchone()
        if not row:
            return None
        return {int(k): v for k, v in json.loads(zlib.decompress(row[0]).decode('utf-8')).items()}


def write_table(path, info, chapters):
    """chapters = {(book, chapter): {절: [덩어리…]}} → SQLite(덮어씀)."""
    tmp = path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.execute('CREATE TABLE info (key TEXT PRIMARY KEY, value TEXT)')
    con.execute('CREATE TABLE chunks (book INTEGER, chapter INTEGER, data BLOB, PRIMARY KEY (book, chapter))')
    con.executemany('INSERT INTO info VALUES (?, ?)', sorted(info.items()))
    con.executemany('INSERT INTO chunks VALUES (?, ?, ?)', [
        (b, c, zlib.compress(json.dumps(vs, ensure_ascii=False, separators=(',', ':')).encode('utf-8'), 9))
        for (b, c), vs in sorted(chapters.items())])
    con.commit()
    con.close()
    os.replace(tmp, path)


# ---- 짝 맞추기(순수 계산) ----

def softmax_pairs(dot, th=1e-3):
    """양방향 softmax 가 둘 다 th 를 넘는 (영어 i, 한국어 j) — awesome-align 무학습 방식."""
    E, K = len(dot), len(dot[0]) if dot else 0
    if not E or not K:
        return set()

    def sm(xs):
        m = max(xs)
        ex = [math.exp(x - m) for x in xs]
        s = sum(ex)
        return [x / s for x in ex]
    r = [sm(dot[i]) for i in range(E)]
    c = [sm([dot[i][j] for i in range(E)]) for j in range(K)]
    return {(i, j) for i in range(E) for j in range(K) if r[i][j] > th and c[j][i] > th}


def head_of(en, pi):
    """구절 pi 의 머리말(마지막 내용어, 없으면 마지막 낱말) 위치."""
    idx = [i for i, x in enumerate(en) if x[2] == pi]
    cont = [i for i in idx if _is_content(en[i][0])]
    return (cont or idx)[-1]


def pair_words(en, ko, cos, dot):
    """낱말 짝 → ({(i, j)}, 점수표). en = [[낱말, 번호, 구절 번호]], ko = [[조각, 번호, 어절 번호]]."""
    E, K = len(en), len(ko)
    epi = {}
    for i, (_, c, pi) in enumerate(en):
        if c:
            epi.setdefault(c, set()).add(pi)
    kcode = {}
    for j, (_, c, _) in enumerate(ko):
        if c and c in epi:
            kcode.setdefault(c, []).append(j)
    A, S = set(), [row[:] for row in cos]
    for c, jl in kcode.items():
        groups = sorted(epi[c])
        if len(groups) == len(jl):
            gp = list(zip(groups, jl))
        else:
            ctr = {g: sum(i for i, x in enumerate(en) if x[2] == g) / max(1, sum(1 for x in en if x[2] == g)) / E
                   for g in groups}
            gp = [(groups[x], jl[y]) for x, y in _match([ctr[g] for g in groups], [j / K for j in jl])]
            done = {j for _, j in gp}
            if LEFTOVER_NEAREST:
                gp += [(min(groups, key=lambda g: abs(ctr[g] - j / K)), j) for j in jl if j not in done]
        for g, j in gp:
            i = head_of(en, g)
            A.add((i, j))
            S[i][j] += 1
    coded = {j for _, j in A}
    for i, j in softmax_pairs(dot):
        if j not in coded and cos[i][j] >= MODEL_TH:
            A.add((i, j))
    return A, S


def glued_flags(ko_text, ko):
    """조각마다 바로 앞 글자가 띄어쓰기가 아닌지(앞 조각에 붙음)."""
    out, p = [], 0
    for t, _, _ in ko:
        i = ko_text.find(t, p)
        i = p if i < 0 else i
        out.append(i > 0 and bool(out) and not ko_text[i - 1].isspace())
        p = i + len(t)
    return out


def align_chunks(en, ko, ko_text, starts, cos, dot):
    """의미 덩어리 짝 → [{'en': [[낱말, 번호|None]], 'ko': [[조각, 번호|None, 띄움]]}]."""
    if not en:
        return []
    b = sorted(set(starts or [0]) | {0}) + [len(en)]
    subs = [list(range(b[k], b[k + 1])) for k in range(len(b) - 1) if b[k] < b[k + 1]]
    heads = {head_of(en, pi) for pi in {x[2] for x in en}}

    def en_out(s):
        return [[en[i][0], en[i][1] if i in heads and en[i][1] else None] for i in s]
    if not ko:
        return [{'en': en_out(range(len(en))), 'ko': []}]
    A, S = pair_words(en, ko, cos, dot)
    sub_of = {i: si for si, s in enumerate(subs) for i in s}
    best = {}
    for i, j in A:
        if j not in best or S[i][j] > S[best[j]][j]:
            best[j] = i
    for j in list(best):                       # 번호 없는 조사 · 어미는 같은 어절의 번호 있는 조각을 따른다
        if not ko[j][1] and any(ko[k][2] == ko[j][2] and ko[k][1] for k in range(len(ko)) if k != j):
            del best[j]
    dest = [sub_of[best[j]] if j in best else None for j in range(len(ko))]
    for j in range(len(ko)):
        if dest[j] is None:
            same = [k for k in range(len(ko)) if ko[k][2] == ko[j][2] and k != j and k in best]
            if same:
                prev = [k for k in same if k < j]
                dest[j] = sub_of[best[prev[-1] if prev else same[0]]]
    for j in range(len(ko)):                   # 짝 없는 어절 — 모델이 어느 정도 확신하면 그쪽
        # (것이며 · 하니 · 하매 같은 문법 어절은 빼고 — 앞 어절을 따른다)
        if dest[j] is None and ORPHAN_TH and cos and not ko[j][0].startswith(('것', '하')):
            i = max(range(len(en)), key=lambda i: cos[i][j])
            if cos[i][j] >= ORPHAN_TH:
                dest[j] = sub_of[i]
    for j in range(len(ko)):
        if dest[j] is None:
            prev = [dest[k] for k in range(j) if dest[k] is not None]
            nxt = [dest[k] for k in range(j + 1, len(ko)) if dest[k] is not None]
            dest[j] = prev[-1] if prev else (nxt[0] if nxt else len(subs) - 1)
    glued = glued_flags(ko_text, ko)
    for j in range(1, len(ko)):
        if glued[j]:
            dest[j] = dest[j - 1]
    mine = [[j for j in range(len(ko)) if dest[j] == si] for si in range(len(subs))]
    i = 0
    while len(subs) > 1 and i < len(subs):
        if mine[i]:
            i += 1
            continue
        if i + 1 < len(subs):
            subs[i + 1] = subs[i] + subs[i + 1]
        else:
            subs[i - 1] = subs[i - 1] + subs[i]
        del subs[i], mine[i]
    out = []
    for s, js in zip(subs, mine):
        kk = []
        for n, j in enumerate(js):
            gap = 0 if n == 0 or (glued[j] and js[n - 1] == j - 1) else 1
            kk.append([ko[j][0], ko[j][1], gap])
        out.append({'en': en_out(s), 'ko': kk})
    return out
