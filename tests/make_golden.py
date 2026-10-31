"""Golden vectors shared by the desktop (Python) and Android (Kotlin) engines.

Run with:  python -X utf8 tests/make_golden.py          (rewrite tests/golden/*.json)
           python -X utf8 tests/make_golden.py --check  (fail if they are stale)

The Android app re-implements the reference parser, text cleaner and output
formatter in Kotlin (docs/ANDROID_PLAN.md). Both sides read the SAME JSON:
this script writes it from the Python engine, android/app/src/test compares the
Kotlin port against it. Fix the Python engine first, re-run this, then port.

Only the git-tracked bibles (KRV, KJV+) are used, so CI and every PC produce the
same output whatever else sits in the user's bible_versions/.

It also writes the tables the Kotlin port loads at runtime (book names, 두벌식
자판 map, default settings) to android/app/src/main/assets/core/tables.json, so
bibleclip/constants.py stays the one source instead of a hand-copied Kotlin table.
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from bibleclip.core.engine import Engine
from bibleclip.core.library import Library
from bibleclip.data.bible_db import BibleDB
from bibleclip import constants as C
from bibleclip.text_utils import clean_text, convert_qwerty_to_hangul

GOLDEN_DIR = os.path.join(ROOT, 'tests', 'golden')
TABLES = os.path.join(ROOT, 'android', 'app', 'src', 'main', 'assets', 'core', 'tables.json')
VERSIONS = ('KRV', 'KJV+')

REFERENCES = [
    '요 3:16', '요3:16', '요한복음 3장 16절', '요 3:16-18', '요 3:16,18-20', '요 3:16~18',
    '요 3：16', '요 3:16，17', '요 3 : 16 - 18', '창1:1', '창세기 1장', '창 1', '창세기 1장 1-3절',
    '시 23편 1절', '시편 23:1-6', '요일 4:8', '요이 1:1', '요삼 1:2', '요일4장8절', '요 1:1',
    '1요 4:8', '요15:4', '요2서 1:1', '삼상 17:45', '고전 13:4-7', '롬 8:28', '계 22:21',
    '마 5:3-12 말씀', '오늘 본문은 요 3:16 입니다', '요 3:16, 롬 8:28', '출 20장 1-17절',
    'John 3:16', 'john 3:16-18', '1 John 4:8', '1John 4:8', 'Gen 1:1', 'Ps 23:1', 'Rev 22:21',
    'Song 2:1', '1Th 5:17', '1 Thess 5:17', 'Matthew 5', 'dy 3:16', 'ckd 1:1', 'tl 23:1',
    '요', '3:16', 'abc', '', '   ', '사랑', '#사랑', '# 믿음 소망',
]

TEXTS = [
    '<n>[말씀이 육신이 되시다]</n> 태초에 말씀이 계시니라',
    '<pb/>지존자여 십현금과',
    'In the beginning<S>7225</S> God<S>430</S> created<S>1254</S>',
    '<f>[a]</f>본문<f>각주</f> 끝',
    '[말씀이 육신이 되시다] 태초에',
    '  여러   칸  띄움  ',
    '<J>Jesus</J> wept.',
    '',
]

QWERTY = ['dy', 'cks', 'rh', 'tkatkd', 'dyrlq', 'Dy', 'dy1', '']

# (label, settings overrides, output order, input text)
FORMATS = [
    ('default', {}, ['KRV'], '요 3:16'),
    ('two-versions', {}, ['KRV', 'KJV+'], '요 3:16-17'),
    ('korean-style', {'chapter_verse_format': 'korean'}, ['KRV'], '요 3:16-17'),
    ('brackets', {'bracket_style': '[]'}, ['KRV'], '롬 8:28'),
    ('parens-after', {'bracket_style': '()', 'ref_position': 'after'}, ['KRV'], '롬 8:28'),
    ('tilde', {'range_symbol': '~'}, ['KRV'], '고전 13:4-7'),
    ('sep-hyphen', {'ref_body_separator': ' - '}, ['KRV'], '창 1:1'),
    ('no-header', {'show_version_header': False}, ['KRV'], '창 1:1'),
    ('hide-ref', {'hide_reference': True}, ['KRV'], '창 1:1-2'),
    ('hide-ref-no-header', {'hide_reference': True, 'show_version_header': False}, ['KRV'], '창 1:1'),
    ('newline', {'output_mode': 'newline'}, ['KRV'], '시 23:1-3'),
    ('newline-cv', {'output_mode': 'newline', 'newline_show_cv': True}, ['KRV'], '시 23:1-3'),
    ('newline-single', {'output_mode': 'newline'}, ['KRV'], '시 23:1'),
    ('long-name', {'book_name': 'long_ko'}, ['KRV', 'KJV+'], '요 3:16'),
    ('discontinuous', {}, ['KRV'], '요 3:16,18-19'),
    ('whole-chapter', {}, ['KRV'], '시 117'),
    ('merged-verse', {}, ['KRV'], '렘 32:3-5'),
    ('strongs-stripped', {}, ['KJV+'], 'Gen 1:1'),
    ('template', {'custom_format_enabled': True,
                  'custom_format_template': '{book_full} {chap}:{verse} {content} ({version}) {x}'},
     ['KRV'], '요 3:16'),
    ('template-off', {'custom_format_enabled': False,
                      'custom_format_template': '{content}'}, ['KRV'], '요 3:16'),
    ('parallel', {'custom_format_enabled': True,
                  'custom_format_template': '{book_short} {chap}:{verse}\n{content}\n{content2}\n— {version}/{version2}'},
     ['KRV', 'KJV+'], '요 3:16-17'),
    ('parallel-one-version', {'custom_format_enabled': True,
                              'custom_format_template': '{content} / {content2}'},
     ['KRV'], '요 3:16'),
    ('missing-verse', {}, ['KRV'], '요 3:99'),
    ('partly-missing', {}, ['KRV'], '요 21:24-27'),
    ('english-input', {}, ['KRV', 'KJV+'], 'John 11:35'),
    ('keyword', {}, ['KRV'], '#사랑'),
    ('no-reference', {}, ['KRV'], '아무 글'),
    ('empty-order', {}, [], '요 3:16'),
]


def load_dbs():
    return {v: BibleDB(os.path.join(ROOT, 'bible_versions', f'{v}.SQLite3')) for v in VERSIONS}


def make_library(dbs, overrides, order):
    """A Library over exactly ``dbs`` — no disk scan, no settings/alias files."""
    lib = object.__new__(Library)
    lib.dbs = dbs
    lib.settings = dict(Library.DEFAULT_SETTINGS, **overrides)
    lib.settings['output_order'] = list(order)
    lib._alias_key = None
    lib.load_alias_overrides = lambda: {}
    return lib


def tables():
    return {
        'korean_book_map': {k: list(v) for k, v in C.KOREAN_BOOK_MAP.items()},
        'english_book_map': C.ENGLISH_BOOK_MAP,
        'qwerty_to_hangul': C.QWERTY_TO_HANGUL,
        'choseong': C.CHOSEONG, 'jungseong': C.JUNGSEONG, 'jongseong': C.JONGSEONG,
        'complex_jungseong': [[a, b, c] for (a, b), c in C.COMPLEX_JUNGSEONG.items()],
        'complex_jongseong': [[a, b, c] for (a, b), c in C.COMPLEX_JONGSEONG.items()],
        'english_versions': sorted(C.ENGLISH_VERSIONS),
        'default_settings': Library.DEFAULT_SETTINGS,
    }


def build():
    dbs = load_dbs()
    lib = make_library(dbs, {}, [])
    aliases = lib.book_aliases()
    engine = [{'in': t,
               'out': [list(r[:4]) + [list(r[4])] for r in Engine.parse_reference(t, aliases)]}
              for t in REFERENCES]
    engine_plain = [{'in': t, 'out': [list(r[:4]) + [list(r[4])] for r in Engine.parse_reference(t)]}
                    for t in REFERENCES]
    formats = []
    for label, over, order, text in FORMATS:
        out = make_library(dbs, over, order).build_output(text)
        formats.append({'label': label, 'settings': over, 'order': order, 'in': text, 'out': out})
    golden = lambda name: os.path.join(GOLDEN_DIR, name)
    return {
        TABLES: tables(),
        golden('engine.json'): {'aliases': dict(sorted(aliases.items())), 'with_aliases': engine,
                                'without_aliases': engine_plain},
        golden('text.json'): {'clean_text': [{'in': t, 'out': clean_text(t)} for t in TEXTS],
                              'qwerty': [{'in': t, 'out': convert_qwerty_to_hangul(t)} for t in QWERTY]},
        golden('format.json'): {'cases': formats},
    }


def dump(obj):
    return json.dumps(obj, ensure_ascii=False, indent=1) + '\n'


def main(check=False):
    stale = []
    files = build()
    for path, obj in files.items():
        name = os.path.relpath(path, ROOT).replace(os.sep, '/')
        text = dump(obj)
        if check:
            try:
                with open(path, encoding='utf-8') as f:
                    if f.read() != text:
                        stale.append(name)
            except FileNotFoundError:
                stale.append(name)
        else:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w', encoding='utf-8', newline='\n') as f:
                f.write(text)
    if stale:
        print('stale golden files (run: python -X utf8 tests/make_golden.py):', ', '.join(stale))
        return 1
    print('golden ' + ('up to date' if check else 'written') + ': '
          + ', '.join(os.path.relpath(p, ROOT).replace(os.sep, '/') for p in files))
    return 0


if __name__ == '__main__':
    sys.exit(main('--check' in sys.argv[1:]))
