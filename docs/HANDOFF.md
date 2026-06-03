# 🔄 최신 인수인계 및 세션 복구 가이드 (2026-06-03 업데이트)

- **현재 버전**: `v1.0.2` (GitHub 배포 및 태그 푸시 완료)
- **진행 상황**: 5차(카드별 ◀▶ 독립 히스토리·저장 디바운스), 6차(콤마 불연속 구절·한 줄 `//` 구분·활성 카드·절 단위 히스토리), 7차(잠금/활성 시각 분리·스크롤 500ms 디바운스) 작업 완료·실창 올패스. 상세는 `docs/WORK_LOG_카드시스템.md` §11~§13.
- **다음 목표**: 다음 차수 `TODO.md` 명세 수신 대기. (카드 시스템 작업 전 `WORK_LOG_카드시스템.md` 필독.)

---

## 🚀 새 세션 시작 시 Claude Code 행동 지침

새 터미널 세션이 열리고 `claude-code`가 구동되면, 가장 먼저 본 항목을 읽고 작업을 즉시 재개하십시오.

### 1. 컨텍스트 동기화
- 현재 프로젝트 루트의 `TODO.md`에 **5차 분할 명세서(Phase 1: 독립 히스토리 / Phase 2: 디바운스 최적화)**가 올바르게 반영되어 있는지 확인하십시오.
- **카드 시스템 관련 작업(이동/리사이즈/스냅/푸시/z-index/사전 라우팅/스크롤 동기화 등) 착수 전에는 반드시 `docs/WORK_LOG_카드시스템.md`를 먼저 읽으십시오.** 자유 배치 워크스페이스의 데이터 모델·핵심 함수(computePush/startMove/startResizeCard 등)·알고리즘·트레이드오프가 정리되어 있습니다. Phase 1(카드별 독립 히스토리)은 이 카드 객체 구조 위에 얹는 작업입니다.

### 1-1. 회귀 검증 명령어 (작업 전후 항상 실행)
```bash
python -X utf8 tests/test_webui_api.py          # 헤드리스 API 스모크 (전체 PASSED 확인)
node --check web/app.js                          # JS 문법 체크
python -c "print('NUL:', open('web/app.js','rb').read().count(b'\x00'))"   # NUL 0 확인
```
> ⚠️ `web/app.js` 편집 중 NUL 바이트가 혼입된 전례가 있습니다(`join(" ")`가 `join("\x00")`로 변질). 커밋·실행 전 NUL 점검은 필수입니다.

### 2. 개발 착수 프로토콜: Phase 1 우선 진행
클로드 코드의 과부하를 방지하기 위해 단계를 엄격히 격리합니다. 먼저 **Phase 1 (카드별 독립 탐색 히스토리)** 구현에만 집중하십시오.

- **대상 파일**: `web/app.js` (및 관련 UI 컴포넌트)
- **핵심 구현 요약**:
  - 개별 카드 객체(`card`) 내부에 `history: []` 배열 및 `historyIndex: -1` 상태 주입
  - 카드 상단 툴바 좌측 영역에 `◀ (뒤로 가기)`, `▶ (앞으로 가기)` 내비게이션 버튼 배치
  - 각 카드가 서로의 흐름을 간섭하지 않고 독립적으로 성경 구절 탐색 이력을 제어하도록 라우팅 연동

### 3. 작업 완료 후 출력 가이드
- Phase 1과 Phase 2가 각각 완료될 때마다, 변경 사항을 본사 기획팀(Gemini)에 동기화할 수 있도록 **오직 수정한 부분의 변경 코드 블록(`git diff`)만 터미널에 깨끗하게 출력**하십시오. (전체 파일 출력 절대 금지)

---

## 🚨 [영구 보존] 프로젝트의 핵심 유산 및 함정 경고 (Pitfalls)

> **주의**: 아래 규칙들은 과거 개발 과정에서 시스템이 파괴되거나 사용자 데이터가 날아갔던 고통스러운 교훈을 바탕으로 작성되었습니다. 코드를 리팩터링하거나 최적화할 때 아래 항목들을 절대 건드리지 마십시오.

### 1. 헤드리스 테스트 시 사용자 설정 파일(.json) 오염 금지
- **본질(영구 유효)**: 테스트·헤드리스 검증이 실제 사용자 설정 파일(`bibleclip_settings.json`)에 쓰기를 해서는 안 됩니다. 한 번 오염되면 창 크기·카드 레이아웃 등 사용자 데이터가 영구 파괴됩니다.
- **현재(웹/pywebview) 기준 수칙**: 헤드리스 API 테스트(`test_webui_api.py`)는 `Api`를 `webview` 없이 직접 생성해 검사하되, **`save_settings`/`set_*`처럼 디스크에 쓰는 경로는 반드시 스텁(stub)으로 막은 뒤** 호출하십시오. 위치 저장(`note_position`), 뷰어 역본 변경(`set_viewer_versions`) 등 영속 메서드를 실제로 부르는 테스트는 `lib.save_settings`를 no-op으로 바꿔 사용자 파일 오염을 차단합니다. (기존 테스트가 이 패턴을 따르고 있으니 새 테스트도 동일하게 작성할 것.)
- **레거시(CTk) 참고**: 과거 tkinter 앱에서는 창을 숨긴(`withdraw()`) 상태로 `_save_settings()`가 `root.geometry()`를 저장하면 `200x200` 같은 값이 기록되는 사고가 있었고, 그래서 렌더 검증 후 `save_settings` 없이 `os._exit(0)`로 즉시 탈출했습니다. CTk 코드(`bibleclip_app.py`+`bibleclip/ui/`)를 만질 때만 해당됩니다 — 현재 배포본인 웹 앱에는 위 "현재 기준 수칙"을 적용하십시오.

### 2. 레거시 'autobible' 흔적 제거 절대 금지 (하위 호환성)
- 이 앱의 전신인 `AutoBible` 및 단일 파일 시절의 레거시 호환용 코드는 무수정 유지가 원칙입니다.
- `config.LEGACY_SETTINGS_FILE = "autobible_settings.json"`(기존 사용자 설정 1회 승계 로직)과 CHANGELOG의 과거 기록, macOS 옛 번들 식별자는 **절대 제거하지 마십시오.** 제거 시 기존 장기 사용자의 마이그레이션 파이프라인이 끊어져 설정이 강제 초기화됩니다.

### 3. 시스템 핵심 파일명 및 데이터 경로 고정
- 아래 파일명과 디렉토리 구조는 PyInstaller 패키징 스크립트(`build_web.ps1`) 및 데이터 로딩 코어에 하드코딩되어 있으므로 임의로 이름을 바꾸거나 위치를 이동해서는 안 됩니다:
  - 설정 파일명: `bibleclip_settings.json` (gitignore 필수)
  - 진입점 파일명: `bibleclip_web.py`
  - 런타임 데이터 폴더: `bible_versions/`, `original_lang/` (루트 고정, 절대 이동 금지)
  - GitHub 저장소 명칭 및 설정 URL: `BibleClip` (`config.GITHUB_REPO="BibleClip"`)

### 4. 윈도우 콘솔 인코딩 및 CI 환경 의존성 (pyperclip)
- 윈도우 환경에서 파이썬 스크립트를 단독 실행하거나 테스트할 때는 한글 깨짐 방지를 위해 반드시 **`python -X utf8`** 플래그를 자석처럼 붙여서 실행하십시오.
- GitHub Actions CI 빌드 시 `requirements.txt`에 `pyperclip`이 누락되거나 frozen 빌드 옵션에서 `--hidden-import pyperclip`가 빠지면, 빌드된 독립 실행형 앱에서 클립보드 캡처 및 절 복사 기능이 **아무런 에러 로그 없이 조용하게 먹통**이 됩니다. 로컬 빌드 환경에 pyperclip이 깔려 있다고 해서 방심하지 말고 빌드 명세서를 항상 재확인하십시오.

---

## 🛠️ 운영 절차 (실행 · 빌드 · 릴리스)

### 앱 실행 / 검증
- **개발 실행**: `python bibleclip_web.py` (또는 `python -m bibleclip.webui`). 진입점은 `bibleclip_web.py`.
- **듀얼 모니터 주의**: pywebview 창이 보조 모니터에 뜰 수 있음(저장된 `web_geometry` 복원). "창이 안 보인다"는 정상일 수 있으니 모니터를 확인할 것.
- **프리즈 빌드(로컬)**: `packaging/build_web.ps1` 실행 → `dist_web/BibleClipWeb/BibleClipWeb.exe`. (`bible_versions/`·`original_lang/`·`icon.ico`를 exe 옆에 복사하는 것까지 스크립트가 처리.)

### 릴리스 절차 (버전 올릴 때 빠짐없이)
1. **작업용 브랜치에서 진행**, 단계마다 커밋.
2. **버전 단일 출처** `bibleclip/_version.py` 갱신 + **반드시 함께 갱신**:
   - `docs/CHANGELOG.md` (최신이 위)
   - **`사용법.txt`** (루트 — 이번 버전에서 바뀐 동작/UI 반영. 릴리스 zip에 자동 동봉됨)
   - `web/index.html`의 `#app-ver` 정적 폴백 값(런타임엔 `get_initial`이 덮어쓰지만 일관성용)
3. **헤드리스 검증 3종**(§1-1) 통과 확인.
4. `main`에 머지 → **푸시 전 반드시 `git pull --rebase origin main`** (아래 ⚠️ 참고) → `git push origin main`.
5. `git tag -a vX.Y.Z -m "..."` → `git push origin vX.Y.Z` → CI가 Win(zip)+Mac(zip/dmg) 빌드·릴리스. 자산명 `BibleClipWeb-*`.

### ⚠️ 푸시 전 rebase 필수 (원격 외부 커밋)
- **관리자(사용자)가 GitHub 웹에서 `killswitch.json`(원격 킬 스위치 매니페스트)을 직접 수정**하는 경우가 있습니다. 그러면 로컬에 없는 커밋이 원격 `main`에 생겨 `git push`가 거부됩니다.
- **절대 force push 하지 말 것** — killswitch 변경이 날아갑니다. 반드시 `git pull --rebase origin main`으로 내 커밋을 그 위에 얹은 뒤 푸시하십시오. (rebase 후 이미 만든 태그는 옛 커밋을 가리키므로 `git tag -d` 후 재생성.)

### CI 확인 (이 환경엔 `gh` CLI 없음 → GitHub REST API 폴링)
- 워크플로 실행: `https://api.github.com/repos/tpwns432-maker/BibleClip/actions/runs`
- 최신 릴리스/자산: `https://api.github.com/repos/tpwns432-maker/BibleClip/releases/latest`
- `curl -s <url> | python -c "..."`로 status/conclusion·assets를 파싱해 확인.

---

## 📌 알려진 미완료 / 다음 세션 주의

- **`사용법.txt`는 v1.0.2에서 카드 워크스페이스 기준으로 재작성 완료**(카드 추가/이동/리사이즈/스냅/잠금/◀▶ 히스토리/역본 칩/사전 연결/콤마·`//` 등 반영). `README.md`도 웹 UI 구조로 현행화함. 다음 릴리스 때도 동작/UI가 바뀌면 두 문서 동반 갱신 필요.
- **워킹트리 untracked 파일**: `TODO.md`(작업 명세서, AG Manager가 매 차수 덮어씀), `RELEASE_*.md`(일회성 릴리스 지시서)는 **의도적으로 커밋하지 않음**. git status에 떠도 정상. (커밋 대상은 소스 + `docs/` 문서 + `AGENTS.md`.)
- **협업 워크플로**는 `AGENTS.md` 참고 — AG Manager(기획·MD 명세) → IDE Agent → Claude Code(구현) 3단 구조. 작업 명세는 `TODO.md`로 내려오고, 변경 보고는 "수정한 diff만 출력"이 원칙(§3).