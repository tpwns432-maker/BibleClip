# BibleClip 아이폰 계획

> 2026-11-04 초안. **본인 한 사람이 쓰는 앱**이다(배포하지 않음). 맥이 없으므로 빌드·시험은 모두
> GitHub의 맥 서버(Actions `macos` 러너)와 윈도우 PC, 실제 아이폰으로 한다. 저장소가 공개라 맥 러너 사용은 무료다.
> 작업은 단계마다 Draft PR → 브랜치 → squash 병합.

## 결정 사항
| 항목 | 결정 |
|---|---|
| 화면 | 안드로이드와 같다. `web/` + `mobile.css`/`mobile.js`를 WKWebView로 띄우고, `window.pywebview.api`와 같은 이름의 브리지를 Swift가 제공한다 |
| 핵심 로직 | Kotlin 코어(`android/.../core/`, 약 1,100줄)를 **Swift로 옮긴다**. 골든 테스트로 PC·안드로이드와 결과가 같은지 확인한다 |
| 최소 버전 | iOS 17 (사용자 기기: iPhone 17 Pro · iOS 27.2.1) |
| 설치 | 무료 Apple ID + 윈도우용 **Impactor**(오픈소스, MIT). 7일마다 다시 서명. 시험 앱으로 iOS 27.2.1 실기기 설치 확인(#44, 2026-11-25). 안 되면 개발자 등록($99/년) |
| 기본 역본 | 데스크톱과 같다. KRV·KJV+만 넣고, 나머지(NRKV 등)는 "파일" 앱에서 추가 |
| 프로젝트 파일 | XcodeGen의 `ios/project.yml`로 CI에서 `.xcodeproj`를 만든다. 맥이 없으니 Xcode 프로젝트 파일을 손으로 고치지 않는다 |

### Kotlin Multiplatform으로 코어를 같이 쓰지 않는 이유
Kotlin 코어는 `org.json`, `java.util.regex`, `java.time`, `java.util.zip`을 쓴다. iOS에서 돌리려면 이 넷을
모두 다른 라이브러리로 바꿔야 한다. 그러면 안드로이드까지 다시 시험해야 한다. 또 Kotlin/Native의 정규식은
JVM과 동작이 조금 달라, 오히려 골든 불일치가 생길 수 있다. 반면 Swift로 옮기는 일은 골든 테스트가 정답을 정해 주니
범위가 분명하다. 대신 **엔진을 고칠 때 Python·Kotlin·Swift 세 군데를 고친다**(순서는 아래 골든 테스트 참고).

## 구조
```
ios/
  project.yml              XcodeGen 설정 (앱 1개, 확장 없음)
  BibleClip/
    App.swift              앱 시작, WKWebView 화면
    Bridge.swift           web/ 의 api 호출 → 코어 (Bridge.kt 와 같은 메서드 이름)
    bridge.js              android/…/bridge.js 와 같고, window.webkit.messageHandlers 로 보냄
    Core/                  Kotlin core/ 를 파일 단위로 1:1 이식
      BibleDb  BibleImporter  Engine  Formatter  Library
      Search   Settings       Tables  TextUtils  UserData
  BibleClipCoreTests/      골든 테스트 (tests/golden/*.json 을 읽음)
.github/workflows/ios.yml  맥 러너: 골든 테스트 → 서명 안 된 .ipa 빌드
```
- `web/`, `android/…/assets/android/mobile.*`, `tests/golden/`, 기본 역본은 **복사하지 않고** 빌드할 때 앱 안으로 넣는다(안드로이드 `RepoAssets`와 같은 방식).
- 코어는 Swift 패키지로 따로 둔다. 그러면 화면 없이 `swift test`만으로 골든 테스트를 돌릴 수 있다.

## iOS에서 달라지는 것
| 기능 | 안드로이드 | 아이폰 |
|---|---|---|
| 글자 선택 → BibleClip | `PROCESS_TEXT` 메뉴 | 없음. 2단계에서 **단축어(App Intents)**로 대신한다. "요 3:16" 선택 → 공유 → 단축어 → 본문 복사. 확장 앱이 아니라서 무료 계정의 앱 3개 제한을 쓰지 않는다 |
| 클립보드 읽기 | 그냥 읽음 | 읽을 때마다 iOS가 "붙여넣기 허용"을 묻는다. 앱을 열 때 자동으로 읽지 않고 **[붙여넣기] 버튼**(`UIPasteControl`, 묻지 않음)을 둔다 |
| 성경 파일 추가 | 파일 선택 창 | 파일 선택 창(`UIDocumentPicker`)으로 "파일" 앱에서 고른다 |
| 데이터 위치 | 앱 내부 저장소 | 앱의 Documents 폴더. "파일" 앱 → 나의 iPhone → BibleClip에 보이게 한다. 노트·형광펜 JSON 백업과 옮기기가 쉬워진다 |
| 진동 | `CLOCK_TICK` | `UISelectionFeedbackGenerator` |
| 빠른 설정 타일 | 있음 | 없음 (제어 센터 위젯은 확장 앱이라 뺀다) |

## 맥 없이 시험하는 법
- **엔진**: CI의 `swift test`가 골든을 비교한다. 실패하면 어느 입력이 틀렸는지 로그에 나온다.
- **화면**: 2단계에서 Simulator 화면을 CI가 스크린샷으로 남긴다(주요 화면 몇 개).
- **실기기 디버깅**: WKWebView를 `isInspectable = true`(iOS 16.4+)로 둔다. 윈도우에서 `ios-webkit-debug-proxy`로 크롬 개발자 도구에 붙인다(지금의 CDP 시험과 비슷). 안 되면 화면 안에 오류 기록 창을 띄워 대신한다.

## 설치 (처음 한 번) — 2026-11-25 시험 앱(#44)으로 확인한 순서
1. PC: Microsoft Store판 **iTunes**(아이폰 드라이버). iTunes가 **켜져 있어야** 기기 서비스(usbmuxd)가 돈다.
2. PC: **Impactor 2.7.3 이상**(`winget install CLARATION.Impactor.GUI` 또는 github.com/claration/impactor 릴리스).
   2.7.2는 Apple 로그인에서 `HTTP 403 … GsService2`로 막힌다(헤더 소문자화 버그, impactor#318).
3. 아이폰: 설정 → 개인정보 보호 및 보안 → **개발자 모드** 켜기 → 재시동. 메뉴가 안 보이면 PC에서
   `pymobiledevice3 amfi reveal-developer-mode`로 꺼낸다.
4. Impactor에 `.ipa`를 끌어 놓고 Apple ID로 로그인 → Install. 옵션 체크는 모두 끈다. Identifier는 바꾸지 않는다.
5. 처음 열 때 "신뢰하지 않는 개발자" → 설정 → 일반 → VPN 및 기기 관리 → 내 Apple ID → 신뢰.
6. 7일마다 같은 방법으로 다시 설치한다(데이터는 남는다). Impactor의 Auto Refresh(베타)로 자동화할 수 있다.

무료 계정 제한: 동시에 앱 3개까지, 새 앱 ID는 7일에 10개까지. 번들 ID는 `com.bibleclip.app.sejun` 하나로 고정한다. 바꾸면 다른 앱이 되어 데이터가 따로 논다.

## 단계
| 단계 | 내용 | 끝 기준 |
|---|---|---|
| 0. 코어 이식 | Swift 패키지로 Kotlin core/ 이식, 골든 테스트, CI `swift test` | 골든 전부 통과 (Kotlin과 같은 수) |
| 1. 앱 골격 | XcodeGen 프로젝트, WKWebView + 브리지, 기본 역본 동봉, 서명 안 된 .ipa CI 빌드 | 아이폰에 설치 → 리더·검색(정렬·필터)·변환·노트·형광펜·장바구니가 안드로이드처럼 동작 |
| 2. 아이폰 기능 | 성경 파일 추가, [붙여넣기] 버튼, 진동, 단축어(App Intents), 안전 영역(노치·홈 막대) 여백 | 실기기에서 NRKV 추가, 단축어로 "요 3:16" 변환 |
| 3. 다듬기 | 다크모드, 한/영, 안드로이드 데이터 JSON 옮겨 오기 | 폰의 노트·형광펜이 아이폰에서 열림 |

## 버전·빌드
- 버전은 데스크톱·안드로이드와 같은 번호를 쓴다(`project.yml`의 `MARKETING_VERSION`).
- `ios-v<버전>` 태그 push → CI가 `.ipa`를 **prerelease**로 Release에 붙인다(`make_latest: false`). 데스크톱 업데이트 확인이 `releases/latest`를 보기 때문이다.
- 저작권 역본은 `.ipa`에 넣지 않는다(기존 규칙과 같음).

## 두 벌이 아니라 세 벌 — 골든 테스트
엔진을 고칠 때 순서: Python 수정 → `python tests/make_golden.py` → Kotlin·Swift 테스트가 깨지면 같은 수정을 각각 옮긴다.
CI에서 안드로이드와 아이폰이 모두 같은 `tests/golden/*.json`을 본다.

## 데스크톱에서 빼는 것
안드로이드와 같다. 클립보드 감시, 자막·PPT 창, F11 전체화면, 자동 업데이트, 글꼴 설치, 원어 사전(38MB)은 뺀다.

## 위험 — 설치 도구의 iOS 27 지원 (해결, 2026-11-25)
AltStore의 iOS 27 지원이 불확실해서, 1단계 전에 빈 시험 앱을 CI로 만들어 실제 아이폰에 설치해 보았다(#44).
**Impactor 2.7.3 + 무료 Apple ID로 iOS 27.2.1에 설치되고, WKWebView ↔ Swift 브리지도 동작했다.** 그래서 AltStore 대신 Impactor로 간다.
Apple이 이런 도구의 로그인을 다시 막으면(2026-11 다른 도구들이 GSA 503을 겪음) Impactor 새 버전을 기다리거나 개발자 등록($99/년)으로 간다.
