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

_kiwi = None
_kiwi_tried = False


def _get_kiwi():
    """The shared Kiwi instance, or None if unavailable. Loaded once, lazily —
    importing/constructing Kiwi is heavy, so it never happens at module import,
    only on the first real tokenize call (i.e. the first fuzzy search)."""
    global _kiwi, _kiwi_tried
    if _kiwi_tried:
        return _kiwi
    _kiwi_tried = True
    try:
        from kiwipiepy import Kiwi
        _kiwi = Kiwi()
    except Exception:
        _kiwi = None
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
