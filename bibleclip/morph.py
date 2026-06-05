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

import sys
import threading

_kiwi = None
_kiwi_tried = False
_kiwi_lock = threading.Lock()


def _get_kiwi():
    """The shared Kiwi instance, or None if unavailable. Loaded once, lazily.

    ⚠️ 프로즌 빌드에서는 Kiwi 를 절대 생성하지 않는다(아래 sys.frozen 가드).
    kiwipiepy 의 C++ 네이티브 런타임이 PyInstaller 로 동봉된 pywebview
    (pythonnet/WebView2)와 같은 프로세스에서 공존하면 **네이티브 힙 손상**
    (STATUS_HEAP_CORRUPTION 0xC0000374)으로 앱이 즉시 강제 종료된다 — 시작 시
    워밍업하면 launch 크래시, 지연 생성하면 첫 다중 키워드 검색에서 크래시. Python
    try/except 로 잡을 수 없는 네이티브 크래시이므로, 배포(프로즌)에서는 형태소
    분석을 끄고 trigram 폴백만 사용한다. 형태소 검색은 소스/개발 실행에서만 동작.
    (kiwipiepy 도 빌드에서 제외 → 동봉 안 됨. 락은 소스 멀티스레드 생성 1회 보장.)"""
    global _kiwi, _kiwi_tried
    if _kiwi_tried:
        return _kiwi
    with _kiwi_lock:
        if _kiwi_tried:                 # double-checked: another thread won the race
            return _kiwi
        try:
            if getattr(sys, 'frozen', False):
                _kiwi = None            # 프로즌: pywebview 와 네이티브 충돌 → 비활성
            else:
                from kiwipiepy import Kiwi
                _kiwi = Kiwi(num_workers=1)   # 단일 스레드(검색어 1줄엔 병렬 무의미)
        except Exception:
            _kiwi = None
        _kiwi_tried = True
    return _kiwi


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
