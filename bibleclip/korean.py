"""한국어 검색 정규화 (v1.0.5 스마트 검색) — 순수 파이썬, 외부 의존 0.

검색어와 색인을 *동일한* 규칙으로 정규화한다(대칭). 조사를 규칙 기반으로 떼어 어근
토큰을 만든다. 형태소 분석기(Kiwi)나 외장 사전이 전혀 필요 없고 ``dict``/``set``/``str``
연산만 쓰므로, PyInstaller 프로즌(.exe) 환경에서도 네이티브 크래시가 구조적으로 불가능
하다 (v1.0.4 Kiwi 힙손상 크래시 교훈 반영).

설계 메모:
- **어미(동사/형용사 활용)는 떼지 않는다** — "창조하시니라"는 통째로 색인되고, "창조"
  같은 어간 질의는 조회 단계의 '부분일치 폴백'(Phase 2)이 회수한다. 고어체 어미 규칙은
  오분리 위험이 커 의도적으로 배제.
- 정규화가 색인·질의에 *동일하게* 적용되므로, 설령 일부 단어가 과하게 잘려도(예: 포도→포)
  **recall 은 깨지지 않는다**(양쪽이 같은 키가 됨). 정밀도 손실은 AND 교집합/스코어링이 흡수.
"""
import re

# 닫힌 조사 집합. 긴 접미사가 먼저 매칭되도록 길이 내림차순으로 미리 정렬해 둔다.
# (어미는 포함하지 않는다 — 위 설계 메모 참조.)
_PARTICLES = sorted([
    '으로서', '으로써', '에게서', '에서', '에게', '으로', '이라',
    '은', '는', '이', '가', '을', '를', '의', '에', '와', '과', '도', '로', '만',
], key=len, reverse=True)

# 검색 분별력이 없는 기능어. 보수적으로 유지 — 실단어가 될 수 있는 글자(수·때·등·한·
# 두 …)는 일부러 제외해 recall 을 보호한다. 실단어 1글자(빛·땅·물·해)는 애초에 여기 없다.
_STOPWORDS = frozenset([
    '그', '또', '또한', '및', '곧', '그리고', '그러나', '하지만', '그것', '이것', '저것',
])

_TAG_RE = re.compile(r'<[^>]+>')
# 토큰 양끝에서 떼어낼 구두점/기호 (가운데 문자는 보존)
_EDGE_PUNCT = ' \t\r\n.,;:!?\'"()[]{}「」『』《》〈〉·…“”‘’~—'


def strip_particle(token):
    """토큰 끝의 조사를 1회 greedy(긴 것 우선) 제거. 어근이 비지 않도록 가드."""
    for p in _PARTICLES:
        if token.endswith(p) and len(token) > len(p):
            return token[:-len(p)]
    return token


def tokenize(text):
    """본문/검색어 → 정규화된 원형 토큰 리스트.

    색인 빌드와 검색어 처리가 **공유하는 단일 진입점**(대칭 보장). 순서:
    태그 제거 → 띄어쓰기 분리 → 양끝 구두점 제거 → 조사 제거 → 빈 토큰·불용어 제외.
    """
    if not text:
        return []
    text = _TAG_RE.sub(' ', text)
    out = []
    for raw in text.split():
        tok = raw.strip(_EDGE_PUNCT)
        if not tok:
            continue
        tok = strip_particle(tok)
        if not tok or tok in _STOPWORDS:
            continue
        out.append(tok)
    return out
