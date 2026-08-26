"""성경 유의어 사전 — 고어(개역한글) ↔ 현대어 검색어 확장.

**왜 필요한가**: BibleClip 은 다역본 앱이라 다른 성경 앱에 없는 검색 실패 모드가 있다.
사용자가 새번역으로 읽다가 '이집트'를 기억하고 개역한글에서 검색하면, 개역한글 본문은
'애굽'이라고 적혀 있어 **결과가 0건**이다(새번역에서는 690건). '자비/긍휼', '낙타/약대',
'기적/이적', '파라오/바로', '전차/병거' 모두 같은 문제다. 역본을 나란히 놓고 읽는 것이
이 앱의 핵심 기능이므로, 현대어로 기억하고 고어체에서 검색하는 상황이 구조적으로 반복된다.

**데이터 출처**: 앱이 이미 가진 한국어 역본들 자체다. 같은 절 주소를 서로 다르게 번역한
**병렬 코퍼스**이므로, 개역한글이 '긍휼'이라 쓴 자리에서 다른 역본들이 '자비'라고 쓴다면
그 둘을 유의어로 볼 수 있다. 절 단위 치환 통계(Dice) + 지지 역본 수 + 장 분산도 + 양방향
상대 임계로 걸러 만들었다. 추출 스크립트는 `_local/synonym_experiment/`(비배포).

**형식**: `{"_meta": {...}, "map": {단어: [[대체어, 신뢰도], ...]}}` — 고어↔현대 **양방향
대칭** 맵. 검색은 한 번에 한 역본을 대상으로 하므로 방향이 고정되지 않는다(개역한글에서
'이집트'를 찾을 수도, 새번역에서 '애굽'을 찾을 수도 있다).

**신뢰도(0~1, 추출 Dice)를 함께 싣는 이유**: 확장어를 전부 같은 무게로 다루면 검색 순위가
망가진다. '이집트' 검색에서 애굽(0.91)과 인도하여(0.22)를 동일 가중치로 두자, **오탐이
더 희귀해 IDF 가 높은 탓에 정답보다 위로 올라왔다**(실측). 호출부(BM25)가 이 값에 비례해
가중치를 매기면 순서가 바로잡힌다.

**위치**: `web/data/bible_synonyms.json`. 빌드 3곳(BibleClipWeb.spec / build_web.ps1 /
build.yml)이 모두 `--add-data web` 을 쓰므로 web/ 안에 두면 **빌드 스크립트를 건드리지 않고**
자동 동봉된다 (v1.1.7 읽기 글꼴을 web/fonts/reading/ 에 둔 것과 같은 요령).

**fail-soft**: 파일이 없거나 깨져도 예외를 밖으로 내지 않는다. 사전이 없으면 확장이 0개일
뿐이고 검색은 기존과 100% 동일하게 동작한다. 순수 dict/str 연산이라 프로즌(.exe)에서 네이티브
크래시가 구조적으로 불가능하다(korean.py 와 같은 설계 원칙).
"""
import json
import os

from bibleclip.config import get_resource_dir

REL_PATH = os.path.join('web', 'data', 'bible_synonyms.json')

# 한 검색어 토큰이 끌어올 수 있는 확장 최대 개수. 사전 자체도 표제어당 4개로 자르지만,
# 검색 품질 안전판으로 호출 측에서 한 번 더 조인다(오탐이 누적되면 결과가 흐려진다).
MAX_EXPAND = 3


class SynonymDict:
    """지연 로드 유의어 사전. 실패해도 '빈 사전'으로 조용히 동작한다."""

    def __init__(self, path=None):
        self._path = path or os.path.join(get_resource_dir(), REL_PATH)
        self._map = None      # None = 아직 안 읽음, {} = 없거나 실패
        self._meta = {}

    def _ensure(self):
        if self._map is not None:
            return
        self._map, self._meta = {}, {}
        try:
            with open(self._path, encoding='utf-8') as f:
                data = json.load(f)
            m = data.get('map')
            if isinstance(m, dict):
                # [[단어, 점수], ...] 만 취한다. 점수가 없는 옛 형식([단어, ...])도
                # 받아들여 신뢰도 1.0 으로 간주한다(형식 호환).
                out = {}
                for k, v in m.items():
                    if not isinstance(v, (list, tuple)):
                        continue
                    alts = []
                    for e in v:
                        if isinstance(e, (list, tuple)) and len(e) >= 2:
                            try:
                                alts.append((str(e[0]), float(e[1])))
                            except (TypeError, ValueError):
                                continue
                        elif isinstance(e, str):
                            alts.append((e, 1.0))
                    if alts:
                        out[k] = tuple(alts)
                self._map = out
                self._meta = data.get('_meta') or {}
        except Exception:
            pass   # 파일 없음/깨짐 → 빈 사전 (검색은 기존 동작 유지)

    @property
    def available(self):
        self._ensure()
        return bool(self._map)

    @property
    def size(self):
        self._ensure()
        return len(self._map)

    @property
    def meta(self):
        self._ensure()
        return dict(self._meta)

    def expand(self, token, limit=MAX_EXPAND):
        """토큰의 [(대체어, 신뢰도), ...]. 사전에 없으면 빈 튜플. 신뢰도 내림차순."""
        self._ensure()
        if not token:
            return ()
        return tuple(self._map.get(token, ())[:limit])

    def words(self, token, limit=MAX_EXPAND):
        """대체어만 (하이라이트·표시용 — 점수가 필요 없는 호출부)."""
        return tuple(w for w, _ in self.expand(token, limit))

    def expand_all(self, tokens, limit=MAX_EXPAND):
        """[토큰] → {토큰: (대체어...)}. 대체어가 있는 토큰만 담는다.

        검색 결과 하이라이트용 — 프론트가 '이집트'로 검색해도 본문의 '애굽'을 강조해야
        사용자가 왜 이 절이 나왔는지 알 수 있다."""
        out = {}
        for t in tokens or ():
            alts = self.words(t, limit)
            if alts:
                out[t] = alts
        return out


_shared = None


def shared():
    """프로세스 공용 인스턴스 (사전은 읽기 전용이라 공유해도 안전)."""
    global _shared
    if _shared is None:
        _shared = SynonymDict()
    return _shared
