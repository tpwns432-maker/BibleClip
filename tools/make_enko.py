"""영한 뜻풀이 자료 만들기 → original_lang/enko_dict.sqlite (영어공부 카드, bibleclip/core/enko.py).

    python -X utf8 tools/make_enko.py <kengdic.tsv> [출력 경로]

1) bible — 성경 영한 낱말장. BSB(Strong) 와 개역한글S 를 절마다 같은 Strong 번호끼리 짝지어, 성경 전체에서
   '영어 낱말 → 옮겨진 한국어' 를 센다(창 9:9 covenant(H1285) ↔ 언약을(H1285) → covenant: 언약 +1).
   한국어는 마지막 어절의 조사를 떼고, '…하사 · …하시고' 같은 동사는 '…하다' 로 모은다.
   재료가 BSB(CC0) · 개역한글(퍼블릭 도메인) · 개역한글S(저장소에 있는 것)라 배포에 제약이 없다.
2) general — 일반 영한 뜻. kengdic(https://github.com/garfieldnate/kengdic, Joe Speigle 외, MPL 2.0 / LGPL 2.0+)
   의 한→영 항목(kengdic.tsv)을 영어 gloss 기준으로 뒤집는다. 이 표는 MPL 2.0 으로 배포한다(info 표에 적음).

영어 낱말은 원형으로 모은다(offerings → offering, cried → cry) — 원형인지는 kengdic 에 있는 낱말로 판단.
"""
import collections
import csv
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bibleclip.core.enko import content_words, lemmas  # noqa: E402

OUT = os.path.join(ROOT, 'original_lang', 'enko_dict.sqlite')
JOSA = re.compile(r'(에게서|에게로|으로써|으로|에게|에서|께서|까지|부터|이라|이니|이요|하고|들의|들이|들을|들은|들에게|들도|'
                  r'와|과|을|를|은|는|이|가|의|에|로|도|만|께|여|아|야)$')
# 조사처럼 끝나지만 낱말 그 자체(아들의 '들' · 여호와의 '와' 를 떼면 '아' · '여호' 가 된다).
KEEP = frozenset({'아들', '여호와', '하나님', '사람', '나라', '아이', '바다', '머리', '다리', '소리', '자리', '거리', '우리',
                  '나귀', '가나', '시내', '모세', '노아', '여자', '남자', '부자', '제자', '왕자', '아비', '어미'})
# 낱말장 숫자가 뜻이 없는 영어 동사(be · have · do) — 일반 뜻만 보인다.
NO_BIBLE = frozenset({'be', 'have', 'do', 'will', 'shall', 'may', 'can', 'must', 'let'})
VERB = re.compile(r'^(.+?)(하|되)(시|셨|신|실|심|사|여|였|고|며|니|라|리|매|면|게|지|는|던|자|오|옵|소|ㅂ|기|나|느|다)')
GENERAL_TOP = 8
# 개역한글S 가 내용어 번호에 함께 붙여 둔 자리 낱말 — 낱말장에선 잡음(맨 앞 하나는 남긴다).
GENERIC = frozenset('자 그 중 위 때 것 바 이 저 내 네 수 줄 곧 또 및 등 앞 뒤 안 밖 하나 있 받 없 하다 되다 행하다 위하다 '
                    '향하다 말미암다 인하다 대하다 같다 아니하다 아니 못 말 일 곳 날 사람'.split())
BIBLE_TOP = 6


def norm_ko(piece):
    """개역한글S 조각 → 낱말장에 셀 꼴: 마지막 어절 · 조사 떼기 · 동사는 '…하다'."""
    w = (piece or '').split()[-1] if (piece or '').split() else ''
    w = re.sub(r'[^가-힣]', '', w)
    if not w:
        return ''
    m = VERB.match(w)
    if m and len(m.group(1)) >= 1:
        return m.group(1) + m.group(2) + '다'
    for _ in range(2):                       # '선지자들의' → '선지자'
        if w in KEEP:
            break
        x = JOSA.sub('', w)
        if x == w or not x:
            break
        w = x
    if len(w) >= 3 and w.endswith('들') and w not in KEEP:
        w = w[:-1]                           # 복수 '선지자들' → '선지자'(두 글자 '아들'은 그대로)
    return w


def read_kengdic(path):
    rev = collections.defaultdict(collections.Counter)
    with open(path, encoding='utf-8', newline='') as f:
        for r in csv.DictReader(f, delimiter='\t'):
            gloss = (r.get('gloss') or '').strip().lower()
            ko = (r.get('surface') or '').strip()
            if not gloss or not ko or len(ko) > 15:
                continue
            for part in re.split(r'[;,/]', gloss):
                part = re.sub(r'^(to|a|an|the)\s+', '', re.sub(r'\s+', ' ', part.strip()))
                part = re.sub(r'\(.*?\)', '', part).strip()
                if part and len(part.split()) <= 3 and re.match(r"^[a-z][a-z' \-]*$", part):
                    rev[part][ko] += 1
    out = {}
    for w, c in rev.items():
        ks = sorted(c, key=lambda k: (-c[k], len(k), k))
        out[w] = ks[:GENERAL_TOP]
    return out


def canonical(word, known):
    """영어 낱말 → 낱말장 열쇠(원형). kengdic 에 있는 첫 후보, 없으면 그대로."""
    for lem in lemmas(word):
        if lem in known:
            return lem
    return word


def build_bible(known):
    from bibleclip.core.library import Library
    from bibleclip.data.original_lang import parse_english_strongs, parse_korean_strongs
    lib = Library()
    bsb, ks = lib.dbs.get('BSB'), lib.bethlehem_strongs
    if bsb is None or ks is None:
        raise SystemExit('bible_versions/BSB.SQLite3 와 original_lang/개역한글S.sdb 가 필요합니다.')
    gl = collections.defaultdict(collections.Counter)
    chapters = bsb.conn.execute('SELECT DISTINCT book_number, chapter FROM verses').fetchall()
    for b, c in chapters:
        ko = {v: parse_korean_strongs(t) for v, t in ks.get_chapter_verses(b, c)}
        for v, raw in bsb.get_chapter_raw(b, c):
            queue = collections.defaultdict(list)
            for piece, code in ko.get(v, []):
                if code and code not in ('H0', 'G0'):
                    queue[code].append(piece)
            for phrase, code in parse_english_strongs(raw, b):
                if not code or not queue.get(code):
                    continue
                piece = queue[code].pop(0)
                heads = [w for w in content_words(phrase) if w.strip("'’").isalpha()]
                k = norm_ko(piece)
                if not heads or not k:
                    continue
                key = canonical(heads[0], known)
                if key not in NO_BIBLE:
                    gl[key][k] += 1
    out = {}
    for w, c in gl.items():
        items = c.most_common()
        top = items[0][1]
        keep = [[k, n] for i, (k, n) in enumerate(items)
                if i == 0 or (k not in GENERIC and n >= max(2, top * 0.03))]
        out[w] = keep[:BIBLE_TOP]
    return out


def write(out_path, bible, general):
    tmp = out_path + '.tmp'
    if os.path.exists(tmp):
        os.remove(tmp)
    con = sqlite3.connect(tmp)
    con.executescript("""
        CREATE TABLE info (name TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE bible (word TEXT PRIMARY KEY, data TEXT NOT NULL);
        CREATE TABLE general (word TEXT PRIMARY KEY, data TEXT NOT NULL);
    """)
    info = {
        'description': 'BibleClip English-Korean glosses for the English Study card',
        'generated': date.today().isoformat(),
        'bible_source': ('Bible glossary: BSB (Berean Standard Bible, CC0 — berean.bible) paired with 개역한글 '
                         '(public domain) by Strong\'s numbers, counted over the whole Bible.'),
        'general_source': ('kengdic — https://github.com/garfieldnate/kengdic (Joe Speigle and contributors). '
                           'The "general" table is derived from kengdic.tsv and is distributed under the '
                           'Mozilla Public License 2.0 (https://www.mozilla.org/MPL/2.0/).'),
        'license': 'general: MPL-2.0 (from kengdic). bible: no restrictions (CC0 / public-domain sources).',
    }
    con.executemany('INSERT INTO info VALUES (?, ?)', list(info.items()))
    con.executemany('INSERT INTO bible VALUES (?, ?)',
                    [(w, json.dumps(v, ensure_ascii=False)) for w, v in sorted(bible.items())])
    con.executemany('INSERT INTO general VALUES (?, ?)',
                    [(w, json.dumps(v, ensure_ascii=False)) for w, v in sorted(general.items())])
    con.commit()
    con.execute('VACUUM')
    con.close()
    for attempt in range(60):                # OneDrive 가 방금 쓴 파일을 한동안 붙잡을 때가 있다
        try:
            os.replace(tmp, out_path)
            break
        except PermissionError:
            if attempt == 59:
                raise
            time.sleep(1)


def main():
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = sys.argv[2] if len(sys.argv) > 2 else OUT
    general = read_kengdic(sys.argv[1])
    bible = build_bible(set(general))
    write(out, bible, general)
    print(f'{out}: 낱말장 {len(bible)}개 · 일반 뜻 {len(general)}개, {os.path.getsize(out) / 1e6:.1f}MB')


if __name__ == '__main__':
    main()
