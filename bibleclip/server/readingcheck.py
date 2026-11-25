"""성경읽기 체크 — 그날 읽은 범위에 대한 짧은 생각(커뮤니티 '성경읽기 체크' 글)을 쓰면 그날 읽음.

따로 체크 장부를 두지 않는다. 글이 곧 기록이다(지우면 체크도 빠지고, 지난 날도 나중에 쓰면 체크).
1년 1독 계획(readingplan) + 커뮤니티 글(community.reading_posts)로 오늘 · 연속 일수 · 날짜별 기록을 만든다.
"""
from datetime import timedelta

from bibleclip.server import readingplan as rp


class ReadingCheck:
    def __init__(self, community, names, chapters, start=rp.START, today=None):
        """names(): {아이디: {'name': ...}}. chapters: readingplan.chapter_list(...). today(): 한국 날짜."""
        self.community = community
        self.names = names
        self.chapters = chapters
        self.start = start
        self.today = today or (lambda: rp.today_kst())

    def info(self, day):
        """그날의 읽기 {'date', 'day', 'round', 'label', 'book', 'chapter'} — 시작 전이면 None."""
        r = rp.reading_for(self.chapters, day, self.start)
        if not r:
            return None
        return {'date': day.isoformat(), 'day': r['day'], 'round': r['round'], 'label': r['label'],
                'book': r['first'][0], 'chapter': r['first'][1]}

    def info_iso(self, iso):
        from datetime import date
        try:
            return self.info(date.fromisoformat(str(iso)))
        except ValueError:
            return None

    def done_on(self, day):
        """{아이디: 글 번호} — 그날 체크한 사람."""
        iso = day.isoformat()
        return self.community.reading_posts(iso, iso).get(iso, {})

    def _streak(self, uid, done, today):
        """오늘까지 이어진 연속 일수(오늘 아직이면 어제까지)."""
        d = today if uid in done.get(today.isoformat(), {}) else today - timedelta(days=1)
        n = 0
        while d >= self.start and uid in done.get(d.isoformat(), {}):
            n += 1
            d -= timedelta(days=1)
        return n

    def status(self, uid):
        today = self.today()
        names = self.names()
        users = sorted(names, key=lambda u: (u != uid, u))      # 나 먼저
        if today < self.start:
            return {'started': False, 'start': self.start.isoformat(), 'today': None,
                    'users': [{'id': u, 'name': names[u].get('name', u), 'me': u == uid} for u in users],
                    'history': []}
        done = self.community.reading_posts(self.start.isoformat(), today.isoformat())
        elapsed = (today - self.start).days + 1
        history = []
        for i in range(elapsed):
            d = today - timedelta(days=i)
            history.append(dict(self.info(d), done=done.get(d.isoformat(), {})))
        out_users = []
        for u in users:
            out_users.append({'id': u, 'name': names[u].get('name', u), 'me': u == uid,
                              'today': done.get(today.isoformat(), {}).get(u),
                              'streak': self._streak(u, done, today),
                              'done': sum(1 for d in done.values() if u in d), 'elapsed': elapsed})
        return {'started': True, 'start': self.start.isoformat(),
                'today': dict(self.info(today), done=done.get(today.isoformat(), {})),
                'users': out_users, 'history': history}
