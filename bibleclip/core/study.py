"""영한 끊어 읽기(영어 공부 모드) — 영어 Strong 역본(BSB · KJV+)과 한국어 Strong 역본(개역개정S ·
개역한글S)을 Strong 번호로 엮어, 영어 어순대로 덩어리를 짝짓는다(직독직해).

    In the beginning / God / created / the heavens and the earth.
    태초에 / 하나님이 / 창조하시니라 / 천지를

따로 맞춘 표 없이 번호만으로 엮는다. 규칙:
1. 한국어 Strong 조각(형태소 단위)을 실제 본문 어절(띄어쓰기)에 얹어 어절마다 번호를 단다.
2. 같은 번호는 나온 차례대로 짝(영어 n번째 ↔ 한국어 n번째). 관사 · 전치사 같은 작은 낱말은 짝을 갖지 않는다.
3. 짝 없는 영어 구절은 다음 덩어리에 붙고, 같은 한국어 어절을 나누는 이웃 구절은 한 덩어리가 된다.
4. 짝 없는 한국어 어절은 접속어(이는 · 그러므로 …)면 다음 덩어리, 아니면 앞 덩어리에 붙는다.
5. 구절 모드(fine=False)는 문장부호(쉼표 · 마침표 …)에서만 끊는다.
성경 전체(BSB ↔ 개역개정S)에서 한국어가 빈 영어 덩어리는 약 1%(2026-11-25 측정).
"""
import re

# 짝을 갖지 않는 영어 작은 낱말(구절 전체가 이것뿐일 때). be 동사는 본동사일 수 있어 넣지 않는다.
FUNC = frozenset({
    'the', 'a', 'an', 'of', 'to', 'and', 'or', 'but', 'that', 'who', 'which', 'in', 'for', 'with',
    'by', 'on', 'at', 'from', 'as', 'so', 'then', 'now', 'all',
})
# 다음 덩어리에 붙는 한국어 어절(짝 없을 때): 접속어 · 관형사.
CONJ_NEXT = frozenset({
    '이는', '그러므로', '그러나', '또', '곧', '그런데', '그리하여', '이에', '그래서', '그러면', '및', '혹은', '오직',
    '이', '그', '저', '그의', '저의', '이제', '또한',     # 뒤 낱말을 꾸미거나 여는 말
})
_PUNCT_END = re.compile(r'[,;:.?!—]["”’\')\]]*$')
_LEAD_PUNCT = re.compile(r'^([,;:.?!]+)\s*(.*)$', re.S)
_PLAIN = re.compile(r"[\[\]“”‘’\"'.,;:!?()—]")


def _plain(s):
    return _PLAIN.sub('', s).strip().lower()


def ends_clause(s):
    """구절 끝에 문장부호가 있으면 True(구절 모드의 끊는 곳)."""
    return bool(_PUNCT_END.search(s.strip()))


def korean_words(text, pieces):
    """실제 본문 어절 + 번호가 나오는 차례 [(code, 어절 번호)].

    pieces = parse_korean_strongs(...) 결과 [(조각, code)]. 조각을 띄어쓰기를 뺀 본문에서 차례로
    찾아 어느 어절에 들었는지 정한다. 본문과 어긋나는 조각(역본 판 차이)은 건너뛴다."""
    words = (text or '').split()
    flat = ''.join(words)
    starts, pos = [], 0
    for w in words:
        starts.append(pos)
        pos += len(w)
    occ, p = [], 0
    for piece, code in pieces or []:
        s = (piece or '').replace(' ', '')
        if not s:
            continue
        k = flat.find(s, p)
        if k < 0 or k - p > 12:
            continue
        p = k + len(s)
        if code and code not in ('H0', 'G0'):
            j = 0
            while j + 1 < len(starts) and starts[j + 1] <= k:
                j += 1
            occ.append((code, j))
    return words, occ


def align_verse(en_pairs, ko_text, ko_pieces, fine=True):
    """영어 [(구절, code)] + 한국어 본문 · 조각 → [(영어 덩어리, 한국어 덩어리)] 영어 순서."""
    words, occ = korean_words(ko_text, ko_pieces)
    queues = {}
    for code, j in occ:
        q = queues.setdefault(code, [])
        if not q or q[-1] != j:
            q.append(j)
    rows = []
    for text, code in en_pairs:
        text = (text or '').strip()
        # KJV+ 는 문장부호가 다음 구절 앞에 온다(', that') — 앞 구절 끝으로 옮긴다.
        m = _LEAD_PUNCT.match(text)
        if m and rows:
            rows[-1] = (rows[-1][0] + m.group(1), rows[-1][1])
            text = m.group(2)
        if not text:
            continue
        js = set()
        if code and _plain(text) not in FUNC and queues.get(code):
            js.add(queues[code].pop(0))
        rows.append((text, js))
    if not rows:
        return []
    # 덩어리 만들기.
    chunks, pending = [], []
    for text, js in rows:
        if not js:
            pending.append(text)
            continue
        last = chunks[-1] if chunks else None
        if last and (js & last['w']) and not ends_clause(last['en'][-1]):
            last['en'] += pending + [text]
            last['w'] |= js
        else:
            chunks.append({'en': pending + [text], 'w': set(js)})
        pending = []
    if pending:
        if chunks:
            chunks[-1]['en'] += pending
        else:
            chunks.append({'en': pending, 'w': set()})
    if not fine:
        merged = []
        for c in chunks:
            if merged and not any(ends_clause(t) for t in merged[-1]['en']):
                merged[-1]['en'] += c['en']
                merged[-1]['w'] |= c['w']
            else:
                merged.append(c)
        chunks = merged
    owner = {}
    for ci, c in enumerate(chunks):
        for j in c['w']:
            owner.setdefault(j, ci)
    n = len(words)
    for j in range(n):
        if j in owner:
            continue
        prev = next((owner[k] for k in range(j - 1, -1, -1) if k in owner), None)
        nxt = next((owner[k] for k in range(j + 1, n) if k in owner), None)
        if words[j].rstrip(',.') in CONJ_NEXT or prev is None:
            owner[j] = nxt if nxt is not None else prev
        else:
            owner[j] = prev
    if not chunks:
        return []
    out = []
    for ci, c in enumerate(chunks):
        ko = ' '.join(words[j] for j in range(n) if owner.get(j, 0) == ci)
        out.append((' '.join(c['en']), ko))
    return out
