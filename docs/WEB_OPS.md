# 웹판 운영 기록 · 인수인계

> 마지막 갱신 2026-11-25 (main `a555778`, PR #29 까지 · 서버 버전 `v1.2.3-15-ga555778`).
> **웹판 일을 이어받으면 이 문서부터 읽는다.** 저장소가 공개라 서버 주소 · 접속 계정 같은 실제 값은 여기 쓰지 않고
> git 밖 **`_local/handoffs/WEB_SERVER_PRIVATE.md`**(이 PC 에만)에 둔다. 아래 `<서버주소>` · `<ssh계정>` 은 그 파일의 값.
> 새 서버 설치는 `docs/WEB_SETUP.md`(서버 주인용),
> 왜 이렇게 만들었는지는 `docs/WEB_PLAN.md` · `docs/TELEGRAM_PLAN.md`.

## 한눈에

| 항목 | 값 |
|---|---|
| 무엇 | 두 사람(개발자 · 서버 주인)만 쓰는 비공개 성경 + 커뮤니티 사이트 |
| 주소 | `https://<서버주소>` (Tailscale 사설망 — Tailscale 앱으로 로그인한 기기만 열림) |
| 서버 | 서버 주인 집의 리눅스. Ubuntu 22.04.5 · x86_64 · **Python 3.10** · Docker 없음 · 도메인 없음 · 시계는 UTC |
| 실행 | systemd 서비스 `bibleclip-web`(전용 사용자 `bibleclip`), 앱은 `127.0.0.1:8765` 에만 열리고 `tailscale serve` 가 https 로 넘김 |
| 프로그램 | `/opt/bibleclip` (GitHub `tpwns432-maker/BibleClip` 의 `main` 을 `git pull`) + `.venv` |
| 데이터 | `/var/lib/bibleclip` — 계정 · 사람별 설정/노트/형광펜 · `community.db` · `telegram.json` · 역본 · 원어 사전 |
| 설정 | `/etc/bibleclip/web.env` (`BIBLECLIP_PORT` · `BIBLECLIP_ARGS` = `--allow-host … --behind-proxy --secure-cookie`) |
| 텔레그램 봇 | 두 사람 다 연결됨(봇 이름은 비공개 파일). 열쇠(토큰)는 사이트에서 넣었고 `telegram.json`(권한 600)에만 있다 |
| 성경읽기 | 1년 1독 계획, 1일째 = **2026-11-25**. 알림 8 · 19 · 22시(한국 시간) |

## 배포 — 이 PC 에서 서버로

자동 업데이트는 **없다**(서버 주인이 원치 않음 — "태그만으로 관리자 권한 코드가 자동 실행되는 건 부담"). 만들지 말 것.

1. 브랜치 → PR → CI(`web` 검사: Ubuntu 22.04 · Python 3.10) 통과 → **사용자가 "병합/배포" 라고 말한 뒤** squash 병합.
2. 사용자에게 알릴 변경이면 **`bibleclip/server/web_changes.json` 맨 앞에 한 항목**(고유 `id` · `date` · `title` · `notes`).
   서버가 켜질 때 봇이 아직 안 알린 항목을 연결된 모두에게 보낸다(보낸 `id` 는 `telegram.json` 의 `announced`).
3. 배포:
   ```bash
   ssh <ssh계정>@<서버주소> 'sudo -n /opt/bibleclip/deploy/update.sh'
   ```
   `update.sh` = `git pull --ff-only` → `install.sh --update`(라이브러리 · 서비스 맞춤 → 다시 켜고 버전 확인).
4. 확인:
   ```bash
   ssh <ssh계정>@<서버주소> 'journalctl -u bibleclip-web --since "-2min" --no-pager | grep telegram'
   # → "봇 시작 — 열쇠 있음 … 연결 2명" · "보냄 패치 안내(<id>) → <아이디>" 두 줄
   ```

### 서버 접속 권한 (서버 주인이 정해 준 것)
- 계정 `<ssh계정>`, 이 PC 의 SSH 키 `~/.ssh/id_ed25519`(비밀번호 없는 키 — 사용자 선택).
- **비밀번호 없이 되는 관리자 명령은 두 개뿐**: `/opt/bibleclip/deploy/update.sh`, `systemctl restart bibleclip-web`.
- 그 밖의 `sudo` 는 그 계정의 비밀번호가 필요하다. **비밀번호는 대화창에 쓰지 않는다** — 사용자가 직접 입력하도록
  PowerShell 창을 띄운다:
  `Start-Process powershell -ArgumentList '-NoExit','-Command','ssh -t <ssh계정>@<서버주소> "sudo <명령>"'`
- `/var/lib/bibleclip` 은 이 계정이 그냥은 못 읽는다(서비스 사용자 전용). 데이터 확인도 sudo(비밀번호) 필요.

### 자주 쓰는 확인
```bash
ssh <ssh계정>@<서버주소> 'systemctl is-active bibleclip-web'
ssh <ssh계정>@<서버주소> 'journalctl -u bibleclip-web -n 50 --no-pager'
ssh <ssh계정>@<서버주소> 'sudo -n systemctl restart bibleclip-web'
```
- 알림이 안 왔다는 문의 → `journalctl … | grep telegram:` 의 `보냄 …` / `실패 …` 줄로 확인(#26).
- 앱 화면 파일(`/_web/*`)은 로그인해야 받을 수 있다(서버에서 curl 하면 401 이 정상).

## 새 서버를 만들 때

`docs/WEB_SETUP.md` 순서 그대로: `git clone` → `install.sh`(계정 만들기 포함) → 역본 · 원어 사전 넣기 → `tailscale.sh`
→ (선택) 텔레그램 열쇠 → 백업 예약. 옮기는 경우에는 그 전에 옛 서버에서
`sudo /opt/bibleclip/deploy/backup.sh --with-bibles` 로 데이터 전부를 받아 새 서버 `/var/lib/bibleclip` 에 풀고
`chown -R bibleclip:bibleclip` 한다(계정 · 글 · 봇 연결이 그대로 따라온다).

설치에서 실제로 겪은 것:
- **Python 3.10 문법만** — 이 PC(3.13)에서만 되는 문법(f-string 안 역슬래시 등)이 섞여 서버가 안 켜진 적이 있다(#21).
  그래서 PR 마다 `.github/workflows/web.yml` 이 22.04/3.10 에서 컴파일 · 테스트한다.
- `web.env` 는 `source` 하지 않고 `sed` 로 읽는다(값에 공백이 있으면 명령으로 실행됐다, #23).
- 설치 스크립트는 일회용 WSL(`wsl --install Ubuntu-24.04 --name bc-test` → 시험 → `wsl --unregister bc-test`)로
  시험한다. 사용자의 원래 Ubuntu 는 건드리지 않는다.
- 저작권 역본(개역개정 · 새번역 등)과 원어 사전 `HebGrkKo.dct` 는 **git 에 넣지 않는다.** 서버 주인이
  `/var/lib/bibleclip/bible_versions` · `original_lang/` 에 직접 넣는다.

## 지금까지 한 일

| PR | 내용 |
|---|---|
| #15 | 계획 문서(`WEB_PLAN.md`) |
| #16 · #17 | 1단계 브라우저에서 열기(`bridge.js`) · 2단계 로그인 + 사람별 데이터 |
| #18 · #19 | 3단계 홈 + 커뮤니티 · 4단계 성경 ↔ 커뮤니티 연결 · 어디서나 테마 |
| #20 | 5단계 리눅스 설치 포장(install/update/backup/tailscale.sh, systemd) · 비밀번호 바꾸기 |
| — | 2026-11-24 공개 저장소 히스토리에서 저작권 파일 6개 제거(filter-repo, **사용자가 직접** 강제 push) |
| #21 | Python 3.10 호환 + 3.10 CI |
| — | **2026-11-24 서버 설치 · 첫 배포**, 두 사람 로그인 · 비밀번호 변경 완료 |
| #22 | 휴대폰에서 안드로이드 앱 모양(`mobile.css` 를 서버가 끼움) |
| #23 | 설치 스크립트가 `web.env` 를 실행하지 않고 읽기 |
| #24 | 텔레그램 봇 — 새 글 · 댓글 알림, 아침 8시 · 저녁 7시 성경읽기 알림 |
| #25 | 내 이름 바꾸기 |
| #26 | 봇이 보낸 기록을 journalctl 에 남기기 |
| #27 | **성경읽기 체크**(커뮤니티 '성경읽기 체크' 글 = 그날 읽음) · 밤 10시 알림 · 패치 안내 |
| #28 · #29 | 아이폰 사파리(iOS 26) 떠 있는 주소창: 화면 높이를 실제 보이는 높이로(`--bc-vh`), 아래 메뉴 바탕을 화면 바닥까지(`--bc-under`) |
| #40 | 글 · 댓글에 쓴 구절("창 1:28")을 그 줄 아래 본문 카드로(`refs[].quote`, 글 하나 10개 · 인용 하나 30절까지) · 글쓰기 '📖 구절 달기' 칸(폰에서도 글 맨 위 구절) · 쓰는 중 알아본 구절 안내(`refs_preview`) |

### 아이폰 사파리 메모 (#28 · #29)
- iOS 26 사파리는 주소창이 화면 아래에 떠 있고 `100vh` · `100dvh` 가 그 뒤까지 잡는다. `env(safe-area-inset-bottom)`
  · `viewport-fit=cover` 는 이 주소창을 반영하지 않는다(WebKit bug 297779 등).
- 사파리는 `position:fixed; bottom:0` 을 주소창 **위**에 둔다 → `bridge.js` 가 보이지 않는 fixed 막대(top:0~bottom:0)
  높이를 재서 `--bc-vh` 로 앱 높이를 맞춘다. 사파리 26+ 아이폰(UA 의 `Version/26`)에서만 `html.ios-float` 를 달고,
  메뉴 바탕을 `100vh − 보이는 높이` 만큼 주소창 뒤로 늘린다(단추는 8px 내려 주소창 위 여백에).
- 진짜 아이폰 확인: #28 은 사용자가 확인(가리지 않음, 다만 떠 보임) → #29 배포. **#29 는 아이폰 확인 대기.**
  어색하면 `web.css` 의 `- 8px`(단추 내림)를 조정한다.

## 남은 일 · 확인할 것
- [ ] **#29 아이폰 확인** — 아래 메뉴가 화면 바닥에 붙어 보이는지(사용자 스크린샷).
- [ ] **GitHub 고객지원 요청(사용자 몫)** — 닫힌 PR #1~11 · #13~19 의 참조가 지운 저작권 파일이 든 옛 커밋
  (`db93ef7` · `f880a63`)을 붙잡고 있다. 지원팀에 그 참조 정리를 요청해야 완전히 사라진다.
- [ ] **자동 백업 예약 여부 확인** — `WEB_SETUP.md` 의 주 1회 `backup.sh` cron 을 서버 주인이 걸었는지 모른다
  (root crontab 이라 개발자 계정으론 못 본다). 서버 주인에게 물어볼 것.
- 안드로이드 앱의 원어 사전 불러오기 — 2026-11-25 사용자 판단으로 **하지 않음**.
- Draft PR #12(아이폰 앱 계획)는 따로 남아 있다(웹판과 무관).

## 규칙 (사용자와 정한 것)
- 병합 · 배포는 **사용자가 그때그때 말해야** 한다. 미리 받은 승인으로 다음 배포를 하지 않는다.
- 웹판을 배포할 때마다 `web_changes.json` 항목을 더한다. 용어는 '통독' 대신 **'성경읽기'**.
- `web/` 화면 파일과 안드로이드 `mobile.css` 는 데스크톱 · 앱과 함께 쓴다 → 웹 전용 동작은
  `bibleclip/server/static/bridge.js` · `web.css` 에만 넣는다(`web/locales` 문구 추가는 예외).
- 저작권 역본 · 서명 열쇠 · 비밀번호 · 봇 열쇠는 git · 대화창에 절대 넣지 않는다.
- 조직 규칙: 착수하면 Draft PR(`[WIP] …`, 본문 첫 줄 = 건드릴 파일) → 열린 PR 확인 → `main` 직접 push 금지 →
  커밋마다 `Task:` 트레일러.
- 화면에 `prefers-reduced-motion` 규칙을 넣지 않는다(사용자 PC 가 켜져 있어 움직임이 다 꺼진다).

## 시험하는 법 (이 PC)
```bash
python -X utf8 -m bibleclip.server.accounts --data <폴더> add tester --name 시험   # 계정 먼저
python -X utf8 -m bibleclip.server --data <폴더> --port 8771                     # http://127.0.0.1:8771
for t in test_server test_community test_telegram test_readingplan test_readingcheck; do python -X utf8 tests/$t.py; done
for t in tests/*.js; do node "$t"; done
```
- 휴대폰 화면은 헤드리스 크롬 + CDP(`Emulation.setDeviceMetricsOverride` mobile · 터치 켜기)로 본다.
- 로컬 서버에 텔레그램 봇을 연결하지 말 것(진짜 봇이 두 곳에서 돌게 된다). 실수했으면 그 데이터 폴더의
  `telegram.json` 을 지운다.
