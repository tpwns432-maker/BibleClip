"""Korean morphological tokenization for verse search (Phase 2, 9차 패치).

Wraps kiwipiepy (Kiwi) to split a search query into *content* morphemes —
명사/어근/수사 등 — so 조사·어미 변화가 매칭을 막지 않는다. The Kiwi model is
loaded lazily and at most once; if kiwipiepy isn't installed or init fails,
``tokenize_keywords()`` returns ``[]`` and callers fall back to the existing
trigram fuzzy search. Every entry point is fail-soft and never raises.
"""

# Content POS tags worth keying a search on: 일반/고유명사, 수사, 어근,
# 외국어/한자, 동사/형용사 어간. Function morphemes (조사 J*, 어미 E*,
# 접사 X[SP]*, 부호 S[FPE] 등) are dropped — that is the whole point.
_CONTENT_TAGS = frozenset({
    'NNG', 'NNP', 'NR', 'XR', 'SL', 'SH', 'VV', 'VA',
})

import threading

_kiwi = None
_kiwi_tried = False
_kiwi_lock = threading.Lock()


def _get_kiwi():
    """The shared Kiwi instance, or None if unavailable. Loaded once, lazily —
    importing/constructing Kiwi is heavy, so it never happens at module import,
    only on the first real use.

    ⚠️ 스레드 안전성: 프로즌 빌드(pywebview/pythonnet)에서 검색은 .NET/WebView2
    브리지 스레드에서 호출된다. Kiwi 를 그 외래 스레드에서 '처음 생성'하면 내부
    워커 스레드풀을 띄우다 네이티브 크래시(즉시 강제 종료)가 났다 — 단일어/문장
    검색은 exact 매치라 Kiwi 를 안 부르고, 다중 키워드만 이 경로를 처음 타며 죽음.
    방어 2겹:
      (1) ``num_workers=1`` 로 내부 스레드풀을 아예 만들지 않는다(인라인 단일 스레드).
      (2) 락으로 생성을 1회로 직렬화 → 시작 시 ``warmup()`` 데몬이 먼저 잡으면
          브리지 스레드의 검색은 락에서 대기, 생성은 안전한 스레드에서 끝난다.
    한 줄 검색어 토큰화에 병렬성은 무의미하므로 단일 스레드가 성능상도 적절."""
    global _kiwi, _kiwi_tried
    if _kiwi_tried:
        return _kiwi
    with _kiwi_lock:
        if _kiwi_tried:                 # double-checked: another thread won the race
            return _kiwi
        try:
            from kiwipiepy import Kiwi
            _kiwi = Kiwi(num_workers=1)
        except Exception:
            _kiwi = None
        _kiwi_tried = True
    return _kiwi


def warmup():
    """Construct the Kiwi singleton ahead of first search. Call from a daemon
    thread at app startup so the heavy/native init happens on a normal Python
    thread — never lazily on the pywebview bridge thread (which crashed)."""
    _get_kiwi()


def available():
    """True when the Kiwi morphological analyzer is usable on this install."""
    return _get_kiwi() is not None


def tokenize_keywords(text, min_len=2):
    """Content morphemes (deduped, original order) from a Korean query, or ``[]``
    when Kiwi is unavailable or nothing meaningful was extracted.

    Tokens shorter than ``min_len`` are dropped to avoid over-broad single-
    character matches — those are already covered by the caller's exact
    (spacing-ignored) substring pass.
    """
    text = (text or '').strip()
    if not text:
        return []
    kiwi = _get_kiwi()
    if kiwi is None:
        return []
    try:
        toks = kiwi.tokenize(text)
    except Exception:
        return []
    out, seen = [], set()
    for t in toks:
        form = t.form
        if t.tag in _CONTENT_TAGS and len(form) >= min_len and form not in seen:
            seen.add(form)
            out.append(form)
    return out
