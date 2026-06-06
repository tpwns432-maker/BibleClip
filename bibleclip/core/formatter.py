"""Formatter: build output text for one bible version from settings."""
import re


class Formatter:
    """Generates formatted bible output text based on user settings."""

    def __init__(self, settings, dbs=None):
        self.s = settings  # dict of all settings
        self.dbs = dbs or {}

    def format_version_output(self, db, book_num, chapter, verses, all_verse_data):
        """Format output for a single bible version.

        Args:
            db: BibleDB instance
            book_num: book number
            chapter: chapter number
            verses: list of verse numbers
            all_verse_data: list of (verse_num, text) tuples
        Returns:
            formatted string
        """
        s = self.s

        # --- Determine book display name ---
        # 각 역본은 *자기 DB*의 책이름을 쓴다. KRV+ESV 동시 출력이면 [룻기 …] / [Ruth …]
        # 처럼 역본별 모국 표기가 나온다(한 언어를 전 역본에 강제하지 않음). 설정의
        # short/long 만 적용; ko/en 구분은 역본 자체 언어가 결정하므로 길이에만 관여한다.
        db_short, db_long = db.books.get(book_num, ('?', '?'))
        # 'long'/'long_ko'/'long_en' → 정식(long), 그 외(short*) → 약칭(short).
        # 구 설정값(long_ko/short_en 등)도 prefix 로 호환 흡수.
        use_long = str(s.get('book_name', 'short')).startswith('long')
        book_display = db_long if use_long else db_short

        # --- Build reference string ---
        range_sym = s.get('range_symbol', '-')
        verse_list_str = self._format_verse_list(verses, range_sym) if verses else ''

        if s['chapter_verse_format'] == 'korean':
            if verse_list_str:
                ref_str = f"{book_display} {chapter}장 {verse_list_str}절"
            else:
                ref_str = f"{book_display} {chapter}장"
        else:
            if verse_list_str:
                ref_str = f"{book_display} {chapter}:{verse_list_str}"
            else:
                ref_str = f"{book_display} {chapter}"

        # --- Build version header ---
        version_header = ""
        if s.get('show_version_header', True):
            version_header = f"[{db.name}]"

        # --- Build body ---
        body = self._build_body(all_verse_data, chapter)

        # --- FEAT-02: 유저 매크로 템플릿 (켜져 있으면 표준 조립 규칙을 대체) ---
        # 지원 태그: {book_full} {book_short} {chap} {verse} {content} {version}.
        # 사용자가 괄호·위치·구분자 대신 템플릿 문자열로 서식을 100% 제어한다.
        # 인식 못한 {x} 는 그대로 남겨 오타가 눈에 띄게 한다. ({content2}/{version2}
        # 는 단일 역본 출력에선 빈 문자열 — 병렬은 format_parallel 가 처리.)
        tmpl = s.get('custom_format_template') or ''
        if s.get('custom_format_enabled') and tmpl.strip():
            return self._apply_template(tmpl, db_long, db_short, chapter,
                                        verse_list_str, body, db.name)

        # --- Assemble with brackets/position ---
        hide_ref = s.get('hide_reference', False)
        if hide_ref:
            # Text only, no reference
            if version_header:
                return f"{version_header}\n{body}"
            return body

        # Bracket style
        bracket = s.get('bracket_style', 'none')
        if bracket == '[]':
            ref_display = f"[{ref_str}]"
        elif bracket == '()':
            ref_display = f"({ref_str})"
        else:
            ref_display = ref_str

        # Separator between ref and body
        ref_sep = s.get('ref_body_separator', ' ')

        # Position
        position = s.get('ref_position', 'before')

        if position == 'before':
            if version_header:
                main_line = f"{version_header} {ref_display}{ref_sep}{body}"
            else:
                main_line = f"{ref_display}{ref_sep}{body}"
        else:  # after
            if version_header:
                main_line = f"{version_header} {body}{ref_sep}{ref_display}"
            else:
                main_line = f"{body}{ref_sep}{ref_display}"

        return main_line

    def _build_body(self, all_verse_data, chapter):
        """Join verse texts into the body string per output_mode (inline/newline).
        Shared by single-version output and the FEAT-05 parallel combiner."""
        s = self.s
        multiline = s['output_mode'] == 'newline'
        show_chapterverse = s.get('newline_show_cv', False)
        if multiline and len(all_verse_data) > 1:
            lines = []
            for v_num, v_text in all_verse_data:
                lines.append(f"{chapter}:{v_num} {v_text}" if show_chapterverse
                             else f"{v_num} {v_text}")
            return '\n'.join(lines)
        # inline — join texts; insert ' // ' across non-consecutive verse groups
        # (a comma split like "1-2,4-6") so the discontinuity stays legible.
        pieces = []
        prev_v = None
        for v_num, v_text in all_verse_data:
            if prev_v is not None:
                pieces.append(' // ' if v_num != prev_v + 1 else ' ')
            pieces.append(v_text)
            prev_v = v_num
        return ''.join(pieces)

    def format_parallel(self, book_num, chapter, col1, col2):
        """FEAT-05 병렬 복사 부스터: 두 역본을 ONE 블록으로 결합. 참조(책/장/절)는
        공유하고 {content}/{content2}=각 역본 본문, {version}/{version2}=역본명으로
        커스텀 템플릿을 1회 치환한다. col = (db, [(verse, text), ...]). 절 목록·책이름은
        첫 역본 기준."""
        s = self.s
        db1, vd1 = col1
        db2, vd2 = col2
        b1_short, b1_long = db1.books.get(book_num, ('?', '?'))
        verses1 = [v for v, _ in vd1]
        verse_list = self._format_verse_list(verses1, s.get('range_symbol', '-')) if verses1 else ''
        body1 = self._build_body(vd1, chapter)
        body2 = self._build_body(vd2, chapter)
        tmpl = s.get('custom_format_template') or ''
        return self._apply_template(tmpl, b1_long, b1_short, chapter, verse_list,
                                    body1, db1.name, content2=body2, version2=db2.name)

    @staticmethod
    def _apply_template(tmpl, book_full, book_short, chapter, verse_list, content,
                        version, content2='', version2=''):
        """Substitute {tag} macros in a user format template. Unknown tags are
        left verbatim so a typo is visible rather than silently dropped.
        content2/version2 carry the second translation for FEAT-05 parallel copy
        (empty in single-version output)."""
        repl = {
            'book_full': str(book_full), 'book_short': str(book_short),
            'chap': str(chapter), 'verse': str(verse_list),
            'content': str(content), 'version': str(version),
            'content2': str(content2), 'version2': str(version2),
        }
        return re.sub(r'\{(\w+)\}', lambda m: repl.get(m.group(1), m.group(0)), tmpl)

    @staticmethod
    def _format_verse_list(verses, range_sym='-'):
        if not verses:
            return ''
        ranges = []
        start = end = verses[0]
        for v in verses[1:]:
            if v == end + 1:
                end = v
            else:
                ranges.append(f"{start}{range_sym}{end}" if start != end else str(start))
                start = end = v
        ranges.append(f"{start}{range_sym}{end}" if start != end else str(start))
        return ','.join(ranges)

