"""BSB 대역표 → Strong 번호가 붙은 BSB 성경 파일(bible_versions/BSB.SQLite3, KJV+ 와 같은 MyBible 형식).

    python -X utf8 tools/make_bsb.py <bsb_tables.tsv> [출력 경로]

- 자료: Berean Standard Bible 번역 대역표 https://bereanbible.com/bsb_tables.tsv (약 85MB, 저장소에 넣지 않음).
  BSB 본문은 2023-04-30 부터 퍼블릭 도메인(CC0) — https://berean.bible/terms.htm
- 대역표는 BSB 영어 어순으로 한 줄에 영어 구절 하나와 그 원어의 Strong 번호를 담는다. 이것을
  KJV+ 처럼 `구절<S>번호</S>` 로 이어 붙인다 → 화면에는 태그가 빠진 BSB 본문, 원전 분해 · 사전 ·
  영한 끊어 읽기(bibleclip/core/study.py)는 번호로 한국어 Strong 역본과 이어진다.
- 문장부호 · 따옴표는 태그 **앞**(그 구절 쪽)에 둔다(KJV+ 는 뒤) — 구절 하나가 한 덩어리로 끝나게.
- 번역자가 덧붙인 말(대역표에서 통째로 [ ] · { } 인 줄)은 번호를 달지 않는다. 괄호 표시는 모두 지운다.
- 원어만 있고 영어가 없는 줄('-', 'vvv' 자리표시, '. . .')은 건너뛴다.
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


def _clean(s):
    return TAG_RE.sub('', s or '').strip()


def read_rows(tsv_path, book_of):
    """[(book, chapter, verse, [(text, code_or_None)])] in BSB order."""
    csv.field_size_limit(10 ** 7)
    verses = {}
    order = []
    cur = None
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
            if not en or en in SKIP:
                continue
            nt = cur[0] >= 470
            num = (row[ix['Str Grk']] if nt else row[ix['Str Heb']]).strip()
            supplied = bool(re.fullmatch(r'\[[^\[\]]*\]|\{[^{}]*\}', en))   # 통째로 [덧붙임] · {함축}
            begq = re.sub(r'^\d+', '', _clean(row[ix['begQ']]))   # 시편 표제 뒤 절 번호 찌꺼기
            text = begq + en + _clean(row[ix['pnc']]) + _clean(row[ix['endQ']])
            text = _MARKS.sub('', text)                         # [ ] { } 표시는 지우고 낱말은 남긴다
            code = num if (num.isdigit() and not supplied) else None
            verses[cur].append((text, code))
    return [(b, c, v, verses[(b, c, v)]) for (b, c, v) in order if verses[(b, c, v)]]


def verse_text(parts):
    """[(text, code)] → 'In the beginning<S>7225</S> God<S>430</S> …'."""
    out = []
    for text, code in parts:
        out.append(f'{text}<S>{int(code)}</S>' if code else text)
    return ' '.join(out)


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
    for attempt in range(10):      # OneDrive 가 방금 쓴 파일을 잠깐 붙잡을 때가 있다
        try:
            os.replace(tmp, out_path)
            break
        except PermissionError:
            if attempt == 9:
                raise
            time.sleep(1)
    return len(rows)


if __name__ == '__main__':
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = sys.argv[2] if len(sys.argv) > 2 else os.path.join(ROOT, 'bible_versions', 'BSB.SQLite3')
    n = build(sys.argv[1], out)
    print(f'{out}: {n}절, {os.path.getsize(out) / 1e6:.1f}MB')
