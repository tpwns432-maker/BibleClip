"""1년 1독 통독 계획 테스트 (bibleclip/server/readingplan.py).

    python -X utf8 tests/test_readingplan.py
"""
import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bibleclip.core.engine import Engine  # noqa: E402
from bibleclip.core.library import Library  # noqa: E402
from bibleclip.server import readingplan as rp  # noqa: E402

lib = Library()
BOOKS = [(b['num'], Engine._canon(b['num'])[1], len(lib.get_chapters('KRV', b['num']))) for b in lib.books('KRV')]
CH = rp.chapter_list(BOOKS)

# 66권 1189장을 365일에 빠짐없이 · 겹치지 않게, 하루 3~4장.
assert len(BOOKS) == 66 and len(CH) == 1189
days = [rp.day_chapters(CH, i) for i in range(rp.DAYS)]
assert [c for d in days for c in d] == CH
assert {len(d) for d in days} == {3, 4}

# 시작일(2026-11-25) = 1일째, 365일째 = 요한계시록 끝, 그다음 날 = 2독째 1일.
assert rp.START == date(2026, 11, 25)
assert rp.reading_for(CH, date(2026, 11, 24)) is None
r = rp.reading_for(CH, date(2026, 11, 25))
assert (r['day'], r['round'], r['label'], r['first']) == (1, 1, '창 1–3장', (10, 1)), r
assert rp.reading_for(CH, date(2026, 12, 10))['label'] == '창 50장 · 출 1–2장'     # 책이 바뀌는 날
last = rp.reading_for(CH, date(2027, 11, 24))
assert last['day'] == 365 and last['label'].startswith('계 ') and last['chapters'][-1][2] == 22
again = rp.reading_for(CH, date(2027, 11, 25))
assert (again['day'], again['round'], again['label']) == (1, 2, '창 1–3장')

# 한 장짜리 책(오바댜 등)과 이름 묶기.
assert rp.label([(380, '옵', 1)]) == '옵 1장'
assert rp.label([(10, '창', 1), (10, '창', 2), (20, '출', 1)]) == '창 1–2장 · 출 1장'

# 한국 시간 날짜: UTC 로 전날 밤 23시 = 한국은 다음 날 아침 8시.
utc = datetime(2026, 11, 24, 23, 0, tzinfo=rp.timezone.utc)
assert rp.today_kst(utc) == date(2026, 11, 25)

print('test_readingplan: ok')
sys.stdout.flush()
os._exit(0)
