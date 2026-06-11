"""Lexicon-markup → HTML helpers for the web bridge.

Dictionary entries are stored as a small pseudo-HTML markup (the same dialect
rendered into tk tags by data.original_lang.render_dict_html). For the web we
only need to translate the two non-standard pieces — '^' separators and the
custom <num> tag; <b>/<br>/<sup>/<font color> render natively in a browser.

Extracted from webui.api so the route mixins (routes/bible.py) can share these
without importing api.py (which would be a circular import — api.py composes the
mixins). api.py re-exports the public names for backwards compatibility.
"""
import re

from bibleclip import i18n

_NUM_RE = re.compile(r'<\s*num\s*>(.*?)<\s*/\s*num\s*>', re.S | re.I)
# A lexicon entry starts: HEADWORD^<font ...>reading</font><br>... The first
# font holds the romanization/Korean reading; the rest is the gloss + body.
_FIRST_FONT_RE = re.compile(r'^\s*<font[^>]*>(.*?)</font>', re.S | re.I)
_TAGS_RE = re.compile(r'<[^>]+>')
_LEAD_BR_RE = re.compile(r'^(?:\s*<br\s*/?>\s*)+', re.I)


def markup_to_html(markup):
    if not markup:
        return ''
    html = markup.replace('^', '  ')
    html = _NUM_RE.sub(r'<span class="lex-num" data-code="\1">\1</span>', html)
    return html


def parse_entry(markup):
    """Split a raw lexicon entry into headword / reading / body-HTML.

    Layout: ``HEADWORD^<font>reading</font><br><font>gloss</font>…body``.
    Falls back gracefully (empty headword/reading) for entries that don't
    follow it."""
    if not markup:
        return {'headword': '', 'reading': '', 'html': ''}
    headword, rest = '', markup
    if '^' in markup:
        headword, rest = markup.split('^', 1)
        headword = headword.strip()
    reading = ''
    m = _FIRST_FONT_RE.match(rest)
    if m:
        reading = _TAGS_RE.sub('', m.group(1)).strip()
        rest = _LEAD_BR_RE.sub('', rest[m.end():])
    return {'headword': headword, 'reading': reading, 'html': markup_to_html(rest)}


def _morph_html(morph, lang='ko'):
    """Render a morphology list (Library.morphology) to the 형태소 분석 block."""
    if not morph:
        return ''
    rows = []
    for w in morph:
        seg = f"<b>{w['lemma']}</b>"
        if w.get('translit'):
            seg += f" {w['translit']}"
        if w.get('pos'):
            seg += f" · {w['pos']}"
        if w.get('gloss') and w['gloss'] != '_':
            seg += f" · {w['gloss']}"
        rows.append(seg)
    return (f'<div class="morph"><div class="morph-h">{i18n.t("dict.morphHeading", lang)}</div>'
            + '<br>'.join(rows) + '</div>')


# Self-contained styles for the right-click dict window. It's created with
# inline HTML (no base URL), so it can't link the bundled CSS/fonts — the font
# stacks fall back to system Korean/Hebrew fonts, which is fine for a popup.
_DICT_THEMES = {
    'light': dict(bg='#FAF9FC', card='#FFFFFF', border='#EFEBF6', text='#241D33',
                  muted='#6A6086', dim='#A99FC0', accent='#6D4DFF',
                  chipbg='#F3EFFE', heb='#1A1330'),
    'dark': dict(bg='#0F0B1A', card='#171127', border='#2A2140', text='#ECE9F5',
                 muted='#A99FC6', dim='#7D7399', accent='#9A86FF',
                 chipbg='#241A3F', heb='#ECE9F5'),
}


# 사전 팝업 창의 언어 선택 드롭다운 라벨(자기 언어 표기 = 엔도님).
_LANG_LABEL = {'ko': '한국어', 'en': 'English'}


def _has_entry(entry):
    """True if a lexicon lookup has real dictionary content (not just verse
    morphology with an empty body) — used to decide which languages to offer."""
    return bool(entry and (entry.get('headword') or entry.get('html')))


def _dict_block_html(entry, lang):
    """The head(원어/읽기) + body(뜻풀이) for ONE language entry. Chip/morph are
    shared across languages, so they live outside this block."""
    if not entry:
        return f'<div class="body">{i18n.t("dict.noEntry", lang)}</div>'
    head = entry.get('headword', '')
    reading = entry.get('reading', '')
    body = entry.get('html', '') or i18n.t('dict.noEntry', lang)
    head_block = ''
    if head:
        head_block = (f'<div class="head"><span class="heb">{head}</span>'
                      f'<span class="rom">{reading}</span></div>')
    return f'{head_block}<div class="body">{body}</div>'


def _dict_page_html(code, entries, theme='light', ui='ko', initial='ko'):
    """Self-contained dict-popup page. ``entries`` = {'ko': entry|None,
    'en': entry|None}. When BOTH languages have a real entry, a 한국어/English
    <select> toggles them in-place (pure JS, no bridge); with one (or none) it
    shows that single entry. ``ui`` = program language (chrome/morph labels +
    the default). ``initial`` = which language to show first."""
    t = _DICT_THEMES.get(theme, _DICT_THEMES['light'])
    entries = entries or {}
    avail = [lg for lg in ('ko', 'en') if _has_entry(entries.get(lg))]
    if initial not in avail:
        initial = initial if initial in ('ko', 'en') else ui
        if avail and initial not in avail:
            initial = avail[0]
    # verse 형태소(morph)는 언어 무관 데이터 — 한 번만(프로그램 언어 라벨로) 렌더.
    morph = ''
    for lg in ('ko', 'en'):
        e = entries.get(lg)
        if e and e.get('morph'):
            morph = _morph_html(e.get('morph'), ui)
            break
    # 언어 선택 리스트는 항상 노출(없는 언어는 noEntry 표시) — 사용자가 어느 표면에서든
    # 한·영을 직접 고를 수 있게. 두 언어 블록을 모두 임베드하고 select 로 show/hide.
    blocks = ''.join(
        f'<div class="lang-block" data-lang="{lg}"{"" if lg == initial else " hidden"}>'
        f'{_dict_block_html(entries.get(lg), lg)}</div>'
        for lg in ('ko', 'en'))
    opts = ''.join(
        f'<option value="{lg}"{" selected" if lg == initial else ""}>{_LANG_LABEL[lg]}</option>'
        for lg in ('ko', 'en'))
    selector = f'<select class="langsel" id="langsel" aria-label="lang">{opts}</select>'
    script = ('<script>document.getElementById("langsel").addEventListener("change",'
              'function(e){var v=e.target.value;document.querySelectorAll(".lang-block")'
              '.forEach(function(b){b.hidden=(b.dataset.lang!==v);});});</script>')
    font_ui = ('"Pretendard","Apple SD Gothic Neo","Malgun Gothic",'
               '"Segoe UI","Noto Sans KR",system-ui,sans-serif')
    font_heb = '"SBL Hebrew","Times New Roman","Noto Serif Hebrew",serif'
    return f"""<!DOCTYPE html><html lang="{ui}" data-theme="{theme}"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{i18n.t('dict.popupTitle', ui, code=code)}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:{font_ui};background:{t['bg']};color:{t['text']};
 padding:20px;line-height:1.8;-webkit-font-smoothing:antialiased}}
.topbar{{display:flex;align-items:center;gap:10px;margin-bottom:12px}}
.chip{{display:inline-block;font-size:11px;font-weight:700;color:{t['accent']};
 background:{t['chipbg']};border-radius:8px;padding:3px 10px}}
.langsel{{margin-left:auto;font-family:inherit;font-size:12px;color:{t['text']};
 background:{t['chipbg']};border:1px solid {t['border']};border-radius:8px;padding:3px 8px}}
.head{{display:flex;align-items:baseline;gap:12px;flex-wrap:wrap;margin-bottom:14px}}
.head .heb{{font-family:{font_heb};font-size:48px;line-height:1.15;color:{t['heb']}}}
.head .rom{{color:{t['accent']};font-weight:700;font-size:15px}}
.morph{{border:1px solid {t['border']};border-radius:10px;padding:10px 12px;
 margin-bottom:14px;font-size:13px;color:{t['muted']}}}
.morph-h{{color:{t['accent']};font-weight:700;font-size:11px;margin-bottom:4px}}
.body{{font-size:13px;color:{t['muted']}}}
.body b{{color:{t['text']}}}
.lex-num{{color:{t['accent']};text-decoration:underline}}
</style></head><body>
<div class="topbar"><span class="chip">{code}</span>{selector}</div>
{morph}{blocks}{script}
</body></html>"""
