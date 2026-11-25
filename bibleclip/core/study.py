"""영한 끊어 읽기(영어공부 카드) — 영어 Strong 역본(BSB · KJV+)과 한국어 Strong 역본(개역개정S ·
개역한글S)을 Strong 번호로 엮어, 영어 어순대로 덩어리를 짝짓는다(직독직해).

    In the beginning / God / created / the heavens / and the earth.
    태초에 / 하나님이 / 창조하시니라 / 천 / 지를

따로 맞춘 표 없이 번호만으로 엮는다. 한국어는 **Strong 조각 단위**(개역개정S 의 `공허<H922> 하며<H1961>`)
로 다룬다 — 어절(띄어쓰기) 단위로 묶으면 `공허하며` 가 통째로 was(H1961)에 붙는다(창 1:2).

규칙:
1. 한국어 Strong 조각을 실제 본문 위에 얹는다(글자 위치). 조각이 덮지 못한 글자도 번호 없는 조각이 된다.
2. 같은 번호는 나온 차례대로 짝(영어 n번째 ↔ 한국어 n번째). 관사 · 전치사 같은 작은 낱말은 짝을 갖지 않는다.
3. 짝 없는 영어 구절은 다음 덩어리에 붙고, 같은 한국어 조각을 나누는 이웃 구절은 한 덩어리가 된다.
4. 짝 없는 한국어 조각: 같은 어절에 짝 있는 조각이 있으면 그 앞 조각(없으면 뒤 조각)에 붙는다(어미 · 조사).
   어절 전체가 짝이 없으면 접속어 · 관형사(이는 · 그 …)는 다음 덩어리, 아니면 앞 덩어리.
5. 구절 모드(fine=False)는 문장부호(쉼표 · 마침표 …)에서만 끊고, 한 어절은 한 덩어리에 둔다.

결과 덩어리: {'en': [[구절, code], ...], 'ko': [[조각, code, 앞에 띄어쓰기 0/1], ...]} — 화면이 조각마다
번호를 달아 누르면 사전(원어)이 뜬다.
"""
import re

# 짝을 갖지 않는 영어 작은 낱말(구절 전체가 이것뿐일 때). be 동사는 본동사일 수 있어 넣지 않는다.
FUNC = frozenset({
    'the', 'a', 'an', 'of', 'to', 'and', 'or', 'but', 'that', 'who', 'which', 'in', 'for', 'with',
    'by', 'on', 'at', 'from', 'as', 'then', 'now',
})
# 다음 덩어리에 붙는 한국어 어절(짝 없을 때): 접속어 · 관형사.
CONJ_NEXT = frozenset({
    '이는', '그러므로', '그러나', '또', '곧', '그런데', '그리하여', '이에', '그래서', '그러면', '및', '혹은', '오직',
    '이', '그', '저', '그의', '저의', '이제', '또한',
})
# 한국어 어절 끝 글자가 이것이면 조사 · 어미로 끝난 말(앞 덩어리에 붙는다). 아니면 맨 명사로 본다.
_ENDINGS = frozenset('은는이가을를의에와과로도만서고며니사라여요다게지면데든나냐랴께처럼아어오우시')
_PUNCT_END = re.compile(r'[,;:.?!—]["”’\')\]]*$')
_LEAD_PUNCT = re.compile(r'^([,;:.?!]+)\s*(.*)$', re.S)
_PLAIN = re.compile(r"[\[\]“”‘’\"'.,;:!?()—]")


def _plain(s):
    return _PLAIN.sub('', s).strip().lower()


def ends_clause(s):
    """구절 끝에 문장부호가 있으면 True(구절 모드의 끊는 곳)."""
    return bool(_PUNCT_END.search(s.strip()))


def korean_units(text, pieces):
    """실제 본문을 Strong 조각 단위로 나눈다 → [{'t', 'c', 'w', 's', 'e'}] 본문 순서.

    t = 본문 그대로의 글자(조각 안 띄어쓰기 포함), c = 번호(없으면 None), w = 시작 어절 번호,
    s/e = 띄어쓰기를 뺀 글자 위치. pieces = parse_korean_strongs(...) 결과 [(조각, code)].
    본문과 어긋나는 조각(역본 판 차이)은 건너뛰고, 덮이지 않은 글자는 번호 없는 조각이 된다."""
    text = text or ''
    flat_to_real, word_of = [], []
    w = -1
    prev_space = True
    for i, ch in enumerate(text):
        if ch.isspace():
            prev_space = True
            continue
        if prev_space:
            w += 1
            prev_space = False
        flat_to_real.append(i)
        word_of.append(w)
    n = len(flat_to_real)
    flat = ''.join(text[i] for i in flat_to_real)
    spans, p = [], 0
    for piece, code in pieces or []:
        s = (piece or '').replace(' ', '')
        if not s:
            continue
        k = flat.find(s, p)
        if k < 0 or k - p > 12:
            # S 역본과 본문의 판이 조금 다르다(개역개정S '나뉘게 하라' ↔ 본문 '나뉘라') — 앞부분만 맞춰 본다.
            k, cut = -1, len(s) - 1
            while cut >= 2:                     # 두 글자까지(한 글자는 엉뚱한 곳에 맞기 쉽다)
                k = flat.find(s[:cut], p)
                if 0 <= k and k - p <= 12:
                    s = s[:cut]
                    break
                k, cut = -1, cut - 1
            if k < 0:
                continue
        spans.append((k, k + len(s), code if code not in ('H0', 'G0') else None))
        p = k + len(s)
    # 덮이지 않은 글자 → 어절별 번호 없는 조각.
    full, pos = [], 0
    for s, e, c in spans + [(n, n, None)]:
        q = pos
        while q < s:
            r = q
            while r < s and word_of[r] == word_of[q]:
                r += 1
            full.append((q, r, None))
            q = r
        if e > s:
            full.append((s, e, c))
        pos = max(pos, e)
    units = []
    for s, e, c in full:
        units.append({'t': text[flat_to_real[s]:flat_to_real[e - 1] + 1], 'c': c,
                      'w': word_of[s], 'we': word_of[e - 1], 's': s, 'e': e})
    return units


def korean_words(text, pieces):
    """(호환) 실제 본문 어절 + 번호가 나오는 차례 [(code, 어절 번호)]."""
    units = korean_units(text, pieces)
    return (text or '').split(), [(u['c'], u['w']) for u in units if u['c']]


def _match(a, b):
    """같은 번호의 영어 자리 a · 한국어 자리 b(각각 절 안 상대 위치 0~1, 오름차순)를 차례를 지키며 짝짓는다.
    개수가 같으면 차례대로, 다르면 위치 차이 합이 가장 작은 쪽으로(예: 영어 'the surface' 2번 ↔ 한국어 '면' 1번).
    → [(a 번호, b 번호)]."""
    if len(a) == len(b):
        return list(zip(range(len(a)), range(len(b))))
    swap = len(a) > len(b)
    x, y = (b, a) if swap else (a, b)            # x 가 짧다: x 전부를 y 일부와
    n, m = len(x), len(y)
    inf = float('inf')
    dp = [[inf] * (m + 1) for _ in range(n + 1)]
    for j in range(m + 1):
        dp[0][j] = 0.0
    for i in range(1, n + 1):
        for j in range(i, m + 1):
            dp[i][j] = min(dp[i][j - 1], dp[i - 1][j - 1] + abs(x[i - 1] - y[j - 1]))
    pairs, i, j = [], n, m
    while i > 0:
        if j > i and dp[i][j] == dp[i][j - 1]:
            j -= 1
        else:
            pairs.append((i - 1, j - 1))
            i, j = i - 1, j - 1
    pairs.reverse()
    return [(q, p) for p, q in pairs] if swap else pairs


def align_units(en_pairs, ko_text, ko_pieces, fine=True):
    """영어 [(구절, code)] + 한국어 본문 · 조각 → 덩어리 목록(모듈 설명 참고) 영어 순서."""
    units = korean_units(ko_text, ko_pieces)
    rows = []
    for text, code in en_pairs:
        text = (text or '').strip()
        # KJV+ 는 문장부호가 다음 구절 앞에 온다(', that') — 앞 구절 끝으로 옮긴다.
        m = _LEAD_PUNCT.match(text)
        if m and rows:
            rows[-1]['t'] += m.group(1)
            text = m.group(2)
        if not text:
            continue
        rows.append({'t': text, 'c': code, 'u': set()})
    if not rows:
        return []
    # 번호마다 영어 자리 ↔ 한국어 조각 짝(작은 낱말은 빼고).
    en_at, ko_at = {}, {}
    for ri, r in enumerate(rows):
        if r['c'] and _plain(r['t']) not in FUNC:
            en_at.setdefault(r['c'], []).append(ri)
    for ui, u in enumerate(units):
        if u['c']:
            ko_at.setdefault(u['c'], []).append(ui)
    # 1) 양쪽 개수가 같은 번호 = 차례대로(기준점).
    anchor = {}                                   # 영어 줄 → 한국어 조각
    for code, ris in en_at.items():
        uis = ko_at.get(code)
        if uis and len(uis) == len(ris):
            for r, u in zip(ris, uis):
                anchor[r] = u
    # 2) 개수가 다른 번호(창 1:7 히브리어 '궁창' 3번 ↔ BSB 'the expanse' 1번 ↔ 개역개정 '궁창' 3번):
    #    영어 줄마다 가장 가까운 기준점 이웃의 한국어 자리를 기대 위치로 삼아 짝짓는다. 한국어는
    #    목적어 · 꾸밈말이 앞에 오므로(made the expanse ↔ 궁창을 만드사) 기대 위치를 앞쪽으로 당긴다.
    nr, nu0 = max(len(rows) - 1, 1), max(len(units) - 1, 1)
    def expect(ri):
        best = None
        for d in range(1, len(rows)):
            for rj in (ri - d, ri + d):          # 같은 거리면 앞 이웃
                if rj in anchor:
                    best = anchor[rj]
                    break
            if best is not None:
                break
        return (best - 0.6) if best is not None else ri / nr * nu0
    for code, ris in en_at.items():
        uis = ko_at.get(code)
        if not uis:
            continue
        if len(uis) == len(ris):
            pairs = list(zip(range(len(ris)), range(len(uis))))
        else:
            pairs = _match([expect(r) for r in ris], [float(u) for u in uis])
        for a, b in pairs:
            rows[ris[a]]['u'].add(uis[b])
    chunks, pending = [], []
    for r in rows:
        if not r['u']:
            pending.append(r)
            continue
        last = chunks[-1] if chunks else None
        if last and (r['u'] & last['u']) and not ends_clause(last['rows'][-1]['t']):
            last['rows'] += pending + [r]
            last['u'] |= r['u']
        else:
            chunks.append({'rows': pending + [r], 'u': set(r['u'])})
        pending = []
    if pending:
        if chunks:
            chunks[-1]['rows'] += pending
        else:
            chunks.append({'rows': pending, 'u': set()})
    if not fine:
        merged = []
        for c in chunks:
            if merged and not any(ends_clause(r['t']) for r in merged[-1]['rows']):
                merged[-1]['rows'] += c['rows']
                merged[-1]['u'] |= c['u']
            else:
                merged.append(c)
        chunks = merged
    owner = {}
    for ci, c in enumerate(chunks):
        for i in c['u']:
            owner.setdefault(i, ci)
    nu = len(units)
    # 짝 없는 조각 — 같은 어절의 짝 있는 조각 먼저.
    for i in range(nu):
        if i in owner:
            continue
        w = units[i]['w']
        prev = next((owner[k] for k in range(i - 1, -1, -1) if units[k]['w'] == w and k in owner), None)
        nxt = next((owner[k] for k in range(i + 1, nu) if units[k]['w'] == w and k in owner), None)
        if prev is not None or nxt is not None:
            owner[i] = prev if prev is not None else nxt
    # 어절 전체가 짝이 없으면 이웃 어절로.
    words = (ko_text or '').split()
    for i in range(nu):
        if i in owner:
            continue
        prev = next((owner[k] for k in range(i - 1, -1, -1) if k in owner), None)
        nxt = next((owner[k] for k in range(i + 1, nu) if k in owner), None)
        w = units[i]['w']
        word = words[w] if 0 <= w < len(words) else units[i]['t']
        bare = word.rstrip(',.')
        # 조사 · 어미 없이 끝난 맨 명사(궁창 아래의, 땅 위)는 뒤 낱말을 꾸민다 → 다음 덩어리.
        if bare in CONJ_NEXT or prev is None or (bare and bare[-1] not in _ENDINGS):
            owner[i] = nxt if nxt is not None else prev
        else:
            owner[i] = prev
    if not fine:   # 한 어절은 한 덩어리에(그 어절 첫 조각의 덩어리)
        first = {}
        for i in range(nu):
            first.setdefault(units[i]['w'], owner.get(i))
        for i in range(nu):
            owner[i] = first[units[i]['w']]
    out = []
    for ci, c in enumerate(chunks):
        ko, last = [], None
        for i in range(nu):
            if owner.get(i, 0) != ci:
                continue
            u = units[i]
            gap = 0 if (last is not None and last['e'] == u['s'] and last['we'] == u['w']) else 1
            ko.append([u['t'], u['c'], gap if ko else 0])
            last = u
        out.append({'en': [[r['t'], r['c']] for r in c['rows']], 'ko': ko})
    return out


def chunk_text(chunk):
    """덩어리 → (영어 글, 한국어 글)."""
    en = ' '.join(t for t, _ in chunk['en'])
    ko = ''.join((' ' if gap else '') + t for t, _, gap in chunk['ko'])
    return en, ko


def align_verse(en_pairs, ko_text, ko_pieces, fine=True):
    """[(영어 덩어리 글, 한국어 덩어리 글)] — 테스트 · 간단한 쓰임용."""
    return [chunk_text(c) for c in align_units(en_pairs, ko_text, ko_pieces, fine)]
