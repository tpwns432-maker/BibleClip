# BibleClip v1.0.3 작업 보고서 (제미나이 / AG Manager 인계용)

> 작성: Claude Code · 대상: AG Manager(제미나이) · 기준 커밋 `v1.0.3` (태그 푸시됨)
> 코드 전체 변경은 루트의 **`v1.0.3_changes.diff`** (124K, `git diff v1.0.2..v1.0.3`) 참고.
> 전달 방법: 이 파일 + `v1.0.3_changes.diff` 두 개를 제미나이에 붙여넣으면 됩니다.

---

## 0. 한 줄 요약
TODO.md **7차 통합 명세(Phase 1~4)** 를 전부 구현하고 **v1.0.3** 으로 릴리스했습니다.
가장 중요한 변화는 **저작권 데이터 분리**(개역한글만 동봉)와 그에 따른 **개역한글s 스트롱 태그
기반 원어 엔진** 도입입니다. 검증(헤드리스 3종 + JS 문법 + NUL) 전부 통과.

## 1. 릴리스/배포 상태
- 배포 버전: **v1.0.3** (커밋 `70213a2`, 태그 `v1.0.3`) — CI가 Win/Mac 클린 빌드 진행.
- **저작권 리메디에이션 완료**: 공개 repo HEAD에서 저작권 데이터 추적 해제 + 기존 릴리스(v1.0.0~1.0.2)
  자산 9개 전부 삭제(`gh`로 처리). 과거 커밋 히스토리는 유지(force-push 안 함, 사용자 결정).
- 빌드 동봉 데이터: **`KRV.SQLite3` + `개역한글S.sdb` 만**. 그 외 역본·사전(HebGrkKo TWOT 한글판,
  HebGrkEn, ESV/NKJV 등)은 **유저가 직접 모듈로 추가**(외장형).

## 2. Phase별 구현 요약 (파일 기준)

### Phase 1 — 비즈니스 가드 (`cf15ea0`)
- `bibleclip/userconfig.py` (신규): `userdata/config.json` 의 `{is_premium}` 로드(fail-soft).
- `bibleclip/usage.py` (신규): 익명·fail-open 구동 핑(데몬 스레드). `config.USAGE_PING_URL`.
- `library`: `is_premium`/`reload_user_config()`; `api.get_initial` 에 `is_premium` 노출.
- `web/app.js`: 무료 게이팅 — 카드 1개 고정(`addCard`/`addCardWithLink`/`init` 트림), 키보드 ←/→ 락.
- `clipboard_monitor`: `stop()` 스레드 join, 콜백 예외 격리.

### Phase 2 — 저작권 가드 + 원어 엔진 (`f880a63`, `5de7990`, `2b1effe`)
- **데이터 분리**: `.gitignore`/빌드 3경로(CI `build.yml`·`build_web.ps1`·`build_mac.sh`)를 화이트리스트로.
- **엔진 백엔드** (`original_lang.py`/`library.py`/`api.py`): `strip_korean_strongs()`(태그 제거),
  `BethlehemDB.search_by_strong()`(`LIKE '%<WH3068>%'`), `search_strong()`(스트롱→구절 역검색).
- **UI** (`api.resolve_reference` + `web/app.js`/`index.html`/`styles.css`): **통합 검색바** —
  한 입력창에서 구절 점프(`창 1:1`)·키워드·원어코드(`H7225`) + 책 이름 자동완성.

### Phase 3 — 묵상 노트 + 분할 비교 (`d74d35a`)
- `bibleclip/notes.py` (신규): `userdata/user_notes.json`(키 `book:chapter:verse`) CRUD, fail-soft.
- `api`: `get/set/delete_note`, `get_chapter_notes`.
- `web/app.js`: 구절 우클릭 컨텍스트 메뉴(구절 복사 / 묵상 노트 / 원어 코드 조회), 노트 에디터 모달,
  📄 배지 + 호버 미리보기. 같은 책·장 성경 카드 간 스크롤 동기화(`progScroll` 루프 가드).
- Export 템플릿: 기존 출력 설정 + "구절 복사"가 이미 `[창세기 1:1] 본문`을 제공 → **중복 미구현**.

### Phase 4 — 패치노트 + 강제 업데이트 + 가이드 (`cf3a1b0`)
- `version_changes.json` (신규, 빌드 동봉): 버전별 변경 내역.
- `api.get_patch_notes/dismiss_patch` + settings `seen_version`/`dismissed_patches`: 첫 실행 패치노트
  모달('다시 보지 않기' 가드). `web/app.js` `maybePatchModal`.
- 강제 업데이트(soft): `killswitch.json` 의 신규 `recommend_version` 임계값 < 현재 → 닫기 불가 모달
  (앱은 실행됨; 하드 차단은 기존 `min_version`). `killswitch.recommended_version()`, `check_update` 에 `mandatory`.
- `사용법.html`: 데이터 정책 콜아웃(개역한글만 기본 + ph4.org 모듈 추가 딥링크).

## 3. ⚠️ 검토가 필요한 설계 결정 / 가정 (제미나이 확인 요망)
1. **`is_premium` 기본값 = True**: 결제 백엔드가 없어 전체 기능을 기본 제공. 백엔드가
   `userdata/config.json` 에 `{"is_premium": false}` 를 쓰면 무료 제한(카드 1개·단축키 락)이 즉시 작동.
   → 무료 정책을 실제로 켜려면 백엔드(또는 기본값) 결정 필요.
2. **무료 모드 "카드 1개 고정"**: `init`에서 첫 성경 카드만 남기고 트림. UX가 강하니 정책 재확인 권장.
3. **구동 카운터 엔드포인트**: 기본 `USAGE_PING_URL = api.github.com/repos/OWNER/REPO`(익명·무해).
   실제 집계가 필요하면 전용 카운트 엔드포인트로 교체해야 함(현재는 토대만).
4. **강제 업데이트**가 기존 **킬스위치 `min_version`(하드 차단)** 과 의미가 겹침. 신규 `recommend_version`
   은 "소프트(모달만)"로 구분했으나, 운영상 둘을 어떻게 쓸지 정리 필요.
5. **Export 템플릿**은 기존 출력 설정과 중복이라 별도 팝업 미구현(우클릭 "구절 복사"로 대체). 별도 UI가
   꼭 필요하면 추가 명세 바람.
6. **한글 원어 뜻풀이**: TWOT 한글 사전 제거로, 사전 모듈 미설치 시 스트롱 클릭은 "모듈 추가 안내"만 표시.
   원어 *역검색*(구절 찾기)은 개역한글s 태그로 사전 없이 동작.

## 4. 새 JS↔Python API (프론트 계약)
- `resolve_reference(text)` → `{book_num, short, long, chapter, verses}` | null
- `search_strong(code)` → `{code, count, hits:[{book_num, ref, chapter, verse, text}]}`
- `get_chapter_notes(book, chapter)` → `{verse: text}`
- `get_note / set_note / delete_note(book, chapter, verse[, text])`
- `get_patch_notes()` → `{version, notes[], show}` / `dismiss_patch(forever)`
- `get_initial` 추가 필드: `lex{ko,en}`, `is_premium`
- `check_update` 추가 필드: `mandatory`

## 5. 새 파일·저장 위치
- 코드: `bibleclip/userconfig.py`, `bibleclip/usage.py`, `bibleclip/notes.py`
- 데이터(런타임, gitignore): `userdata/config.json`(프리미엄), `userdata/user_notes.json`(노트)
- 배포 동봉: `version_changes.json`, `사용법.html`(그래픽 가이드)
- 새 settings 키: `seen_version`, `dismissed_patches`
- 새 killswitch 필드: `recommend_version`

## 6. 검증 상태
- ✅ `python -X utf8 tests/test_core.py` (콤마·//·원어 역검색·비즈니스 가드)
- ✅ `python -X utf8 tests/test_webui_api.py` (통합검색·노트 CRUD·패치 가드 등)
- ✅ `python -X utf8 tests/test_killswitch.py` · `node --check web/app.js` · NUL 0
- ⏳ 사용자 실창 테스트(특히 통합 검색바·묵상 노트 UI·분할 스크롤) 권장

## 7. 다음 차수 후보 (제안)
- 무료/프리미엄 정책 확정 + 결제/라이선스 백엔드 연동
- 한글 원어 뜻풀이를 PD(Strong's/BDB) 기반으로 자체 제작(권리 깨끗)
- 묵상 노트: 검색/목록 보기, 내보내기
- `사용법.txt`/`사용법.html` 신기능(통합검색·노트) 항목 보강
