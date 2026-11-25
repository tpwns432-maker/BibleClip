"""BSB 대역표 → Strong 번호가 붙은 BSB 성경 파일(bible_versions/BSB.SQLite3, KJV+ 와 같은 MyBible 형식).

    python -X utf8 tools/make_bsb.py <bsb_tables.tsv> [출력 경로]
    python -X utf8 tools/make_bsb.py --check <bsb.txt> [BSB.SQLite3]   # 공식 본문과 절마다 대조

- 자료: Berean Standard Bible 번역 대역표 https://bereanbible.com/bsb_tables.tsv (약 85MB, 저장소에 넣지 않음).
  BSB 본문은 2023-04-30 부터 퍼블릭 도메인(CC0) — https://berean.bible/terms.htm
- 대역표는 BSB 영어 어순으로 한 줄에 영어 구절 하나와 그 원어의 Strong 번호를 담는다. 이것을
  KJV+ 처럼 `구절<S>번호</S>` 로 이어 붙인다 → 화면에는 태그가 빠진 BSB 본문, 원전 분해 · 사전 ·
  영한 끊어 읽기(bibleclip/core/study.py)는 번호로 한국어 Strong 역본과 이어진다.
- 문장부호 · 따옴표는 태그 **앞**(그 구절 쪽)에 둔다(KJV+ 는 뒤) — 구절 하나가 한 덩어리로 끝나게.
- 번역자가 덧붙인 말(대역표에서 통째로 [ ] · { } 인 줄)은 번호를 달지 않는다. 괄호 표시는 모두 지운다.
- 원어만 있고 영어가 없는 줄('-', 'vvv' 자리표시, '. . .')은 건너뛰되, 그 줄의 문장부호 · 따옴표(pnc · endQ ·
  End text)는 앞 구절 끝에, 여는 따옴표(begQ)는 다음 구절 앞에 옮긴다(버리면 5,616절에서 쉼표 · 마침표가 빠졌다).
"""
import csv
import os
import re
import sqlite3
import sys
import time

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

TAG_RE = re.compile(r'<[^>]*>')
SKIP = {'-', 'vvv', '. . .', '…'}
_MARKS = re.compile(r'[\[\]{}]')
_PLACEHOLDER = re.compile(r'(?<=\s)(?:\.\s\.\s\.|…|-|vvv)(?=\s)')
_SPACE_BEFORE = re.compile(r'\s+([,.;:?!”’)\]])')
_STARTS_TIGHT = re.compile(r'^[,.;:?!)\]”’—]')     # 앞 구절에 붙여 쓰는 문장부호 · 닫는 따옴표
_ENDS_TIGHT = re.compile(r'[—(“‘](?:<S>\d+</S>)?$')   # 줄표 · 여는 괄호 · 여는 따옴표 뒤는 붙여 쓴다


def _clean(s):
    return TAG_RE.sub('', s or '').strip()


# 대역표 원문의 오탈자(공식 bsb.txt 와 대조해 찾음).
_TYPOS = {'shekelsof': 'shekels of'}


def _tidy(text):
    """대역표 글의 띄어쓰기 · 자리표시 찌꺼기 정리 — 공식 bsb.txt 와 같아지도록(2026-11-25 대조 99.7%+)."""
    for a, b in _TYPOS.items():
        text = text.replace(a, b)
    text = re.sub(r'\s*\bvvv\b\s*', ' ', text)                 # '(vvv meaning' → '(meaning'
    text = re.sub(r'\s{2,}', ' ', text)
    text = _SPACE_BEFORE.sub(r'\1', text)                      # 'Likewise , every' · '1 ,700' · 'No, ”'
    text = re.sub(r'([“‘(])\s+', r'\1', text)                   # '‘ I never' · '( meaning'
    text = re.sub(r'\s*—\s*', '—', text)                       # 줄표는 붙여 쓴다
    text = re.sub(r'([.?!;:])([A-Z“‘])', r'\1 \2', text)          # 'the web.Then'
    return text.strip()


def read_rows(tsv_path, book_of):
    """[(book, chapter, verse, [(text, code_or_None)])] in BSB order."""
    csv.field_size_limit(10 ** 7)
    verses = {}
    order = []
    cur = None
    carry = {}                      # 절 → 다음 구절 앞에 붙일 여는 따옴표
    with open(tsv_path, encoding='utf-8-sig', newline='') as f:
        rd = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
        head = [h.strip() for h in next(rd)]
        ix = {h: i for i, h in enumerate(head)}
        for row in rd:
            if len(row) < len(head) - 1:
                continue
            row += [''] * (len(head) - len(row))
            vid = row[ix['VerseId']].strip()
            if vid:
                m = re.match(r'^(.*\S)\s+(\d+):(\d+)$', vid)
                if not m:
                    raise SystemExit(f'알 수 없는 절 표기: {vid!r}')
                bn = book_of(m.group(1))
                cur = (bn, int(m.group(2)), int(m.group(3)))
                if cur not in verses:
                    verses[cur] = []
                    order.append(cur)
            if cur is None:
                continue
            en = _clean(row[ix['BSB version']])
            # 구절 안에 섞인 자리표시('. . . 40,500', '- Hezron')는 지운다.
            en = _PLACEHOLDER.sub(' ', ' ' + en + ' ').strip()
            begq = re.sub(r'^\d+', '', _clean(row[ix['begQ']]))   # 시편 표제 뒤 절 번호 찌꺼기
            if not en or en in SKIP:
                # 영어 낱말이 없는 줄('-' · '. . .' · 'vvv')에도 문장부호 · 따옴표가 달려 있다(창 1:7 'above.',
                # 창 3:4 'die,”') — 버리지 말고 닫는 쪽은 앞 구절 끝에, 여는 따옴표는 다음 구절 앞에 옮긴다.
                tail = _clean(row[ix['pnc']]) + _clean(row[ix['endQ']]) + _clean(row[ix['End text']])
                if tail and verses[cur]:
                    t, c = verses[cur][-1]
                    verses[cur][-1] = (_tidy(_MARKS.sub('', t + tail)), c)
                if begq:
                    carry[cur] = carry.get(cur, '') + begq
                continue
            nt = cur[0] >= 470
            num = (row[ix['Str Grk']] if nt else row[ix['Str Heb']]).strip()
            supplied = bool(re.fullmatch(r'\[[^\[\]]*\]|\{[^{}]*\}', en))   # 통째로 [덧붙임] · {함축}
            begq = carry.pop(cur, '') + begq
            text = begq + en + _clean(row[ix['pnc']]) + _clean(row[ix['endQ']]) + _clean(row[ix['End text']])
            text = _MARKS.sub('', text)                         # [ ] { } 표시는 지우고 낱말은 남긴다
            # 대역표 글 안의 띄어쓰기 찌꺼기('Likewise , every' · '1 ,700' · '{ goodbye } .' · 'No, ”')를 정리.
            text = _tidy(text)
            code = num if (num.isdigit() and not supplied) else None
            verses[cur].append((text, code))
    for key in order:
        parts = verses[key]
        if parts:
            t, c = parts[-1]
            parts[-1] = (re.sub('’’$', '', t), c)
    return [(b, c, v, verses[(b, c, v)]) for (b, c, v) in order if verses[(b, c, v)]]


def verse_text(parts):
    """[(text, code)] → 'In the beginning<S>7225</S> God<S>430</S> …'."""
    out = ''
    for text, code in parts:
        seg = f'{text}<S>{int(code)}</S>' if code else text
        # 줄표는 앞뒤를 띄우지 않는다(BSB: 'with you—birds').
        joint = '' if (not out or _STARTS_TIGHT.match(text) or _ENDS_TIGHT.search(out)) else ' '
        out += joint + seg
    return out


def build(tsv_path, out_path):
    from bibleclip.core.library import Library
    lib = Library()
    kjv = lib.dbs.get('KJV+')
    if kjv is None:
        raise SystemExit('bible_versions/KJV+.SQLite3 가 필요합니다(책 이름 표를 빌려 쓴다).')
    from bibleclip.data.original_lang import PROTESTANT_BOOK_ORDER
    seen = []

    def book_of(name):
        """대역표는 창세기~요한계시록 66권 차례 — 처음 나온 차례로 우리 책 번호(10~730)를 매긴다."""
        if name not in seen:
            seen.append(name)
        return PROTESTANT_BOOK_ORDER[seen.index(name)]

    rows = read_rows(tsv_path, book_of)
    if len(seen) != 66:
        raise SystemExit(f'책이 66권이 아님: {len(seen)}')
    # 이름 확인: 대역표 책 이름과 우리 번호가 맞는지 몇 권 맞춰 본다.
    for i, want in ((0, 10), (21, 260), (39, 470), (65, 730)):
        assert PROTESTANT_BOOK_ORDER[i] == want, (seen[i], want)
    tmp = out_path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript("""
        CREATE TABLE info (name TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (name));
        CREATE TABLE books (book_number NUMERIC NOT NULL, short_name TEXT NOT NULL, long_name TEXT NOT NULL,
                            book_color TEXT NOT NULL, PRIMARY KEY (book_number));
        CREATE TABLE books_all (book_number NUMERIC NOT NULL, short_name TEXT NOT NULL, long_name TEXT NOT NULL,
                                book_color TEXT NOT NULL, is_present BOOLEAN NOT NULL, PRIMARY KEY (book_number));
        CREATE TABLE verses (book_number NUMERIC NOT NULL, chapter NUMERIC NOT NULL, verse NUMERIC NOT NULL,
                             text TEXT NOT NULL DEFAULT '', PRIMARY KEY (book_number, chapter, verse));
    """)
    info = {
        'description': "Berean Standard Bible with Strong's numbers",
        'language': 'en',
        'strong_numbers': 'true',
        'chapter_string': 'Chapter',
        'chapter_string_ps': 'Psalm',
        'russian_numbering': 'false',
        'right_to_left': 'false',
        'detailed_info': ('The Holy Bible, Berean Standard Bible, BSB is produced in cooperation with Bible Hub, '
                          'Discovery Bible, OpenBible.com, and the Berean Bible Translation Committee. '
                          'Dedicated to the public domain (CC0) on April 30, 2023 — https://berean.bible/terms.htm . '
                          "Strong's tagging from the BSB translation tables (bereanbible.com/bsb_tables.tsv)."),
    }
    con.executemany('INSERT INTO info VALUES (?, ?)', list(info.items()))
    src = sqlite3.connect(kjv.db_path)
    present = {b for b, *_ in rows}
    for r in src.execute('SELECT book_number, short_name, long_name, book_color FROM books ORDER BY book_number'):
        if r[0] in present:
            con.execute('INSERT INTO books VALUES (?, ?, ?, ?)', r)
            con.execute('INSERT INTO books_all VALUES (?, ?, ?, ?, 1)', r)
    src.close()
    con.executemany('INSERT INTO verses VALUES (?, ?, ?, ?)',
                    [(b, c, v, verse_text(parts)) for b, c, v, parts in rows])
    con.commit()
    con.execute('VACUUM')
    con.close()
    for attempt in range(60):      # OneDrive 가 방금 쓴 파일을 한동안 붙잡을 때가 있다(실측 10초 넘게)
        try:
            os.replace(tmp, out_path)
            break
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(1)
    return len(rows)


def check(official_txt, db_path):
    """공식 BSB 본문(https://bereanbible.com/bsb.txt)과 절마다 글자 그대로 대조 → (같은 절, 비교한 절, 다른 절 목록).
    2026-11-25: 31,086/31,086 같음(BSB 가 각주로 돌린 16절은 대역표에 없어 비교 밖)."""
    from bibleclip.data.original_lang import PROTESTANT_BOOK_ORDER
    from bibleclip.text_utils import clean_text
    off, seen = {}, []
    for line in open(official_txt, encoding='utf-8-sig'):
        p = line.rstrip('\r\n').split('\t')
        m = re.match(r'^(.*\S)\s+(\d+):(\d+)$', p[0]) if len(p) > 1 else None
        if not m:
            continue
        if m.group(1) not in seen:
            seen.append(m.group(1))
        off[(PROTESTANT_BOOK_ORDER[seen.index(m.group(1))], int(m.group(2)), int(m.group(3)))] = p[1].strip()
    con = sqlite3.connect(f'file:{db_path}?mode=ro', uri=True)
    ours = {(b, c, v): clean_text(t) for b, c, v, t in con.execute('SELECT book_number, chapter, verse, text FROM verses')}
    con.close()
    diff = sorted(k for k in ours if k in off and ours[k] != off[k])
    both = sum(1 for k in ours if k in off)
    return both - len(diff), both, diff


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == '--check':
        db = sys.argv[3] if len(sys.argv) > 3 else os.path.join(ROOT, 'bible_versions', 'BSB.SQLite3')
        same, both, diff = check(sys.argv[2], db)
        print(f'공식 본문과 같은 절 {same}/{both}')
        for k in diff[:20]:
            print('  다름', k)
        sys.exit(1 if diff else 0)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'bible_versions', 'BSB.SQLite3')
    n = build(sys.argv[1], out)
    print(f'{out}: {n}절, {os.path.getsize(out) / 1e6:.1f}MB')
