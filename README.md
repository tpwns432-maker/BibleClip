# BibleClip

클립보드의 성경 구절(예: `창 2:1`)을 자동으로 인식해 설정한 형식으로 변환·복사해 주는
한국어 데스크톱 앱입니다. 자유 배치 카드 워크스페이스(본문/원어/사전), 여러 역본 병렬
보기, 히브리어/헬라어 원어·사전, 키워드 검색, GitHub 기반 자동 업데이트를 지원합니다.

> 이 프로젝트는 이전 `AutoBible` 저장소에서 **`BibleClip`** 으로 이전했습니다.
> 현재 배포본은 **pywebview 기반 웹 UI**(`bibleclip_web.py` + `web/`)입니다. 과거
> CustomTkinter UI(`bibleclip_app.py` + `bibleclip/ui/`)는 빌드/배포하지 않지만
> 하위 호환을 위해 소스에 남아 있습니다.

## 실행 (개발)

```bash
python bibleclip_web.py
# 또는
python -m bibleclip.webui
```

Python 3.9+ 와 `pywebview` 가 필요합니다(Windows는 WebView2가 OS에 기본 내장,
macOS는 내장 WKWebView 사용). 클립보드 입출력에 `pyperclip`, 자동 업데이트 SSL
검증에 `certifi` 를 사용합니다. (`requirements.txt` 참고.)

## 프로젝트 구조

```
bibleclip_web.py        웹 앱 진입점 → bibleclip.webui
bibleclip/              애플리케이션 패키지
├─ _version.py          버전 단일 출처(ASCII 전용)
├─ config.py            플랫폼·폰트·경로·GitHub URL
├─ constants.py         자모/책이름 매핑
├─ text_utils.py        한글 조립·정제·검색 trigram
├─ update.py            릴리스 체크·플랫폼 자산 선택
├─ data/                bible_db.py · original_lang.py
├─ core/                library.py(비-UI 코어) · engine.py(파서) · formatter.py
│                       · clipboard_monitor.py · installer.py
├─ webui/               api.py(JS-facing 브리지, pywebview 비의존) + 진입 모듈
└─ ui/                  (레거시 CustomTkinter — 미배포, 하위호환 보존)

web/                    프론트엔드 (배포 UI)
├─ index.html / app.js  레이아웃 + 전체 로직(CardManager 포함)
├─ css/                 tokens.css · styles.css · fonts.css
└─ fonts/               Pretendard 번들

bible_versions/         성경 SQLite DB (런타임 데이터, 루트 고정)
original_lang/          원어/사전 데이터 (런타임 데이터, 루트 고정)
icon.ico / icon.png     앱 아이콘
사용법.txt              사용자 매뉴얼 (릴리스 zip에 동봉)
packaging/              build_web.ps1(Win 프리즈) · build_mac.sh
tests/                  헤드리스 테스트(test_core · test_webui_api 등)
docs/                   CHANGELOG · HANDOFF · 작업 로그 · BUILD_MAC
.github/workflows/      태그 푸시 시 Windows/macOS 자동 빌드·릴리스
```

`bibleclip/webui/api.py` 의 `Api` 는 pywebview 없이도 생성·검사할 수 있어
헤드리스 테스트가 가능합니다(`tests/test_webui_api.py`).

## 빌드 / 릴리스

- **자동(권장):** `v*` 태그를 push 하면 GitHub Actions가 Windows `.exe`(zip)와
  macOS `.app`(zip + dmg)을 빌드해 릴리스에 첨부합니다.
- **macOS 로컬:** `packaging/build_mac.sh` (자세한 내용은 `docs/BUILD_MAC.md`).

버전은 `bibleclip/_version.py` 한 곳에서 관리합니다. 변경 시 `docs/CHANGELOG.md` 도
함께 갱신하세요.

## 사용자 데이터

- 설정 파일: `bibleclip_settings.json` (예전 `autobible_settings.json` 은 최초 실행 시
  자동 승계됩니다).
- 성경/원어 데이터는 실행 파일 옆 또는 macOS `.app` 번들 안에서 로드됩니다.
