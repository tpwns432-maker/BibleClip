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


def _morph_html(morph):
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
    return ('<div class="morph"><div class="morph-h">형태소 분석</div>'
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


def _dict_page_html(code, entry, theme='light'):
    t = _DICT_THEMES.get(theme, _DICT_THEMES['light'])
    if not entry:
        head = body = ''
        reading = ''
        morph = ''
    else:
        head = entry.get('headword', '')
        reading = entry.get('reading', '')
        body = entry.get('html', '') or '사전 항목 없음'
        morph = _morph_html(entry.get('morph'))
    head_block = ''
    if head:
        head_block = (f'<div class="head"><span class="heb">{head}</span>'
                      f'<span class="rom">{reading}</span></div>')
    font_ui = ('"Pretendard","Apple SD Gothic Neo","Malgun Gothic",'
               '"Segoe UI","Noto Sans KR",system-ui,sans-serif')
    font_heb = '"SBL Hebrew","Times New Roman","Noto Serif Hebrew",serif'
    return f"""<!DOCTYPE html><html lang="ko" data-theme="{theme}"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>사전 · {code}</title><style>
*{{box-sizing:border-box;margin:0;padding:0}}
body{{font-family:{font_ui};background:{t['bg']};color:{t['text']};
 padding:20px;line-height:1.8;-webkit-font-smoothing:antialiased}}
.chip{{display:inline-block;font-size:11px;font-weight:700;color:{t['accent']};
 background:{t['chipbg']};border-radius:8px;padding:3px 10px;margin-bottom:12px}}
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
<span class="chip">{code}</span>{head_block}{morph}<div class="body">{body}</div>
</body></html>"""
