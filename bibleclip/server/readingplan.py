"""1년 1독 통독 계획 — 날짜 → 그날 읽을 장들 (docs/TELEGRAM_PLAN.md).

성경 순서로 66권 1189장을 365일에 고르게 나눈다(하루 3~4장). 두 사람이 같은 시작일 · 같은 계획으로
읽는다. 365일이 지나면 처음부터 다시(2독째). 모두 순수 함수라 tests/test_readingplan.py 가 바로 시험한다.
"""
from datetime import date, datetime, timedelta, timezone

DAYS = 365
KST = timezone(timedelta(hours=9), 'KST')   # 한국은 일광 절약 시간이 없어 고정 +9 로 충분하다
START = date(2026, 11, 25)                  # 1일째(사용자 결정 2026-11-24)


def chapter_list(books):
    """books: [(책 번호, 짧은 이름, 장 수)] 성경 순서 → [(책 번호, 짧은 이름, 장)]."""
    return [(num, short, ch) for num, short, n in books for ch in range(1, n + 1)]


def day_chapters(chapters, index):
    """계획의 index(0부터)번째 날에 읽을 장들. 장 수를 고르게 나눈다."""
    n = len(chapters)
    i = index % DAYS
    return chapters[round(i * n / DAYS):round((i + 1) * n / DAYS)]


def label(chs):
    """[(책, 이름, 장)...] → '창 1–4장' / '창 50장 · 출 1–2장'."""
    parts, i = [], 0
    while i < len(chs):
        num, short, first = chs[i]
        j = i
        while j + 1 < len(chs) and chs[j + 1][0] == num and chs[j + 1][2] == chs[j][2] + 1:
            j += 1
        last = chs[j][2]
        parts.append(f'{short} {first}장' if first == last else f'{short} {first}–{last}장')
        i = j + 1
    return ' · '.join(parts)


def reading_for(chapters, day, start=START):
    """그날(date)의 읽기. 시작 전이면 None.
    {'day': 몇째 날(1~365), 'round': 몇 독째, 'chapters': [...], 'label': str, 'first': (책, 장)}"""
    d = (day - start).days
    if d < 0:
        return None
    chs = day_chapters(chapters, d)
    return {'day': d % DAYS + 1, 'round': d // DAYS + 1, 'chapters': chs,
            'label': label(chs), 'first': (chs[0][0], chs[0][2]) if chs else None}


def today_kst(now=None):
    return (now or datetime.now(KST)).astimezone(KST).date()
