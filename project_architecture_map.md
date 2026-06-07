# BibleClip — Project Architecture Map (지명도 파일)

> **목적**: Claude가 컨텍스트 리프레시 시 전체 파일을 `cat`/`find`로 전수 조사하는 토큰 낭비를 막기 위한 **마스터 인덱스**. 새 기능/버그 추적 지시를 받으면 **이 파일을 먼저 읽고** 타깃 파일·함수를 조준한 뒤 해당 파일만 연다.
>
> **유지보수 규칙 (STRICT)**: `api.py`/`routes/*`에 API 추가, `app.js`(프론트)에 이벤트 디스패처/컴포넌트 추가, 파일 구조·경로 변경 시 **반드시 이 파일을 동시에 갱신**한다. 커밋·작업완료 보고 전 "지명도 파일 업데이트 완료 여부"를 체크포인트로 확인한다.

- **현재 버전**: v1.1.2 (`bibleclip/_version.py` = `__version__`, ASCII-only single source of truth)
- **killswitch**: `recommend_version` = 1.1.1 (직전 버전 규칙)
- **★ v1.1.2 내용(일부 PC "런타임 에러" 진범 해결)**: 다운로드 zip의 **MOTW(Zone.Identifier=3)** 가 번들 `Python.Runtime.dll`에 묻어 .NET이 "인터넷 어셈블리" 로드를 거부(`Failed to resolve Python.Runtime.Loader.Initialize`)하던 문제. **로컬 복사본은 표식 없어 정상, 다운로드본만 실패** → startup_error.log로 확진(ZoneId=3 + ReferrerUrl=zip). 수정: `app.py _strip_motw`(clr import 전 번들 .dll/.pyd/.exe의 Zone.Identifier ADS 1회 제거, `.motw_cleared` 마커) + `BibleClipWeb.exe.config`의 `loadFromRemoteSources`(읽기전용 위치 백스톱, build_web.ps1 동봉). .NET·WebView2·Python 버전·보안SW 전부 무죄였음.
- **v1.1.1 내용**: 실행 실패 의심으로 CI Windows 빌드 Python 3.12→3.13 + `requirements.txt` 정확 버전 핀(재현성). 시작 실패 안내·로깅: 실제 .NET/WebView2/보안SW 탐지 후 원인별 분기(_diagnostics) + `userdata/startup_error.log` 기록 + 안내 페이지. (실제 진범은 v1.1.2의 MOTW였음 — 이 로깅 덕에 잡음.)
- **v1.1.0 내용**: FEAT-01 장바구니 DnD+FLIP / FEAT-02 매직 포맷터 매크로+태그칩 / FEAT-03 묵상 노트 **슬라이딩 레일 패널**(독립 카드에서 전환) / FEAT-04 카드별 대조 토글(역본 쌍 고정) / FEAT-05 병렬 복사 부스터 / BUG-01·BUG-i18n·FIX-01 핫픽스 / KJV+ 동봉 + 원전 분해 소스 선택
- **마지막 맵 동기화**: 2026-06-07 (v1.1.2 MOTW 자동 해제 반영)

---

## 1. 디렉토리 트리 구조 요약

```
BibleClip Project/
├─ bibleclip/                      # Python 패키지 (백엔드 + UI)
│  ├─ _version.py                  # 버전 단일 소스 ("1.1.2")
│  ├─ config.py                    # 플랫폼/폰트/경로/GitHub URL/리소스 해석
│  ├─ constants.py                 # 자모맵 + 책이름 테이블(한/영) + 영어역본 set
│  ├─ userconfig.py                # 라이선스 게이트(is_premium) — UI설정과 분리
│  ├─ usage.py                     # 익명 실행 핑(fire-and-forget)
│  ├─ killswitch.py                # 원격 킬스위치(비활성/강제업뎃) — fail-open
│  ├─ korean.py                    # 순수파이썬 한국어 검색 정규화(조사제거/토큰화)
│  ├─ morph.py                     # Kiwi 형태소 토큰화(frozen 빌드 비활성)
│  ├─ i18n.py                      # 백엔드측 i18n (web/locales/*.json 공유)
│  ├─ notes.py                     # 묵상 노트(절-단위 저장, user_notes.json)
│  ├─ text_utils.py                # 한글조합/clean_text/despace/trigrams
│  ├─ theme.py                     # LIGHT/DARK/CTK 색상 팔레트
│  ├─ update.py                    # GitHub Releases 업뎃 체크/에셋 선택/SSL
│  ├─ __main__.py                  # python -m bibleclip → ui.app.main()
│  ├─ core/                        # ★ UI 비의존 비즈니스 코어
│  │  ├─ engine.py                 #   참조 파서(한/영 텍스트 → 정규 튜플)
│  │  ├─ formatter.py              #   참조 → 출력 텍스트 포맷(설정 반영/매크로)
│  │  ├─ library.py                #   ★중앙 상태 허브(DB/설정/원어/파이프라인)
│  │  ├─ installer.py              #   업뎃 zip 다운/추출 + 업데이터 스크립트
│  │  └─ clipboard_monitor.py      #   클립보드 폴링 스레드(콜백 라우팅)
│  ├─ data/                        # ★ 데이터 액세스 레이어
│  │  ├─ bible_db.py               #   SQLite 성경 1개 래퍼(검색/지연색인)
│  │  └─ original_lang.py          #   히/헬 스트롱/렉시콘/원전분해
│  ├─ ui/                          # ★ 데스크톱 UI (CustomTkinter + Tkinter) — 믹스인 조합
│  │  ├─ app.py                    #   BibleClipApp 루트(10개 믹스인 조합)
│  │  ├─ viewer_tab.py             #   성경 뷰어 탭 빌드(3패널+로그)
│  │  ├─ viewer_ops.py             #   뷰어 칩 드래그/장로드/스크롤싱크/폰트/복사
│  │  ├─ settings_tab.py           #   출력설정 탭 빌드(버전순서+포맷)
│  │  ├─ order.py                  #   출력 버전 선택/순서/미리보기
│  │  ├─ search.py                 #   키워드 검색 + 결과 클릭복사
│  │  ├─ nav.py                    #   ←/→ 장 네비게이션 키바인딩
│  │  ├─ lexicon.py                #   원어 패널 클릭/호버/형태소/사전팝업
│  │  ├─ monitor.py                #   클립보드 모니터링 + 참조처리 + 로그
│  │  ├─ theming.py                #   다크/라이트 토글 + 위젯 테밍
│  │  ├─ updater_ui.py             #   업뎃체크/진행바/플랫폼 업데이터 스크립트
│  │  └─ widgets.py                #   ScrollDropdown(스크롤 가능 드롭다운)
│  └─ webui/                       # ★ pywebview 데스크톱(웹 프론트 + JS브리지)
│     ├─ app.py                    #   pywebview 창 부트스트랩/생명주기/.NET 에러
│     ├─ api.py                    #   Api 브리지 파사드(3개 라우트 믹스인 조합)
│     ├─ dicthtml.py               #   렉시콘 마크업 → HTML 헬퍼
│     ├─ __main__.py               #   python -m bibleclip.webui
│     └─ routes/                   #   JS-호출 가능 브리지 메서드(HTTP 아님)
│        ├─ bible.py               #     성경 탐색/검색/렉시콘 (BibleRoutes)
│        ├─ notes.py               #     묵상 노트 CRUD (NoteRoutes)
│        └─ system.py              #     부트/설정/업뎃/폰트/출력포맷 (SystemRoutes)
├─ web/                            # ★ 프론트엔드 SPA (vanilla JS, 프레임워크 없음)
│  ├─ index.html                   #   DOM 셸(.rail/.main/뷰/드로어/모달)
│  ├─ js/
│  │  ├─ i18n.js                   #   i18n 엔진(로케일 로드/라이브 전환/DOM스윕)
│  │  ├─ core.js                   #   부트/전역상태/API브리지/UI헬퍼 (window.BC)
│  │  ├─ cards.js                  #   ★CardManager(자유배치 카드 워크스페이스)
│  │  └─ search-notes.js           #   ★검색/노트/설정/카트/업뎃/폰트/약칭/라이브i18n
│  ├─ css/  (styles/tokens/fonts.css)
│  ├─ fonts/ (Pretendard)
│  └─ locales/ (ko.json, en.json)
├─ bibleclip_app.py                # 데스크톱(Tkinter) 진입점 shim
├─ bibleclip_web.py                # 웹뷰(pywebview) 진입점 shim
├─ bible_versions/                 # 성경 SQLite DB 드롭 폴더(KRV.SQLite3 등)
├─ original_lang/                  # 원어 데이터(HebGrkEn.dct, 개역한글S.sdb)
├─ tests/                          # test_core / test_webui_api / test_installer / test_killswitch
├─ killswitch.json                 # 킬스위치 매니페스트(recommend_version 등)
├─ version_changes.json            # 버전별 패치노트 데이터
└─ packaging/                      # build_web.ps1, build_mac.sh
```

**두 개의 런타임 프론트엔드가 공존**: (a) `ui/` = 레거시/병행 CustomTkinter 데스크톱 GUI, (b) `webui/`+`web/` = 현행 pywebview 데스크톱(웹 프론트). **둘 다 `core/`·`data/` 코어를 공유**한다.

---

## 2. 핵심 데이터 흐름

```
클립보드 → ClipboardMonitor.read_fn()
   → Library.build_output(text)
   → Engine.parse_reference(text, book_aliases)   # 참조 인식
   → BibleDB.get_verses / get_verse_text          # 절 본문
   → Formatter.format_version_output(...)          # 설정/매크로 반영 포맷
   → ClipboardMonitor.write_fn() → 클립보드
   → (webui) Api._on_reference → window.bibleclip.onReference(JS)
   → (web) CardManager.goToRef() → 카드 네비게이트/하이라이트
```

**설계 패턴**: 의존성 주입(Monitor가 read/write 콜러블 수신) · 지연 색인(BibleDB 첫 검색 시 인덱스 구축) · Fail-soft(모든 DB/파일 로드 예외 무시 후 진행) · 한국어 우선(스트롱/형태소/토큰화) · 믹스인 조합(`ui.app`, `webui.api`).

---

## 3. 백엔드 코어 (`bibleclip/core/`)

### core/engine.py — 참조 파서 (한/영 텍스트 → 정규 (책번호, 장, 절들))
- **class `Engine`** (무상태 파서)
  - `parse_reference(text, extra_books=None)` → [(book_num, short, long, chapter, verses)]
  - `parse_verses(verse_str)` → 정렬된 절번호 리스트 ("1-3,5" 범위 처리)
  - `resolve_ambiguous_book(book_str, has_verse_separator)` / `_lookup_book(...)` / `_lookup_english_book(...)` / `_lookup_alias_token(...)` / `_norm_book(s)` / `_canon(book_num)`
  - 패턴 상수: `VERSE_PATTERN`, `KOREAN_STYLE_PATTERN`, `ENGLISH_PATTERN`, `LEADING_ALIAS_PATTERN`
  - 의존: `KOREAN_BOOK_MAP`/`ENGLISH_BOOK_MAP`(constants), `convert_qwerty_to_hangul`(text_utils)

### core/formatter.py — 참조 → 출력 텍스트 포맷
- **class `Formatter`** — `__init__(settings, dbs=None)`
  - `format_version_output(db, book_num, chapter, verses, all_verse_data)` → str
  - `format_parallel(book_num, chapter, col1, col2)` → str — **FEAT-05 병렬 복사 부스터**. 두 역본(col=`(db, [(verse,text)])`)을 한 출력 블록으로 결합. `{content2}`/`{version2}` 매크로 사용
  - `_apply_template(tmpl, book_full, book_short, chapter, verse_list, content, version, content2='', version2='')` → str (매크로 치환 = **FEAT-02 매직 포맷터**, content2/version2 옵셔널 인자 추가)
  - `_build_body(all_verse_data, chapter)` → 단일·병렬 경로 공유 본문 빌더(추출 헬퍼)
  - `_format_verse_list(verses, range_sym)` → "1,3-5"
  - 설정 키: `book_name`/`chapter_verse_format`/`bracket_style`/`ref_position`/`range_symbol`/`ref_body_separator`/`output_mode`/`show_version_header`/`hide_reference`/`custom_format_enabled`/`custom_format_template`
  - 매크로 태그: `{book_full}`/`{book_short}`/`{chap}`/`{verse}`/`{content}`/`{version}`/`{content2}`/`{version2}`

### core/library.py — ★ 중앙 상태 허브 (UI 비의존 코어)
- **class `Library`** — `__init__()` 가 설정·DB·원어 전부 로드
  - **DB 로딩**: `load_databases()` / `load_bethlehem()` / `refresh_databases()`
  - **설정**: `load_settings()` / `save_settings()`
  - **읽기 API**: `versions()` / `books(version)` / `primary_version()` / `book_aliases()`(캐시) / `get_chapters(version, book_num)` / `get_chapter(version, book_num, chapter)` / `search(version, keyword)`
  - **원어**: `lookup_strong(code, lang='ko')` / `search_strong(code)` / `interlinear(book_num, chapter, version=None)` / `morphology(code, book_num, chapter, verse)`
  - **약칭 오버라이드**: `parse_reference(text)` / `load_alias_overrides()` / `list_alias_overrides()` / `add_alias_override(alias, book_num)` / `remove_alias_override(alias)`
  - **참조→출력**: `build_output(text)` → {kind:'reference'|'keyword',...} / `format_reference(book_num, chapter, verses, order=None)` → (text, n_parts) — 템플릿에 `{content2}`/`{version2}`가 있고 2개 이상 역본이면 `Formatter.format_parallel()`로 병렬 결합(FEAT-05), (text, 2) 반환
  - **모니터링**: `start_monitoring(read_fn, write_fn, on_reference, on_keyword)` / `stop_monitoring()` / `set_poll_interval(seconds)` / `notify_clipboard_written(text)`
  - 상태: `dbs`{name:BibleDB}, `bethlehem_strongs`/`bethlehem_wonjun`, `lexicon_ko`/`lexicon_en`, `settings`, `user_config`, `is_premium`, `notes`(Notes), `_monitor`
  - 상수: `DEFAULT_SETTINGS`(20+ 키)

### core/installer.py — 업뎃 zip 다운/추출 + 업데이터 스크립트 (순수/테스트가능)
- `download_file(url, dest, on_progress=None, timeout=30)` / `stage_payload(zip_path, extract_dir, payload_name)` / `write_windows_bat(bat_path, src_dir, install_dir, exe_name)` / `write_mac_sh(sh_path, src_dir, app_dst, pid, data_names=())`
- 의존: `urllib.request`, `zipfile`, `update.urlopen_resilient`

### core/clipboard_monitor.py — 클립보드 폴링 스레드
- **class `ClipboardMonitor`** — `__init__(read_fn, write_fn, build_output, on_reference, on_keyword, poll_interval=None)`
  - `start()` / `stop()` / `_loop()` / `_handle(text)`
  - 상태: `last`(자기출력 재인식 방지), `poll_interval`(런타임 가변), `_running`/`_thread`
  - 상수: `POLL_INTERVAL = 0.5`

---

## 4. 데이터 레이어 (`bibleclip/data/`)

### data/bible_db.py — SQLite 성경 1개 래퍼 (검색/지연색인)
- **class `BibleDB`** — `__init__(db_path)` (info+books 로드, 인덱스 지연=None)
  - 메타: `_load_info()` / `_load_books()` / property `display_name`
  - 절 접근: `get_chapters(book_number)` / `get_verses(book_number, chapter)`(정규화) / `get_chapter_raw(...)`(마크업 유지, 스트롱파싱용) / `get_verse_text(book_number, chapter, verse)`
  - 검색(**4단계 폴백**): `search(keyword, limit=300, fuzzy_threshold=0.7, mode='and')` / `smart_search(keyword, mode='and', limit=300)` / `_build_search_index()` / `_build_inverted_index()` / `inverted_index()` / `_score(addr, query_tokens)`
  - 라이프사이클: `close()`
  - 상태: `name`, `conn`, `info`, `description`, `language`, `is_english`, `has_strongs`, `books`{num:(short,long)}, `book_list`, 지연캐시 3종
  - 검색 4단계: ① smart(역색인 AND/OR+점수) ② 공백무시 substring ③ Kiwi 형태소 ④ trigram fuzzy
  - 의존: `sqlite3`, `korean.tokenize`, `morph.tokenize_keywords`, `text_utils`, `constants.ENGLISH_VERSIONS`

### data/original_lang.py — 히/헬 스트롱·렉시콘·원전분해
- 함수: `resolve_original_lang_dir(base_dir=None)` / `strip_korean_strongs(text)` / `parse_korean_strongs(text)`→[(word,code)] / `parse_english_strongs(text, book_num)` / `parse_wonjun_verse(text)`→[{surface,code,lemma,translit,pos,gloss}] / `render_dict_html(text_widget, html, base_font, fg, num_color)`
- **class `BethlehemDB`** — `__init__(db_path)`; `get_chapter_verses(our_book_num, chapter)` / `get_chapter_count(our_book_num)` / `search_by_strong(code)` / `close()`
- **class `Lexicon`** — `__init__(db_path)`; `lookup(code)`→dtext / `close()`
- 상수: `ORIGINAL_LANG_DIR="original_lang"`, `LEGACY_ORIGINAL_LANG_DIRS=["BethlehemWin"]`, `PROTESTANT_BOOK_ORDER`, `OUR_TO_BETHLEHEM`/`BETHLEHEM_TO_OUR`, `WONJUN_BLOCK`(regex), `NT_FIRST_BOOK_NUM=470`(≥470=헬라어)

---

## 5. 톱레벨 유틸/지원 모듈 (`bibleclip/*.py`)

| 파일 | 역할 | 주요 심볼 |
|---|---|---|
| `config.py` | 플랫폼/폰트/경로/URL/리소스 해석 | `IS_WINDOWS`, `UI_FONT`/`BODY_FONT`/`MONO_FONT`/`SERIF_FONT`, `GITHUB_OWNER`("tpwns432-maker")/`GITHUB_REPO`("BibleClip"), `UPDATE_CHECK_URL`/`RELEASES_PAGE_URL`/`KILLSWITCH_URL`/`USAGE_PING_URL`, `BASE_DIR`/`SETTINGS_FILE`/`USERDATA_DIR`/`BIBLE_DIR`; `get_base_dir()`/`get_resource_dir()`/`system_env()`/`get_userdata_dir()`/`candidate_data_roots()`/`resolve_data_dir(name)` |
| `userconfig.py` | 라이선스 게이트(설정과 분리) | `CONFIG_FILE="config.json"`, `DEFAULTS={'is_premium':True}`; `config_path()`/`load_user_config()`/`is_premium()` |
| `usage.py` | 익명 실행 핑 | `_ping(url)`/`ping_usage_async(url=USAGE_PING_URL)` |
| `killswitch.py` | 원격 킬스위치(fail-open) | `_fetch_manifest(timeout)`/`check_killswitch(timeout=6)`→(blocked,msg)/`recommended_version(timeout=6)` |
| `morph.py` | Kiwi 형태소(frozen 비활성) | `_CONTENT_TAGS`, `_get_kiwi()`/`available()`/`tokenize_keywords(text, min_len=2)` |
| `korean.py` | 순수파이썬 한국어 정규화 | `_PARTICLES`/`_STOPWORDS`; `strip_particle(token)`/`tokenize(text)` |
| `i18n.py` | 백엔드 i18n(웹로케일 공유) | `DEFAULT_LANG='ko'`; `_table(lang)`/`t(key, lang, **fmt)`/`resolve_ui_lang(settings=None)` |
| `notes.py` | 묵상 노트(절-단위) | `NOTES_FILE="user_notes.json"`; **class `Notes`**: `get/set/delete(book,chapter,verse)`, `all()`, `for_chapter(book,chapter)` |
| `text_utils.py` | 한글조합/정제/검색 | `convert_qwerty_to_hangul(text)`/`assemble_hangul(jamo)`/`clean_text(text)`/`despace(s)`/`trigrams(s)` |
| `constants.py` | 정적 데이터 | `QWERTY_TO_HANGUL`, `CHOSEONG`/`JUNGSEONG`/`JONGSEONG`, `KOREAN_BOOK_MAP`{name→(id,abbr,full)}, `ENGLISH_BOOK_MAP`, `ENGLISH_VERSIONS`(set) |
| `theme.py` | 색상 팔레트 | `LIGHT_THEME`/`DARK_THEME`/`CTK`(각 (light,dark) 튜플) |
| `update.py` | GitHub 업뎃 체크 | `parse_version(s)`/`urlopen_resilient(req, timeout)`/`fetch_latest_release(timeout=8)`/`select_platform_asset(assets)` |
| `_version.py` | 버전 단일 소스 | `__version__="1.1.2"` |

**의존 그래프**: `_version` ← `config` ← (대부분); `korean`/`constants`/`theme` 독립; `morph` Kiwi-옵셔널; `text_utils` ← `constants`.

---

## 6. 데스크톱 UI (`bibleclip/ui/` — CustomTkinter + Tkinter)

진입점 `bibleclip_app.py::main()` → `ui.app`. **믹스인 조합 패턴**: `BibleClipApp(ViewerTabMixin, SettingsTabMixin, LexiconMixin, OrderMixin, ViewerOpsMixin, SearchMixin, NavMixin, MonitorMixin, ThemeMixin, UpdateMixin)`. `self.core` = Library.

| 파일 | 믹스인/클래스 | 핵심 메서드 |
|---|---|---|
| `app.py` | `BibleClipApp` | `__init__(root)`, `_build_ui()`, `_on_tab_change(value)`, `_show_tab(name)`, `_build_top_bar()`, `_refresh_databases()`, `_save_settings()`, `_get_format_settings()` |
| `viewer_tab.py` | `ViewerTabMixin` | `_build_viewer_tab()` (칩바+네비카드+3패널 PanedWindow+로그). 위젯: `viewer_text`/`lex_mid_text`/`lex_right_text`/`log_text`, `book_combo`/`chapter_combo`(ScrollDropdown), `search_entry`, `lex_lang_seg` |
| `viewer_ops.py` | `ViewerOpsMixin` | 칩 DnD: `_render_viewer_versions()`/`_build_chip(name)`/`_layout_chips(...)`/`_chip_anim_step()`/`_commit_drag(...)`; 장로드: `_populate_books()`/`_load_chapter(highlight_verses)`/`_on_chapter_changed(e)`; 스크롤싱크: `_scroll_text_to_verse(...)`/`_do_sync_middle_to_viewer()`; 폰트: `_change_font_size(delta)`/`_on_ctrl_wheel(e)`; 복사: `_copy_verses_formatted(verse_nums)`; sash: `_restore_sash_positions(...)`/`_capture_sash_positions()` |
| `settings_tab.py` | `SettingsTabMixin` | `_build_settings_tab()` (좌:버전 듀얼리스트박스/우:포맷 세그먼트+미리보기). vars: `book_name_var`/`cv_format_var`/`bracket_var`/`position_var`/`range_var`/`sep_var`/`output_mode_var`/`newline_cv_var`/`version_header_var`/`hide_ref_var` |
| `order.py` | `OrderMixin` | `_refresh_available_list()`/`_add_to_order()`/`_remove_from_order()`/`_move_up()`/`_move_down()`/`_clear_order()`/`_sync_order_to_settings()`/`_on_setting_changed()`/`_update_preview()` |
| `search.py` | `SearchMixin` | `_on_search_box(e)`/`_search_version()`/`_run_search(raw, copy_first=False)`/`_render_search_results(...)`/`_on_search_result_click(idx)`/`_copy_single_ref(book_num, chapter, verse)` |
| `nav.py` | `NavMixin` | `_nav_keys_allowed()`/`_on_arrow_prev(e)`/`_on_arrow_next(e)`/`_prev_chapter()`/`_next_chapter()` |
| `lexicon.py` | `LexiconMixin` | `_render_lex_middle(our_bn, chapter)`/`_lex_word_at(e)`/`_on_lex_word_click(e)`/`_on_lex_word_popup(e)`/`_on_lex_hover(e)`/`_show_tip(...)`/`_morphology_html(code, verse)`/`_show_lex_entry(code, verse)`/`_open_lex_popup(code, verse)`; Win32 z-order: `_win_zorder_map()`/`_win_root_hwnd(win)` |
| `monitor.py` | `MonitorMixin` | `_toggle_monitoring()`/`_clipboard_read()`/`_clipboard_write(text)`/`_on_reference_caught(r)`/`_on_keyword_caught(keyword)`/`_update_viewer_from_ref(...)`/`_append_log_ref(...)`/`_update_status(text, active)` |
| `theming.py` | `ThemeMixin` | `_toggle_dark_mode()`/`_apply_theme()`/`_apply_viewer_chip_theme()`/`_apply_listbox_theme()`/`_style_scrollbar(sb)` |
| `updater_ui.py` | `UpdateMixin` | `_start_update_check()`/`_update_check_worker()`/`_manual_update_check()`/`_show_update_banner()`/`_start_update()`/`_write_mac_updater_sh(...)`/`_write_updater_bat(...)`/`_download_with_progress(...)`/`_on_close()` |
| `widgets.py` | `ScrollDropdown(ctk.CTkButton)` | `__init__(master, values, variable, command, width, max_visible, **kw)`/`configure(**kw)`/`set(value)`/`get()`/`_open()`/`_close()`/`_select(value)` |

---

## 7. 웹 UI / 브리지 레이어 (`bibleclip/webui/`)

> **중요**: HTTP 서버 아님(Flask/http.server 없음). **pywebview** = WebView2/Chromium 임베드 + JS 브리지. JS↔Python 통신은 `pywebview.api.<method>()` 호출. 백→프론트 푸시는 `window.bibleclip.<fn>()` (evaluate_js).

### webui/app.py — pywebview 창 부트스트랩/생명주기
- `main()`(공개진입) → **`_strip_motw()`(시작 즉시, clr import 전: 다운로드 zip이 번들 .dll/.pyd/.exe에 남긴 MOTW=Zone.Identifier ADS를 제거 → .NET이 Python.Runtime.dll 로드 거부하던 문제 해소. `_MEIPASS` 기준, `.motw_cleared` 마커로 1회)** → `_main()`(Library+Api+창생성+워치독). 시작 실패 시: `_diagnostics(exc)`로 실제 .NET/WebView2/보안SW 탐지 → `_log_startup_error()`(`userdata/startup_error.log` 기록) → `_show_runtime_error(diag)` 원인별 분기(.NET 없음→.NET / WebView2 없음→WebView2 / 둘 다 있으면→보안 차단 안내).
- 진단 프로브: `_is_runtime_error(exc)`(텍스트 휴리스틱), `_dotnet_release()`(레지스트리 NDP\v4\Full Release≥461808=4.7.2+), `_webview2_version()`(EdgeUpdate Clients GUID `pv`), `_security_software()`(Services 레지스트리에서 안랩/V3/ASTx 등 키워드 매칭)
- 기타: `_index_path()`, `_blocked_html`, `_conn_error_html(lang)`, `_on_closing()`, `_open_popup(title, html)`, `_conn_watchdog()`(15s ERR_CONNECTION_REFUSED 가이드)
- 상수: `DOTNET_PAGE_URL`, `WEBVIEW2_PAGE_URL`(설치본 자동다운 대신 안내 페이지), `_SECURITY_KW`
- locale: `dotnet.errTitle/errBody`, `webview2.errTitle/errBody`, `secblock.errTitle/errBody`

### webui/api.py — Api 브리지 파사드
- **class `Api(SystemRoutes, BibleRoutes, NoteRoutes)`** — `__init__(library)`; `set_window(window)`/`set_popup_factory(factory)`/`_push(fn, *args)`
  - 모니터링: `start_monitoring()`/`stop_monitoring()`/`_clip_read()`/`_clip_write(text)`/`_on_reference(result)`/`_on_keyword(keyword)`
  - 복사/내보내기: `copy_reference(book, chapter, verses, versions=None)`/`copy_references(items, versions=None)`/`copy_text(text)`/`export_text_file(text, suggested_name)`
  - `pyperclip` 클립보드 백엔드(옵셔널); dicthtml 심볼 재익스포트

### webui/dicthtml.py — 렉시콘 마크업 → HTML
- `markup_to_html(markup)`/`parse_entry(markup)`→{headword,reading,html}/`_morph_html(morph, lang='ko')`/`_dict_page_html(code, entry, theme='light', lang='ko')`(자체완결 팝업페이지)
- 상수: `_NUM_RE`/`_FIRST_FONT_RE`/`_TAGS_RE`/`_LEAD_BR_RE`/`_DICT_THEMES`(light/dark)

### ★ JS-호출 가능 브리지 메서드 인벤토리 (= 프론트가 부르는 "API")

> 새 API 추가 시 **이 표를 즉시 갱신**. (HTTP route가 아니라 `pywebview.api.<name>()` RPC)

**BibleRoutes (`routes/bible.py`) — 성경 탐색/검색/렉시콘:**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `get_books` | `(version)` | 버전의 책 목록 |
| `get_chapters` | `(version, book)` | 책의 장 목록 |
| `get_chapter` | `(version, book, chapter)` | {ref, verses:[{n,text}]} |
| `get_interlinear` | `(book, chapter, version=None)` | [{n, words:[{w, code}]}] 원전분해 |
| `resolve_reference` | `(text)` | "창 1:1" → {book_num,short,long,chapter,verses}|None |
| `get_aliases` | `()` | [{alias, book_num, book_name}] 사용자 약칭 |
| `add_alias` | `(alias, book_num)` | {ok}|{ok:False,error_code} |
| `remove_alias` | `(alias)` | {ok} |
| `search_strong` | `(code)` | 역검색 {code,count,hits:[...]} |
| `search` | `(keyword, version=None, limit=200, mode='and')` | {keyword,version,display,mode,matched_tokens,hits} |
| `lookup_strong` | `(code, lang='ko', book=None, chapter=None, verse=None)` | 전체엔트리 {code,headword,reading,html,morph} |
| `hover_summary` | `(code, book=None, chapter=None, verse=None)` | 짧은 미리보기 {code,headword,reading,lines} |
| `open_dict_window` | `(code, lang='ko', book=None, chapter=None, verse=None, theme='light')` | 독립 네이티브 사전 팝업 {ok} |
| `_search_version` | (헬퍼) | 기본 검색 버전 결정 |

**NoteRoutes (`routes/notes.py`) — 묵상 노트 CRUD (FEAT-03):**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `get_chapter_notes` | `(book, chapter)` | {verse→text} (📄 배지용) |
| `get_all_notes` | `()` | 전체 [{book,chapter,verse,text,ts}] (모아보기 카드) |
| `get_note` | `(book, chapter, verse)` | {text, ts}|None |
| `set_note` | `(book, chapter, verse, text)` | 생성/수정/삭제(빈텍스트=삭제) {ok, note} |
| `delete_note` | `(book, chapter, verse)` | {ok} |

**SystemRoutes (`routes/system.py`) — 부트/설정/업뎃/폰트/출력포맷:**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `get_initial` | `()` | ★부트 1회 페이로드(versions/primary/viewer/books/last/dark_mode/font_size/lex_lang/ui_lang/reading_font/interlin_sources/is_premium/web_cards_layout/version…), `_booted` set |
| `get_locale` | `(lang)` | 프론트 i18n 문자열 테이블 |
| `list_fonts` / `get_font` | `()` / `(file)` | 커스텀 읽기폰트 목록 / base64 폰트 바이트 |
| `set_dark_mode` | `(on)` | 다크모드 저장 |
| `set_font_size` | `(size)` | 8~400 클램프 저장 |
| `refresh_databases` | `()` | bible_versions 재스캔 {added, versions} |
| `note_position` | `(book, chapter)` | 마지막 위치 기억 |
| `set_viewer_versions` | `(names)` | 뷰어 병행 버전 set(최소 1유지) |
| `set_viewer_order` | `(names)` | 칩 드래그 순서(FEAT 관련) |
| `get_app_settings` / `set_app_setting` | `()` / `(key, value)` | 앱설정 읽기 / 화이트리스트(`_APP_KEYS`) 검증저장(poll_interval은 라이브 적용) |
| `reset_settings` | `()` | 전체 기본값 복원 |
| `open_data_folder` / `open_github` | `()` | OS 파일매니저 / 브라우저 |
| `save_cards_layout` | `(layout)` | 웹 카드 레이아웃 JSON 저장 |
| `check_update` | `()` | GitHub 최신릴리스 {has_update,mandatory,current,latest,notes,url,skipped} |
| `get_patch_notes` / `dismiss_patch` | `()` / `(forever=False)` | 현버전 패치노트 / 모달 확인 |
| `open_releases_page` / `skip_update` | `()` / `(version)` | 릴리스페이지 / 버전 스킵 |
| `install_update` | `()` | 다운+스테이징+인플레이스 적용(frozen만, 워커스레드) |
| `get_settings` | `()` | {format, output_order, versions} 출력설정 |
| `set_setting` | `(key, value)` | `_FORMAT_KEYS` 화이트리스트 한 개 갱신 |
| `set_output_order` | `(names)` | 클립보드 출력 버전 순서 |
| `get_preview` | `()` | 샘플(요 1:1-3) 현 설정 포맷 미리보기 |
| 헬퍼 | | `_interlin_sources()`, `_version_changes()`, `_run_install(info)`, `_quit_for_update()` |

- **`_APP_KEYS`**: auto_update_check, search_click_navigates, auto_copy_top_result, lex_lang('ko'/'en'), ui_lang('ko'/'en'), reading_font, poll_interval(0.1~2.0), web_cards_layout
- **`_FORMAT_KEYS`**: book_name, chapter_verse_format, bracket_style, ref_position, range_symbol, ref_body_separator, output_mode, newline_show_cv, show_version_header, hide_reference, **custom_format_enabled**, **custom_format_template**(≤500자, FEAT-02)

---

## 8. 프론트엔드 SPA (`web/` — vanilla JS, 프레임워크 없음)

**스크립트 로드 순서(필수)**: `i18n.js` → `core.js` → `cards.js` → `search-notes.js`(끝에서 boot()). 전역 네임스페이스 `window.BC`, `window.I18N`, `CardManager`. 백→프론트 푸시: `window.bibleclip.{onReference, onKeyword, onUpdateProgress, onUpdateReady, onUpdateError}`.

**index.html DOM 셸**: `.rail`(좌측 아이콘 네비, `#notes-toggle` 포함) + `.main`(`.topbar`/`.controls`/`.viewer-view>.panels-container`/`.settings-view`/`.search-view`) + 드로어(`#log-drawer`/`#cart-drawer`/**`#notes-drawer`**(FEAT-03 묵상 노트 레일 패널: `#notes-list`+`#notes-foot`)) + 모달(`#settings-modal`/`#alias-modal`) + `.toast-wrap`.

### i18n.js — i18n 엔진 (IIFE, `window.I18N`)
- `register(lang, dict)`/`lookup(key)`/`t(key, vars)`/`apply(root)`(DOM스윕)/`load(lang)`/`boot()`/`setLang(lang)`/`getLang()`
- 데이터 속성: `data-i18n`(textContent)/`-html`/`-title`/`-tip`/`-placeholder`/`-aria`
- 이벤트: `window.dispatchEvent("i18n:changed", {detail:{lang}})`
- `tables`{lang:{key:str}}, `current`, `SUPPORTED=["ko","en"]`, `DEFAULT_LANG="ko"`

### core.js — 부트/전역상태/API브리지/UI헬퍼 (`window.BC`)
- `boot()` async(i18n로드→get_initial→카드복원→전역컨트롤 와이어), `applyFontScale()`, `booksFor(version)`/`chaptersFor(version, book)`/`bookLongFor`/`bookShortFor`/`displayName(name)`
- 팝업/UI: `openMenu(anchor, items, onPick, opts)`/`closeMenus()`/`showTooltip(el)`/`hideTooltip()`/`toast(msg)`/`openDrawer()`/`closeDrawer()`/`flagUnread()`
- 와이어링: `wireGlobalControls()`/`wireMonitor()`/`wireCart()`/`wireTabs()`/`wireUpdate()`/`wireAppSettings()`/`wireReadingFontMenu()`/`wireAliasManager()`/`bootReadingFont(family)`/`maybePatchModal()`
- `state` 객체(versions/viewer/primary/monitoring/fontSize/lexSources/isPremium…), `window.pywebview.api` 브리지

### cards.js (~1765줄) — ★ CardManager (자유배치 카드 워크스페이스, IIFE)
- **카드 타입**: `"bible"`/`"interlinear"`/`"lexicon"` (※ v1.1.0에서 `"notes"` 카드 타입 **폐기** → 슬라이딩 레일 패널로 전환, search-notes.js로 이동)
- **모듈 상태**: `cards[]`, `activeId`, `fsCardId`(F11 전체화면), `zTop`, `cascadeN`, `interacting`, `progScroll`(싱크가드)
- **FEAT-04 대조(parallel) 필드**: `card.parallel`(bool), `card.parallelVersion`(str) — 카드별 대조 토글, 역본 쌍 고정
- CRUD: `init(layout)`/`addCard(type)`/`addCardWithLink(type, linkId)`/`removeCard(id)`/`mountCard`/`unmountCard`/`renderAll()`/`serialize()`/`restore(layout)`
- 지오메트리(%기반): `startMove(card, sec, e)`/`startResizeCard(card, sec, dirs, e)`/`applyGeom(card)`/`bringToFront(card)`/`setActive(card)`/`snapTo(...)`/`computePush(...)`/`renderGuides`/`clearGuides`. 상수 `MIN_W=12%`/`MIN_H=15%`/`SNAP_PX=8`/`DIV_X`/`DIV_Y`
- 네비/로드: `goToRef(book, chapter, verses)`/`loadCard(card)`/`loadBibleCard(card, highlight)`/`loadInterlinearCard(card)`/`loadLexiconCard(card)`/`reloadDependents(card)`/`decorateNotes(card)`/`ensureInterlinearFor(bibleId)` (※ `loadNotesCard` 제거됨)
- 히스토리: `seedHistory`/`recordHistory`/`cardHistoryNav(card, delta)`/`cardChapStep(card, delta)`/`chapStepPrimary`/`chapStepActive`/`updateNavButtons`
- 잠금(N-1 규칙): `toggleLock(card)`/`normalizeLocks()`/`refreshLockStates()`
- 싱크(BUG-01 픽스): `anchorVerseOf(body)`/`verseTopFraction(body, n)`/`scrollBodyToVerse(...)`/`syncInterlinFrom(card, body)`/`snapshotAnchors()`/`realignAnchors(anchors)`/`lockHistoryVerse(card, body)`(500ms 디바운스) — 본문 점프 시 원어 카드가 타깃 절 추종(1절 고정 버그 해소)
- 렌더: `headerHTML(card)`/`skeleton(card)`/`updateBibleHeader`(대조 pill 렌더)/`handleAction(card, act, actEl)`(case `"parallel"`=대조 역본 선택 드롭다운)/`renderVersesInto(...)`/`renderMultiVersesInto(...)`/`cardVersions(card)`(대조 시 [base, parallelVersion] 반환, 렌더·복사 공유)/`renderInterlinearInto`/`renderLexEntryInto`/`renderMorph` (※ `renderNotesInto`/`wireNotes` 제거됨)
- 이벤트 위임: `wireContainer()` (클릭/스크롤/드래그/contextmenu/hover 단일 핸들러)
- public: `{init, addCard, addCardWithLink, goToRef, primaryVersion, primaryBible, bibleCards, lexiconCards, bodyEl, linkedBibleFor, chapStepPrimary, chapStepActive, reloadAllBible, relabel, presentToggle, ensureInterlinearFor, decorateNotesFor:decorateNotes, snapshotAnchors, realignAnchors}`

### search-notes.js (~1682줄) — ★ 검색/노트/설정/카트/업뎃/폰트/약칭/라이브i18n
- 노트/절메뉴: `showVerseMenu(card, verse, x, y)`/`openNoteEditor(card, verse)`/`addVerseToCart(card, verse)`/`openOriginalFor(card, verse)`
- **묵상 노트 레일 패널(FEAT-03, 카드→레일 전환)**: `renderNotes()`(API에서 전체 노트 fetch·렌더)/`openNotes()`/`closeNotes()`(로그·카트와 상호배타)/`wireNotesRail()`(토글·새로고침·복사·내보내기·전체선택 바인딩)/`buildNotesText(list)`/`notesTargets()`(선택분 없으면 전체)/`syncNotesSelAll()`/`noteRowKey(n)`. 상태: `notesData[]`/`notesSel`(Set). DOM: `#notes-drawer`/`#notes-list`/`#notes-foot`/`#notes-toggle`/`#notes-close`/`#notes-reload`/`#notes-selall-cb`/`#notes-copy`/`#notes-export`. API: `get_all_notes()`/`copy_text(text)`/`export_text_file(text, filename)`
- 호버툴팁: `scheduleTip(code, verse, book, chapter, x, y)`(400ms)/`hideTip()`
- 업뎃/패치: `checkUpdate(silent)`/`showForcedUpdate(r)`/`maybePatchModal()`/`onUpdateProgress`/`onUpdateReady`/`onUpdateError`/`wireUpdate()`
- 앱설정모달: `openAppSettings()`/`closeAppSettings()`/`setSeg(...)`/`setSwitch(...)`/`wireAppSettings()`/`wireSettingsActions()`
- 버전칩(FLIP애니): `renderVerChips()`/`flipChips(prev)`/`updateViewerVersions(newViewer)`/`wireChipDrag()`/`layoutChipGap(insertIdx)`/`commitChipDrag()`
- 모니터링: `setStatus(active)`/`wireMonitor()`/`logReference(entry)`/`renderLog()`/`flagUnread()`
- **장바구니(FEAT-01 DnD+FLIP)**: `addToCart(item)`/`removeFromCart(i)`/`clearCart()`/`saveCart()`/`cartKey(it)`/`renderCart()`/`wireCartDnD(list)`/`flipReorder(list, mutate)`(드래그 중 FLIP 실시간 위치 애니메이션)/`commitCartFromDOM(list)`(DnD 후 DOM 순서→카트 배열 동기화, dragend)/`extractCart(items, allMode)`/`extractAllCart()`/`extractSelectedCart()`/`toggleSelectAll(on)`/`openCart()`/`closeCart()`/`wireCart()`
- F2 빠른검색: `openQuickSearch()`/`closeQuickSearch()`/`quickJump(q)`
- 커스텀 읽기폰트: `loadFontsList()`/`injectFont(family, file)`/`applyReadingFont(family)`/`selectReadingFont(...)`/`bootReadingFont(family)`/`fontStep(size)`/`nextFontSize(size, d)`/`wireReadingFontMenu()`
- 약칭관리: `setAliasBook(num)`/`renderAliasList()`/`addAlias()`/`openAliasManager()`/`closeAliasManager()`/`wireAliasManager()`
- 출력설정(+FEAT-02 매크로 템플릿 UI, 태그 버튼화): `renderFormat()`/`renderOrder()`/`commitOrder(next)`/`moveOrder(i, d)`/`removeOrder(i)`/`loadSettings()`/`refreshPreview()`/`insertAtCaret(input, text)`(태그칩 클릭 시 커서 위치에 매크로 삽입). 상수 `FORMAT_MACRO_TAGS`(`{book_full}`…`{content2}`/`{version2}`), UI `.fmt-tagchips`/`.fmt-tagchip`(칩 버튼)
- 통합검색: `runSearch(kw)`/`searchMode()`/`copyHit(h)`/`renderSearch(res)`/`renderStrongSearch(res)`/`wireSearchHitClicks()`/`highlightHtml(...)`/`renderSuggest(q)`/`wireSearch()`/`updateSearchVerLabel()`
- 뷰전환/전역: `showView(name)`('viewer'|'settings'|'search')/`wireTabs()`/`wireGlobalControls()`/`refreshDbs()`/`retranslateViewport()`(i18n:changed시)/`relabelDynamic()`
- 키보드: F11=presentToggle, F2=openQuickSearch, ←/→=chapStepActive, +/−(전체화면)=폰트
- 전역상태: `noteCache`/`lexLang`/`lexCur`/`refLog`/`cart`/`cartSel`/`cartDragFrom`/`searchHits`/`fontsList`/`setState`(출력설정)/`notesData`/`notesSel`(노트 레일 패널)

---

## 9. 버전별 핵심 인프라 성과 (롤백/사이드이펙트 주의)

- **v1.0.5** — BibleDB 4단계 검색 폴백(smart 역색인 AND/OR + 점수), `korean.py` 순수파이썬 정규화 도입
- **v1.0.7** — 카드 컨텍스트 격리, 약칭(alias) UI 안정화
- **v1.0.8** — 보안 loopback 차단 안내(한국 보안모듈/방화벽 대응)
- **v1.0.9** — .NET 누락 시 네이티브 안내 + 설치 직링크(`DOTNET_DOWNLOAD_URL`), killswitch `recommend_version` 소프트 넛지
- **v1.1.0(릴리즈 준비완료)** — **핫픽스**: BUG-01(본문 점프 시 원어 카드 1절 고정 → 타깃 절 추종) / BUG-i18n(사전 카드 `dict.placeholder` 영어 번역 누락) / FIX-01(F2 잠금 카드 스크롤 이탈). **신기능**: FEAT-01 장바구니 DnD+FLIP 실시간 애니메이션 / FEAT-02 매직 포맷터(매크로 `custom_format_template` + 태그칩 버튼화) / FEAT-03 묵상 노트 **슬라이딩 레일 패널**(`#notes-drawer`, 독립 카드에서 전환) / FEAT-04 카드별 대조 토글(`card.parallel`/`parallelVersion`, 역본 쌍 고정) / FEAT-05 병렬 복사 부스터(`Formatter.format_parallel`, `{content2}`/`{version2}`) / KJV+ 동봉 + 원전 분해 소스 선택(`interlin_sources`, viewer 분리)
- **배포 실행환경 이슈**: 한국 보안모듈/미서명 exe 차단 → 일반사용자 실행 실패(.NET CLR 로드 실패·loopback 차단). 근본완화 = 코드서명(Authenticode).

---

## 10. 테스트 (`tests/`)
- `test_core.py` — Engine 파싱/Formatter/Library 코어
- `test_webui_api.py` — Api 브리지 메서드(헤드리스, webview 미임포트 설계 덕분)
- `test_installer.py` — installer 다운/스테이징/스크립트
- `test_killswitch.py` — 킬스위치 fail-open/min_version 로직
