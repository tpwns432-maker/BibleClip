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
6. (2026-11-25 전수조사, _local/bsb/audit/REPORT.md) 어절 전체가 짝 없을 때: 대명사 주어 · 목적어(내가 ·
   너희에게 …)는 같은 인칭 · 격의 영어 대명사 덩어리로(뒤쪽 우선), 단서 없는 대명사 · 지시어는 다음, 동사 어미
   (이르되 · 하매 …)는 앞. S 오탈자는 근사 · 뒷부분 맞춤, 이형 번호 22쌍은 같은 번호로 본다(FOLD_LEX).
   표본 덩어리 오류율 11.0% → 6.0%, 표본 밖 새 25절 중 23절 개선 · 악화 0.

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
    spans, p, slack = [], 0, 0
    for piece, code in pieces or []:
        s = (piece or '').replace(' ', '')
        if not s:
            continue
        win = 12 + slack                       # 앞 조각을 놓쳤으면 그만큼 더 멀리 찾는다(연쇄 놓침 막기)
        k = flat.find(s, p)
        if k < 0 or k - p > win:
            # S 역본과 본문의 판이 조금 다르다(개역개정S '나뉘게 하라' ↔ 본문 '나뉘라') — 앞부분만 맞춰 본다.
            k, cut = -1, len(s) - 1
            while cut >= 2:                     # 두 글자까지(한 글자는 엉뚱한 곳에 맞기 쉽다)
                k = flat.find(s[:cut], p)
                if 0 <= k and k - p <= win:
                    s = s[:cut]
                    break
                k, cut = -1, cut - 1
            if k < 0 and len(s) >= 2:
                # S 오탈자(허럭 ↔ 허락, 증거 ↔ 증언) — 같은 길이, ¼ 이하 다르고 첫 · 끝 글자 하나는 같다.
                L, lim = len(s), max(1, len(s) // 4)
                for kk in range(p, min(p + win, len(flat) - L) + 1):
                    seg = flat[kk:kk + L]
                    if sum(a != b for a, b in zip(seg, s)) <= lim and (seg[0] == s[0] or seg[-1] == s[-1]):
                        k = kk
                        break
            if k < 0:
                # 덧붙은 글자(그 이름을 ↔ 그의 이름을) — 뒷부분을 맞추고 앞은 p 부터 덮는다.
                for cut in range(len(s) - 1, max(1, (len(s) + 1) // 2) - 1, -1):
                    kk = flat.find(s[-cut:], p)
                    if 0 <= kk and kk - p <= len(s):
                        k, s = p, flat[p:kk + cut]
                        break
            if k < 0:
                slack += len(s)
                continue
        spans.append((k, k + len(s), code if code not in ('H0', 'G0') else None))
        p = k + len(s)
        slack = 0
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
            en_at.setdefault(FOLD_LEX.get(r['c'], r['c']), []).append(ri)
    for ui, u in enumerate(units):
        if u['c']:
            ko_at.setdefault(FOLD_LEX.get(u['c'], u['c']), []).append(ui)
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
        w, we = units[i]['w'], units[i]['we']
        # 여러 어절에 걸친 조각('권하는 자' + '임을')도 같은 어절로 본다(앞 조각의 끝 어절 = 이 어절).
        prev = next((owner[k] for k in range(i - 1, -1, -1) if units[k]['we'] == w and k in owner), None)
        nxt = next((owner[k] for k in range(i + 1, nu) if units[k]['w'] == we and k in owner), None)
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
        # 대명사 주어 · 목적어(내가, 너희에게 …): 같은 인칭 · 격의 영어 대명사가 있는 덩어리 중 가까운 곳
        # (뒤쪽 우선 — 한국어는 주어 · 목적어가 서술어 앞). 전수조사 오류의 2/3 가 이것이었다.
        cls = _pron_class(bare)
        if cls and (prev is not None or nxt is not None):
            best, bd = None, None
            for ci, c in enumerate(chunks):
                if not c['u'] or not (_en_words(c) & cls):
                    continue
                dd = min((k - i) if k > i else (i - k) + 10 for k in c['u'])
                if bd is None or dd < bd:
                    best, bd = ci, dd
            if best is not None and bd <= 99:
                owner[i] = best
                continue
        # 영어 단서가 없는 대명사 · 지시어 체언(관형 포함)은 뒤 낱말과 함께.
        if prev is not None and nxt is not None and _pron_stem(bare):
            owner[i] = nxt
            continue
        # 동사 어미(이르되 · 하매 · 하거늘 …)는 앞 덩어리 — 맨 명사로 오인하던 것.
        if bare and bare[-1] in _VERB_END and bare not in CONJ_NEXT and bare not in _ADN and prev is not None:
            owner[i] = prev
            continue
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
        if fine:
            out.extend(_split_words(c['rows'], ko))
        else:
            out.append({'en': _en_tokens(c['rows']), 'ko': ko})
    return out


# 단어 모드에서 뒤 내용어에 붙는 영어 작은 낱말(관사 · 전치사 · 접속사 · 대명사 · 소유격 · not · 조동사).
# be · have · do 는 본동사일 수 있어 내용어로 친다(was hovering → was / hovering).
ATTACH = frozenset({
    'the', 'a', 'an', 'of', 'to', 'and', 'or', 'but', 'nor', 'in', 'on', 'at', 'for', 'with', 'by', 'from', 'as',
    'into', 'onto', 'upon', 'unto', 'over', 'under', 'through', 'throughout', 'before', 'after', 'against', 'among',
    'between', 'about', 'above', 'below', 'beside', 'beyond', 'toward', 'towards', 'within', 'without', 'around',
    'near', 'across', 'along', 'behind', 'beneath', 'during', 'except', 'like', 'since', 'till', 'until', 'off',
    'out', 'up', 'down', 'that', 'which', 'who', 'whom', 'whose', 'what', 'so', 'then', 'now', 'if', 'than',
    'because', 'when', 'where', 'while', 'though', 'although', 'yet', 'also', 'even', 'his', 'her', 'their', 'my',
    'your', 'our', 'its', 'thy', 'thine', 'this', 'these', 'those', 'all', 'every', 'each', 'any', 'some', 'no',
    'not', 'he', 'she', 'it', 'they', 'we', 'you', 'i', 'me', 'him', 'them', 'us', 'thee', 'thou', 'ye', 'one',
    'shall', 'will', 'would', 'should', 'may', 'might', 'can', 'could', 'must', 'let',
})
_ALPHA = re.compile(r"[^A-Za-z']")


def _is_content(word):
    w = _ALPHA.sub('', word).strip("'").lower()
    return bool(w) and w not in ATTACH


AUXV = frozenset({'is', 'was', 'are', 'were', 'am', 'be', 'been', 'being', 'have', 'has', 'had', 'having',
                  'do', 'does', 'did'})
# 앞 동사에 붙는 부사 소사(bring forth · cast away · come again) — 따로 끊지 않는다.
BACK = frozenset({'forth', 'away', 'back', 'again', 'together', 'aside', 'apart', 'abroad', 'asunder'})


def _plainw(word):
    return _ALPHA.sub('', word).strip("'").lower()


def _row_tokens(rows):
    """구절 줄들 → [(낱말, 줄 번호, 머리말?, 끊는 자리?)].
    머리말 = 그 줄의 마지막 내용어(BACK 소사 빼고, 없으면 마지막 낱말) — 원어 번호와 한국어를 단다.
    끊는 자리 = 내용어, 또는 내용어가 없어도 한국어 짝이 있는 줄의 머리말(beneath ↔ 아래의 가 사라지지 않게)."""
    toks = []
    for ri, r in enumerate(rows):
        ws = r['t'].split()
        if not ws:
            continue
        heads = [i for i, w in enumerate(ws) if _is_content(w) and _plainw(w) not in BACK]
        h = heads[-1] if heads else len(ws) - 1
        for i, w in enumerate(ws):
            back = _plainw(w) in BACK
            split = (_is_content(w) and not back) or (i == h and not heads and bool(r['u']))
            toks.append((w, ri, i == h, split, back))
    return toks


def _en_tokens(rows):
    """덩어리의 영어 → 낱말마다 [낱말, 번호](번호는 각 줄의 머리말에만) — 화면이 낱말 하나씩 누르게."""
    return [[w, rows[ri]['c'] if head else None] for w, ri, head, _, _ in _row_tokens(rows)]


def _split_words(rows, ko):
    """단어 모드: 덩어리를 내용어마다 끊는다(작은 낱말은 뒤 내용어에, 끝에 남으면 앞 덩어리에,
    forth · away 같은 소사는 앞 동사에). 한국어는 짝이 맞은 줄(u 가 있는 마지막 줄)의 머리말이 든 조각에."""
    toks = _row_tokens(rows)
    subs, buf = [], []
    for w, ri, head, split, back in toks:
        t = (w, ri, head)
        if back and not buf and subs:
            subs[-1].append(t)              # bring / forth → bring forth
            continue
        buf.append(t)
        if split:
            subs.append(buf)
            buf = []
    if buf:
        if subs:
            subs[-1] += buf
        else:
            subs = [buf]
    matched = [ri for ri, r in enumerate(rows) if r['u']]
    target = None
    if matched:
        m = matched[-1]
        target = next((si for si, s in enumerate(subs) for w, ri, head in s if ri == m and head), None)
    if target is None:
        target = len(subs) - 1
    # 한국어 조각을 번호가 같은 줄의 머리말이 든 조각으로 나눈다(And Abraham / said ↔ 아브라함이 / 또 가로되).
    # 번호가 안 맞는 조각은 바로 앞 조각을 따라가고, 맨 앞이면 target.
    sub_of_code = {}
    for si, s in enumerate(subs):
        for w, ri, head in s:
            if head and rows[ri]['c']:
                sub_of_code.setdefault(rows[ri]['c'], si)
    dest, prev = [], None
    for text, code, gap in ko:
        si = sub_of_code.get(code) if code else None
        if si is None:
            si = prev if prev is not None else target
        dest.append(si)
        prev = si
    mine = [[ko[i] for i in range(len(ko)) if dest[i] == si] for si in range(len(subs))]
    # 한 구절이 여러 낱말 조각으로 쪼개졌는데 한국어는 머리말 조각에 한 덩이로 몰렸으면(BSB · 개역한글S 가
    # 'And Abraham said,' ↔ '아브라함이 또 가로되' 를 번호 하나로 묶음), 어절을 한국어 어순대로 나눈다:
    # 마지막 어절은 머리말에, 그 앞 어절들은 앞 낱말 조각에(꾸밈말 · 주어가 앞).
    def main_row(s):
        return next((ri for w, ri, head in reversed(s) if head or _is_content(w)), s[-1][1])
    # be · have · do 조각은 한국어 어절을 받지 않는다(한국어에선 어미에 녹는다: is my shepherd ↔ 나의 목자시니).
    def aux_only(s):
        cw = [_plainw(w) for w, _, _ in s if _is_content(w)]
        return bool(cw) and all(w in AUXV for w in cw)
    for ri in {main_row(s) for s in subs}:
        sis = [si for si, s in enumerate(subs) if main_row(s) == ri]
        hs = next((si for si in sis if any(r == ri and h for _, r, h in subs[si])), None)
        if len(sis) < 2 or hs != sis[-1] or not mine[hs] or any(mine[si] for si in sis if si != hs):
            continue
        sis = [si for si in sis if si == hs or not aux_only(subs[si])]
        eoj = [(e, c) for t, c, _ in mine[hs] for e in t.split()]
        # 어절이 조각보다 많을 때만(한국어에 그 낱말이 없을 수 있다: Moses went out ↔ 다시 나가니).
        if len(sis) < 2 or len(eoj) < len(sis) + 1:
            continue
        cut = len(eoj) - (len(sis) - 1)
        parts = [eoj[:cut]] + [[x] for x in eoj[cut:]]
        for si, part in zip(sis, parts):
            code = part[-1][1] if si == hs else None
            mine[si] = [[' '.join(e for e, _ in part), code, 0]]
    # 짝 있는 낱말만 끊는다: 한국어가 빈 조각은 다음 조각에(끝이면 앞 조각에) 붙인다
    # (is my shepherd ↔ 나의 목자시니 · Moses went out ↔ 다시 나가니).
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
    for si, s in enumerate(subs):
        m = [[t, c, g if j else 0] for j, (t, c, g) in enumerate(mine[si])]
        out.append({'en': [[w, rows[ri]['c'] if head else None] for w, ri, head in s], 'ko': m})
    return out


_NP_PART = ('에게서', '에게로', '에게는', '에게', '께서', '께', '와', '과', '의', '가', '이', '은', '는', '을', '를', '도')
_VERB_END = frozenset('되매늘까즉')                       # '러 · 려' 는 넣으면 나빠졌다(전수조사)
_ADN = {'여러', '오히려', '아울러', '그런즉'}
_PRON_STEM = {'나': '1s', '내': '1s', '우리': '1p', '너': '2', '네': '2', '너희': '2', '당신': '2', '그대': '2',
              '당신들': '2', '그대들': '2', '그': '3s', '그녀': '3s', '그들': '3p',
              '주': '2'}                                 # 기도문의 주께서 · 주께 = You
_SUBJ = ('께서', '가', '이', '은', '는', '도', '만')
_OBJ = ('에게서', '에게로', '에게는', '에게도', '에게', '께', '을', '를', '와', '과', '게')
_EN_SUBJ = {'1s': {'i'}, '1p': {'we'}, '2': {'you', 'ye', 'thou'}, '3s': {'he', 'she'}, '3p': {'they'}}
_EN_OBJ = {'1s': {'me', 'myself'}, '1p': {'us', 'ourselves'}, '2': {'you', 'thee', 'yourself', 'yourselves'},
           '3s': {'him', 'her', 'himself', 'herself'}, '3p': {'them', 'themselves'}}
_DEMO = {'이것', '그것', '저것', '이들', '이곳', '그곳', '거기', '여기'}
_WORD = re.compile(r"[A-Za-z']+")


def _pron_class(word):
    """대명사 주어 · 목적어 어절 → 짝지을 영어 대명사 집합(관형 '나의' · 맨 '내' 는 None)."""
    if not word:
        return None
    for p in _OBJ + _SUBJ:
        stem = word[:-len(p)]
        if word.endswith(p) and stem in _PRON_STEM:
            k = _PRON_STEM[stem]
            return frozenset(_EN_SUBJ[k] if p in _SUBJ else _EN_OBJ[k])
    return None


def _pron_stem(word):
    """대명사 · 지시어로 시작하는 체언(관형 포함) — 뒤 덩어리로."""
    if not word:
        return False
    if word in ('내', '네', '너희', '우리', '그들', '자기'):
        return True
    for p in _NP_PART:
        stem = word[:-len(p)]
        if word.endswith(p) and (stem in _PRON_STEM and stem != '주' or stem in _DEMO or stem == '자기'):
            return True
    return False


def _en_words(chunk):
    return {w.lower() for r in chunk['rows'] for w in _WORD.findall(r['t'])}


# 번호 체계 차이(같은 낱말의 이형 번호) → 대표 번호. 짝 찾기에만 쓰고 화면 · 사전 번호는 원래 그대로.
# 대명사 · be 동사 굴절군은 일부러 뺐다 — 합치면 덩어리가 잘게 쪼개지고 순서가 틀렸다(전수조사).
FOLD_LEX = {}
for _lemma, _forms in {
    'G3708': 'G1492 G3700', 'G3004': 'G2036 G2046 G4483', 'G1520': 'G3391', 'G3173': 'G3187',
    'G1438': 'G4572 G1683', 'G2400': 'G2396', 'G2112': 'G2117',
    'H1980': 'H3212', 'H5117': 'H3240', 'H2396': 'H3169', 'H1841': 'H1840', 'H7122': 'H7125',
    'H4714': 'H4713', 'H3372': 'H3373', 'H3415': 'H7489', 'H2895': 'H2896', 'H3878': 'H3881',
}.items():
    for _f in _forms.split():
        FOLD_LEX[_f] = _lemma


def chunk_text(chunk):
    """덩어리 → (영어 글, 한국어 글)."""
    en = ' '.join(t for t, _ in chunk['en'])
    ko = ''.join((' ' if gap else '') + t for t, _, gap in chunk['ko'])
    return en, ko


def align_verse(en_pairs, ko_text, ko_pieces, fine=True):
    """[(영어 덩어리 글, 한국어 덩어리 글)] — 테스트 · 간단한 쓰임용."""
    return [chunk_text(c) for c in align_units(en_pairs, ko_text, ko_pieces, fine)]
