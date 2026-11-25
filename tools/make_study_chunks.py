"""영어공부 '의미 덩어리' 표 만들기 — 성경 전체를 이 PC 에서 한 번 계산한다(앱에는 결과 표만).

    python -X utf8 tools/make_study_chunks.py KRV  [--en BSB] [--out original_lang/study_chunks_BSB_KRV.sqlite]
    python -X utf8 tools/make_study_chunks.py NRKV --books 10,500        (일부 책만 — 시험용)

필요(개발 PC 만, 앱 의존성 아님): pip install torch transformers spacy && python -m spacy download en_core_web_sm
모델: sentence-transformers/LaBSE 6층(낱말 유사도), en_core_web_sm(영어 덩어리 경계).

🔑 저작권: 개역한글(KRV) 표는 git · 릴리스 동봉. 개역개정(NRKV) 표는 이 PC 에만 — git · 릴리스 금지.
방법 · 검수(2026-11-25, 하이쿠 표본 · 갈래 11 · 눈가림): 덩어리 오류율 낱말 단위 14.9% → 의미 덩어리 8.0%
(구절 단위 7.5%, 절당 덩어리 7.0 대 3.0)."""
import argparse
import datetime
import os
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.chdir(ROOT)

from bibleclip.core.study import korean_units  # noqa: E402
from bibleclip.core.study_chunks import align_chunks, write_table  # noqa: E402
from bibleclip.data.original_lang import parse_english_strongs, parse_korean_strongs  # noqa: E402

SMALL = set('the a an of to and or but that who which whom in for with by on at from as then now so'.split())
PUNCT_END = tuple(',;:—.?!')


def english_starts(nlp, words):
    """영어 의미 덩어리 시작 낱말 번호들(직독직해 단위).
    끊는 자리: 문장부호 다음 · 전치사(of 는 앞말과 — 한국어 X의 Y) · 접속사 · 종속절/관계절 시작 ·
    동사구 시작(주어가 대명사 한 낱말이면 함께: He said) · to부정사/목적절/부사절 시작(3낱말+) ·
    목적어/보어 앞(3낱말+). 작은 낱말뿐인 덩어리는 뒤와 합친다."""
    text = ' '.join(words)
    starts, p = [], 0
    for w in words:
        i = text.find(w, p)
        starts.append(i)
        p = i + len(w)
    word_at = {}
    for wi, (s, w) in enumerate(zip(starts, words)):
        for k in range(s, s + len(w)):
            word_at[k] = wi
    doc = nlp(text)
    cut = set()

    def mark(t):
        wi = word_at.get(t.idx)
        if wi is not None and starts[wi] == t.idx:
            cut.add(wi)

    for t in doc:
        if t.dep_ in ('prep', 'agent') and t.pos_ == 'ADP' and t.lower_ != 'of':
            mark(t)
        elif t.dep_ == 'cc':
            # 형용사 · 부사끼리 잇는 and 는 끊지 않는다(His one and only Son)
            conj = [c for c in t.head.children if c.dep_ == 'conj' and c.i > t.i]
            if not (conj and conj[0].pos_ in ('ADJ', 'ADV', 'DET')):
                mark(t)
        elif t.dep_ == 'mark':
            mark(t)
        elif t.tag_ in ('WDT', 'WP', 'WP$', 'WRB') and t.dep_ != 'ROOT':
            mark(t)
        if t.pos_ in ('VERB', 'AUX') and t.dep_ not in ('aux', 'auxpass'):
            subj = [c for c in t.children if c.dep_ in ('nsubj', 'nsubjpass', 'expl')]
            group = [c for c in t.children if c.dep_ in ('aux', 'auxpass', 'neg') and c.i < t.i] + [t]
            gs = min(x.i for x in group)
            while gs - 1 >= 0 and doc[gs - 1].dep_ == 'advmod' and doc[gs - 1].head == t and doc[gs - 1].pos_ == 'ADV':
                gs -= 1
            if subj and subj[0].i < gs and (subj[0].pos_ != 'PRON' or len(list(subj[0].subtree)) >= 3):
                mark(doc[gs])
            # 문장 앞 부사구 뒤의 주어는 따로(In the beginning / God created)
            if subj:
                se = subj[0].left_edge
                for c in t.children:
                    if c.i < se.i and c.dep_ in ('prep', 'advmod', 'npadvmod', 'advcl') and len(list(c.subtree)) >= 2:
                        mark(se)
                        break
            if t.dep_ in ('xcomp', 'ccomp', 'advcl') and t.i > 0:
                span = list(t.subtree)
                if len(span) >= 3 and span[0].i > t.head.i:
                    mark(span[0])
            for c in t.children:
                if c.dep_ in ('dobj', 'attr', 'acomp', 'oprd', 'dative') and c.i > t.i:
                    span = list(c.subtree)
                    if len(span) >= 3:
                        mark(doc[span[0].i])
    for wi, w in enumerate(words[:-1]):
        if w.rstrip('”’"\')]').endswith(PUNCT_END):
            cut.add(wi + 1)
    cut.discard(0)
    b = [0] + sorted(cut)
    groups = [list(range(b[k], b[k + 1] if k + 1 < len(b) else len(words))) for k in range(len(b))]
    out, carry = [], []
    for g in groups:
        g = carry + g
        if all(words[i].lower().strip('“‘"\'(,.;:') in SMALL for i in g) and g[-1] != len(words) - 1:
            carry = g
            continue
        carry = []
        out.append(g)
    if carry:
        if out:
            out[-1] += carry
        else:
            out.append(carry)
    return [g[0] for g in out]


class Embedder:
    """LaBSE 6층 낱말 벡터(낱말 = 글자 구간, 하위 토큰 평균)."""

    def __init__(self):
        import torch
        from transformers import AutoModel, AutoTokenizer
        self.torch = torch
        self.tok = AutoTokenizer.from_pretrained('sentence-transformers/LaBSE')
        self.mdl = AutoModel.from_pretrained('sentence-transformers/LaBSE', output_hidden_states=True).eval()

    def vectors(self, text, pieces):
        torch = self.torch
        sp, p = [], 0
        for t in pieces:
            i = text.find(t, p)
            i = p if i < 0 else i
            sp.append((i, i + len(t)))
            p = i + len(t)
        enc = self.tok(text, return_offsets_mapping=True, return_tensors='pt', truncation=True, max_length=512)
        offs = enc.pop('offset_mapping')[0].tolist()
        with torch.no_grad():
            hs = self.mdl(**enc).hidden_states[6][0]
        vs = []
        for s, e in sp:
            idx = [k for k, (a, b) in enumerate(offs) if b > a and a < e and b > s]
            vs.append(hs[idx].mean(0) if idx else torch.zeros(hs.shape[1]))
        return torch.stack(vs)

    def sims(self, E, K):
        n = self.torch.nn.functional.normalize
        return (n(E, dim=1) @ n(K, dim=1).T).tolist(), (E @ K.T).tolist()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('ko')
    ap.add_argument('--en', default='BSB')
    ap.add_argument('--out')
    ap.add_argument('--books')
    ap.add_argument('--refs', help='JSON [[책, 장, 절]…] — 그 절만 계산(규칙 다듬기용 표본)')
    a = ap.parse_args()
    out = a.out or os.path.join(ROOT, 'original_lang', f'study_chunks_{a.en}_{a.ko}.sqlite')

    import spacy
    from bibleclip.core.library import Library
    lib = Library()
    attr = next((at for k, at, _ in lib.STUDY_KO if k == a.ko), None)
    if attr is None or a.ko not in lib.dbs or a.en not in lib.dbs:
        sys.exit(f'역본 없음: {a.en} / {a.ko}')
    sdb = getattr(lib, attr)
    nlp = spacy.load('en_core_web_sm')
    emb = Embedder()
    books = [int(x) for x in a.books.split(',')] if a.books else None
    import sqlite3
    p = os.path.join(ROOT, 'bible_versions', f'{a.en}.SQLite3')
    pairs_all = sorted(sqlite3.connect(p).execute('SELECT DISTINCT book_number, chapter FROM verses').fetchall())
    if books:
        pairs_all = [x for x in pairs_all if x[0] in books]
    only = None
    if a.refs:
        import json
        only = {tuple(r) for r in json.load(open(a.refs, encoding='utf-8'))}
        pairs_all = [x for x in pairs_all if any(r[:2] == x for r in only)]
    check_log = open(out + '.check.txt', 'w', encoding='utf-8')
    bad = 0
    t0 = time.time()
    chapters = {}
    nv = 0
    for n, (b, c) in enumerate(pairs_all):
        ko_text = dict(lib.dbs[a.ko].get_verses(b, c))
        ko_pieces = {v: parse_korean_strongs(t) for v, t in sdb.get_chapter_verses(b, c)}
        res = {}
        for v, raw in lib.dbs[a.en].get_chapter_raw(b, c):
            pairs = parse_english_strongs(raw, b)
            en = [[w, code, pi] for pi, (ph, code) in enumerate(pairs) for w in ph.split()]
            if not en or (only is not None and (b, c, v) not in only):
                continue
            kt = ko_text.get(v, '') or ''
            ko = [[u['t'], u['c'], u['w']] for u in korean_units(kt, ko_pieces.get(v, []))]
            words = [w for w, _, _ in en]
            starts = english_starts(nlp, words)
            if ko:
                et = ' '.join(words)
                cos, dot = emb.sims(emb.vectors(et, words), emb.vectors(kt, [t for t, _, _ in ko]))
            else:
                cos = dot = []
            res[v] = got = align_chunks(en, ko, kt, starts, cos, dot)
            nv += 1
            # 자동 점검(장마다, 토큰 없음): 조각 빠짐 · 한국어 빈 덩어리 · 덩어리 수가 이상함
            probs = []
            if sum(len(x['ko']) for x in got) != len(ko):
                probs.append('조각 수 불일치')
            if ko and any(not x['ko'] for x in got):
                probs.append('한국어 빈 덩어리')
            if ' '.join(w for x in got for w, _ in x['en']) != ' '.join(words):
                probs.append('영어 어긋남')
            if len(words) >= 12 and len(got) == 1:
                probs.append('긴 절이 한 덩어리')
            if probs:
                bad += 1
                check_log.write(f'{b}:{c}:{v}' + chr(9) + ' · '.join(probs) + chr(10))
        chapters[(b, c)] = res
        if n % 50 == 0:
            el = time.time() - t0
            print(f'{n + 1}/{len(pairs_all)} 장 · {nv} 절 · {el / 60:.1f}분 · 남은 예상 '
                  f'{el / (n + 1) * (len(pairs_all) - n - 1) / 60:.0f}분', flush=True)
    info = {'en': a.en, 'ko': a.ko, 'made': datetime.date.today().isoformat(), 'verses': str(nv),
            'method': 'spaCy en_core_web_sm 덩어리 + 원어 번호(강제) + LaBSE 6층 낱말 짝(tools/make_study_chunks.py)'}
    for i in range(60):
        try:
            write_table(out, info, chapters)
            break
        except PermissionError:          # OneDrive 가 새 파일을 잠깐 잡는다
            time.sleep(1)
    check_log.close()
    print(f'완료 {out} · {nv} 절 · {(time.time() - t0) / 60:.1f}분 · {os.path.getsize(out) / 1e6:.1f} MB · '
          f'자동 점검 걸린 절 {bad} ({out}.check.txt)')


if __name__ == '__main__':
    main()
