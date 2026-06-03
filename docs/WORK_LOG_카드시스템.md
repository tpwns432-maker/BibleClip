# BibleClip — 자유 배치 카드 시스템 작업 내역 (2026-06-03)

> 이 문서는 Claude Code(CC) 세션에서 진행한 작업을 다른 AI 세션/검증자와 공유하기 위한 작업 로그입니다.
> 사용자 피드백 검증 시 이 문서를 컨텍스트로 사용하세요.
> **최신 업데이트: 4차 작업 완료 (문서 하단 §10 참고). 3차 전 항목 사용자 테스트 통과.**

---

## 1. 프로젝트 배경

- **BibleClip**: 클립보드의 성경 구절(예: `창 2:1`)을 자동 인식·변환·복사하는 한국어 데스크톱 앱
- 기술 스택: Python + **pywebview** (WebView2) + 순수 HTML/CSS/JS 프론트엔드
- 저장소: `tpwns432-maker/BibleClip`, 현재 v1.0.0 (AutoBible에서 이전한 신규 저장소)
- 주요 파일:
  - `web/app.js` — 프론트엔드 전체 로직 (CardManager 포함)
  - `web/index.html` — 앱 레이아웃
  - `web/css/styles.css` — 스타일
  - `bibleclip/webui/api.py` — Python 백엔드 브리지 (JS에서 `pywebview.api.*`로 호출)
  - `bibleclip/core/library.py` — 비-UI 코어 로직

## 2. 이번 작업의 목표 (사용자와 합의된 스펙)

기존의 "고정 3분할 패널(본문/원어/사전)"을 **모듈형 카드 워크스페이스**로 전환하는 작업의 연속.
이전 단계에서 카드 추가/제거/가로 일렬 배치까지 구현했고, 이번 세션에서 아래를 구현함.

### 2-1. 자유 배치 + Attach(스냅) 카드 시스템 ("그리드" 아이디어는 폐기됨)

사용자가 명시적으로 결정한 사항:

| 항목 | 결정 내용 |
|---|---|
| 배치 방식 | **자유 배치** (PowerPoint 도형처럼 아무 위치에나 놓을 수 있음) |
| 스냅(Attach) | 이동/리사이즈 시 다른 카드 가장자리·작업영역 경계에 **착 달라붙음** + 정렬 가이드라인 표시 |
| 리사이즈 | 각 카드가 **독립적으로** 크기 조절 (카드 사이 공유 경계선/스플리터 개념 **없음**) |
| 푸시(밀림) | 카드 1을 키워서 붙어있는 카드 2와 만나면 → **카드 2는 크기를 유지한 채 밀려남** (작아지는 것이 아님) |
| 겹침 | **허용**. 클릭/드래그한 카드가 맨 위로 (z-order) |
| 카드 추가/제거 시 | 다른 카드들은 **자리 유지** (일반 윈도우처럼). 재배치는 유저 몫 |
| 새 카드 생성 위치 | **작업영역 정중앙 + 맨 위에** (연속 추가 시 계단식 오프셋) |
| 작업영역 스크롤 | **없음**. 스크롤은 오직 카드 내부 콘텐츠만 |
| 윈도우 리사이즈 | 카드는 비례 스케일링 (% 좌표), **폰트는 px 고정** |
| 카드 추가 버튼 | 상단 컨트롤바 우측에 `＋ 본문` / `＋ 원어` / `＋ 사전` 3개 |

### 2-2. 원어 스크롤 실시간 동기화

- "동기화"의 의미: 같은 장을 띄우는 것이 **아니라**, **스크롤 위치의 실시간 동기화**
- 기준: 본문 카드에서 **"처음부터 끝까지 온전히 보이는 최상단 절"**
  - 예: 레위기 1:4가 위가 잘려 일부만 보이고 1:5부터 온전히 보이면 → 원어 카드 최상단에 **1:5** 정렬
- 방향: 본문 → 원어 (단방향), rAF 스로틀

### 2-3. 역본 칩 드래그 순서 변경 (라이브 애니메이션)

- 칩을 드래그하는 **도중에** 다른 칩들이 실시간으로 밀려나며 자리를 비켜주는 애니메이션
- (놓을 때만 애니메이션 되는 것이 아님 — 사용자가 명시적으로 강조한 사항)
- 첫 번째 칩 = 기본(primary) 역본. 순서 변경 시 모든 성경 카드 재렌더

### 2-4. 다역본 병렬 보기 (이전 세션에서 구현, 유지됨)

- 상단의 **전역 역본 칩**이 모든 성경 본문 카드에 적용됨
- 여러 역본 선택 시 각 절마다 역본별 줄(`.vline` + 역본 배지)로 병렬 표시

### 2-5. 클립보드 라우팅 (이전 세션에서 구현, 유지됨)

- 클립보드 구절 수신 시 **단 하나의 카드만** 반응:
  1. **1순위**: 잠금(락)된 카드 중 현재 책/장이 수신 구절과 일치하는 카드 (제자리에서 절 하이라이트)
  2. **2순위**: 첫 번째 잠금 안 된 카드 (해당 위치로 이동)
- 락 = "조건부 수신": 완전 차단이 아니라, 자기 책/장과 일치하면 수신함

## 3. 구현 상세

### 3-1. 데이터 모델 (`web_cards_layout`에 저장)

```js
// 각 카드 디스크립터:
{
  id: "bible-1",            // bible-N / inter-N / lex-N
  type: "bible" | "interlinear" | "lexicon",
  x: 0, y: 0,               // 위치 (작업영역의 %)
  w: 34, h: 100,            // 크기 (작업영역의 %)
  z: 1,                     // 쌓임 순서 (클릭 시 ++zTop)
  // bible 전용:
  version, book, chapter, locked,
  // interlinear/lexicon 전용:
  link: "bible-1",          // 연결된 성경 카드 id
}
```

- 백엔드 저장: `api.save_cards_layout(layout)` → `settings['web_cards_layout']` (자유 형식 JSON, 서버측 검증 없음)
- 디바운스 400ms로 자동 저장

### 3-2. CardManager 핵심 함수 (web/app.js)

| 함수 | 역할 |
|---|---|
| `defaultLayout()` | 첫 실행: 본문(34%) \| 원어(33%) \| 사전(33%) 가로로 붙여서 전체 높이 |
| `restore(layout)` | 저장된 레이아웃 복원 + 검증 (구버전 형식이면 기본 배치로 폴백) |
| `startMove(card, sec, e)` | 헤더 드래그 이동 + 스냅 + 가이드라인 |
| `startResizeCard(card, sec, dirs, e)` | 8방향 리사이즈 + 스냅 + **푸시 체인** |
| `collectChain(card, dir, chain)` | 특정 방향으로 붙어있는(attach) 카드 체인 수집 (재귀) |
| `bringToFront(card)` | z-order 최상위로 |
| `syncInterlinFrom(card, body)` | 본문 → 원어 스크롤 동기화 |
| `goToRef(book, chapter, verses)` | 클립보드 라우팅 (단일 카드 반응) |
| `addCard(type)` | 중앙 생성 + 계단식 오프셋 |

### 3-3. 주요 상수

```js
const MIN_W = 12, MIN_H = 15;   // 카드 최소 크기 (%)
const SNAP_PX = 8;              // 스냅 임계값 (px)
const ATTACH_EPS = 0.6;         // 이 거리(%) 이내면 "붙어있음"으로 판정
const MAX_BIBLE = 4;            // 성경 카드 최대 개수
```

### 3-4. 푸시 알고리즘

1. 리사이즈 시작 시 모든 카드의 원본 좌표 스냅샷
2. 활성 방향(예: 동쪽)으로 붙어있는 카드 체인을 재귀 수집
3. 매 프레임: 전체를 원본으로 리셋 → 델타 계산 → 스냅 → 체인의 가장 끝 카드가 작업영역 경계에 닿으면 델타 클램프 → 체인 전체를 델타만큼 이동
4. 리사이즈하는 카드 자신은 MIN_W/MIN_H 아래로 줄어들지 않음

### 3-5. 칩 드래그 라이브 갭

1. dragstart: 모든 칩의 원본 위치/너비 스냅샷
2. dragover: 마우스 X로 삽입 인덱스 계산 → **모든 칩**(드래그 중인 반투명 칩 포함)을 "놓았을 때의 위치"로 translateX (CSS transition .18s)
3. drop: FLIP 방식으로 재렌더 (화면 위치 그대로 안착, 점프 없음) → `api.set_viewer_order()` 저장 → 성경 카드 재렌더

### 3-6. 변경된 파일

| 파일 | 변경 내용 |
|---|---|
| `web/app.js` | CardManager 전면 재작성 (자유 배치), 칩 드래그, 스크롤 동기화, 카드 추가 버튼 배선 |
| `web/index.html` | 컨트롤바: 역본 칩 + `＋` / 우측에 `＋ 본문`·`＋ 원어`·`＋ 사전` 버튼 |
| `web/css/styles.css` | `.panels-container` (relative, overflow hidden), `.mcard` (absolute), `.rs` 8방향 핸들, `.snap-guide`, 칩 transition |
| `bibleclip/webui/api.py` | (이전 세션) `web_cards_layout` 설정키 + `save_cards_layout()` |
| `bibleclip/core/library.py` | (이전 세션) `DEFAULT_SETTINGS`에 `web_cards_layout: None` |
| `tests/test_webui_api.py` | (이전 세션) `web_cards_layout` 테스트 |

## 4. 검증 상태

- ✅ `python -X utf8 tests/test_webui_api.py` 전체 통과
- ✅ `node --check web/app.js` 문법 OK
- ✅ NUL 바이트 0
- ⏳ 사용자 실창 테스트 진행 중 (이 문서 작성 시점)

## 5. 알려진 설계 트레이드오프 / 잠재적 이슈 (검증자 참고)

피드백 검증 시 아래 사항을 염두에 두세요:

1. **푸시는 리사이즈에만 적용**: 카드를 "이동"할 때는 푸시 없음 (스냅+겹침만). 이동 중 푸시는 미구현.
2. **붙어있음(attach) 판정**: 가장자리 거리 0.6% 이내 + 교차축 겹침. 스냅으로 붙인 카드는 정확히 0이므로 확실히 붙음. 손으로 어중간하게 놓으면 안 붙은 것으로 판정될 수 있음.
3. **줄어들 때는 안 따라옴**: 카드 1을 줄이면 붙어있던 카드 2는 따라오지 않음 (밀기만 있고 당기기는 없음 — PowerPoint와 동일).
4. **스냅 대상**: 다른 카드의 상하좌우 가장자리 + 작업영역 경계. 중심선(center) 스냅은 미구현.
5. **카드 본문 클릭 시에도 z-order 상승**: 절 복사를 위해 본문을 클릭해도 카드가 맨 위로 올라옴 (의도된 동작이지만 거슬릴 수 있음).
6. **원어 동기화는 단방향**: 원어를 스크롤해도 본문은 안 따라감.
7. **최소 카드 크기**: 너비 12%, 높이 15%. 이보다 작게 줄일 수 없음.
8. **윈도우 리사이즈 시**: % 기반이므로 카드가 자동 스케일링되지만, 카드가 작아지면 내부 콘텐츠(고정 px 폰트)가 넘쳐서 스크롤이 생길 수 있음 (정상 동작).
9. **이전 레이아웃 호환**: 이전 세션에서 저장된 레이아웃(x/y/w/h 없는 형식)은 무시되고 기본 배치로 초기화됨.

## 6. 테스트 체크리스트 (사용자 피드백 항목과 대조용)

- [x] 카드 헤더 드래그로 이동 → 스냅 + 가이드라인 (1차 통과)
- [x] 8방향 리사이즈 (가장자리 4 + 모서리 4) (1차 통과)
- [x] 붙은 카드 방향으로 키울 때 푸시(밀림) (1차 통과)
- [x] 겹침 + 클릭 시 맨 위로 (1차 통과)
- [x] `＋ 본문/원어/사전` 버튼 → 중앙 생성 (1차 통과)
- [x] 역본 칩 드래그 중 라이브 밀림 애니메이션 (1차 통과)
- [x] 본문 스크롤 → 원어 카드 실시간 동기 (1차 통과)
- [x] 클립보드 수신 → 한 카드만 반응 (이전 검증 통과)

---

## 7. 2차 피드백 작업 (완료)

| # | 항목 | 구현 내용 |
|---|---|---|
| 1 | 스냅 거터 | `GUTTER` 상수 도입 — 카드↔카드 스냅 시 간격 유지, 경계는 밀착 |
| 2 | 동적 푸시 체인 | 리사이즈 중 밀리던 카드가 떨어진 카드와 만나면 체인 합류 (→ 3차에서 버그 수정) |
| 3 | 칩 ✕ 커서 | `.pill.sel .x { cursor: pointer }` — 칩 본체 grab, ✕는 pointer (사용자 통과) |
| 4 | 사전 link 라우팅 | `lexCurMap` (bible별 사전 상태). 원어 카드 클릭 → 같은 bible에 link된 사전 카드만 갱신. 없으면 그 bible에 link된 새 사전 카드 생성. 교차참조는 자기 카드만 (사용자 통과) |

## 8. 3차 피드백 작업 (완료 — 최신)

| # | 항목 | 구현 내용 |
|---|---|---|
| 1 | 거터 1/3 축소 | `GUTTER` 1.0% → **0.33%**, `ATTACH_EPS` 0.6 → 0.2 |
| 2 | **푸시 체인 joinAt 재설계** (핵심 버그 수정) | 기존 expandPush(grow를 접촉거리로 영구 클램프 + 합류 카드가 grow 전체만큼 점프) 폐기. 새 `computePush(dir, rawGrow, card, orig)`: 체인 멤버마다 **joinAt**(접촉에 필요한 grow) 기록 → 이동량 = `max(0, grow - joinAt)`, 경계 클램프 = `min(joinAt_i + 여유공간_i)`. 4방향 공통 일반화 (lead/trail/gap/space 헬퍼) |
| 3 | 작업영역 분할 가이드 스냅 | `DIV_X = [25, 33.3, 50, 66.7, 75]`, `DIV_Y = [33.3, 50, 66.7]`. 이동/리사이즈 스냅 타깃에 추가(밀착). 카드 간 스냅이 타이 우선(타깃 배열에서 카드 먼저 + strict `<`). 분할선 가이드는 **점선** 스타일(`.snap-guide.div`) |

### 3차 작업 2의 알고리즘 상세 (검증자 참고)

```
computePush(dir, rawGrow, card, orig):
  1. 반복 탐색: 체인 밖 카드 c에 대해, 모든 mover(리사이즈 카드 joinAt=0 + 체인 멤버)로부터
     contact_c = mover.joinAt + max(0, gap(mover→c) - GUTTER) 계산.
     min(contact_c) < rawGrow 이면 c를 체인에 합류 (joinAt_c = min contact). 안정될 때까지 반복.
  2. 경계 클램프: grow = min(rawGrow, 자기여유, min_i(joinAt_i + 여유_i))
  3. 이동량: disp_i = max(0, grow - joinAt_i)  → Map 반환
적용부: disp.forEach((d, c) => c.x = orig.x ± d)  (방향별 부호)
```

- 증상 A 해소: grow가 접촉거리로 클램프되지 않으므로 접촉 후에도 계속 키울 수 있음
- 증상 B-1 해소: 합류 카드는 `grow - joinAt`만큼만 이동 → 점프 없음
- 증상 B-2 해소: 경계 클램프가 `joinAt_i + 여유_i` 기준 → 합류 카드의 작은 여유공간으로 grow가 붕괴하지 않음

### 3차 작업 후 변경된 상수/함수 위치 (web/app.js)

- 상수: `MIN_W/MIN_H/SNAP_PX/GUTTER/ATTACH_EPS/DIV_X/DIV_Y` — CardManager 최상단
- `computePush()` — 구 collectChain/collectChainOrig/expandPush 자리 (모두 삭제됨)
- `snapTo()` — `{at, kind}` 객체 타깃 지원 (kind="div" → 점선 가이드)
- `startMove()` / `startResizeCard()` — 타깃 배열 순서: 카드 → 경계 → 분할선

## 9. 3차 테스트 체크리스트 — ✅ 전 항목 사용자 통과 (2026-06-03)

- [x] 스냅된 카드 사이 간격이 기존의 약 1/3로 보임 (거터 축소 확인)
- [x] **A**: 떨어진 카드를 향해 키우면 접촉 지점에서 스냅, 계속 키우면 밀림. 크기 되돌아감 없음
- [x] **B-1**: `1|2 ... 3`에서 2가 3에 닿으면 3이 점프 없이 그 지점부터 함께 밀림
- [x] **B-2**: 3이 경계에 닿으면 전체 푸시 멈춤. 1·2 되돌아감 없음
- [x] 카드 가장자리를 작업영역 중앙(50%)·1/3 지점에 스냅 가능 + 점선 가이드 표시
- [x] 분할선 스냅이 카드 간 스냅을 방해하지 않음

## 10. 4차 피드백 작업 (완료 — 최신)

### 작업 4 — 역본 드롭다운이 카드에 가려지는 z-index 버그

**루트 원인**: 카드 클릭 시마다 `bringToFront()`가 `card.z = ++zTop`으로 z-index를 무한 증가시킴.
드롭다운 `.menu`는 `z-index: 100` 고정 → 카드를 100번 이상 클릭/조작하면 카드 z가 메뉴를 추월해
드롭다운(역본/책/장 선택)이 카드 뒤에 가려짐. 스냅 가이드(z:80)·드로어(z:90)도 같은 위험.

**수정 내용 (근본 해결 + 안전벨트 이중 방어)**:

| 구분 | 파일 | 내용 |
|---|---|---|
| 근본 ① | `web/app.js` `bringToFront()` | `zTop > 50`이 되면 모든 카드의 z를 쌓임 순서 보존하며 **1..n으로 정규화** → 카드 z는 영원히 ~50 이하 유지 |
| 근본 ② | `web/app.js` `restore()` | 저장된 레이아웃 복원 시에도 z를 1..n으로 정규화 (과거에 저장된 큰 z값 정리) |
| 안전벨트 ③ | `web/css/styles.css` `.menu` | `z-index: 100` → **1000** |
| 안전벨트 ④ | `web/css/styles.css` `.snap-guide` | `z-index: 80` → **500** (카드 위, 메뉴 아래) |

**레이어 구조 (최종)**:
```
카드(.mcard)        z ≤ ~50  (정규화로 상한 보장)
스냅 가이드          z = 500
클립보드 드로어      z = 90   (카드보다 위 — 정규화로 보장됨)
드롭다운 메뉴(.menu) z = 1000
토스트/사전팁/모달/툴팁  z = 200~400 (카드보다 위 — 정규화로 보장됨)
```

### 4차 테스트 체크리스트

- [ ] 어떤 카드에서든 역본/책/장 드롭다운을 펼쳤을 때 다른 카드에 가려지지 않음
- [ ] 카드를 수십 번 클릭한 뒤에도 드롭다운·스냅 가이드·드로어가 정상적으로 카드 위에 표시됨

---

## 11. 5차 피드백 작업 (완료 — 최신, v1.0.2 대상)

> TODO.md 5차 명세 기준. Phase 1·2를 격리 구현. 변경 파일: `web/app.js`, `web/css/styles.css`.

### Phase 1 — 카드별 독립 탐색 히스토리 (◀ ▶ 뒤로/앞으로)

각 **성경 카드**가 자신이 방문한 `{book, chapter}` 참조를 독립적으로 기억해, 헤더의 ◀ ▶ 버튼으로
**다른 카드에 영향 없이** 그 카드만 이전/다음 구절로 이동한다. 히스토리는 **세션 한정**(serialize에
미포함 — 영속 저장 안 함)이며 카드 생성/복원 시 현재 참조로 시드된다.

| 구분 | 내용 |
|---|---|
| 데이터 | `card.history: [{book, chapter}, …]`, `card.historyIndex` (성경 카드 전용) |
| 시드 | `seedHistory(card)` — `init`(restore 후 forEach) + `addCard`(bible) 에서 호출 |
| 기록 | `recordHistory(card)` — 사용자 내비게이션 후 호출. 현재와 동일하면 no-op, 분기 시 forward 엔트리 절단(splice) 후 push |
| 이동 | `cardHistoryNav(card, ±1)` — 히스토리에서 참조를 꺼내 적용(기록 안 함). 바운드 가드 |
| 버튼 | `updateNavButtons(card)` — 양 끝에서 `.disabled` 토글. `loadBibleCard` 끝/기록/이동 시 갱신 |
| UI | `headerHTML` bible 분기에 `◀`(`data-act="back"`)·`▶`(`data-act="forward"`) `.hd-mini.hd-nav` 추가. 좌측(제목 뒤) 배치 |
| 배선 | `handleAction`에 `back`/`forward` case. `recordHistory` 삽입처: 책 선택, 장 선택, `cardChapStep`(이전/다음 장), `goToRef`(잠금 아닌 타깃이 이동했을 때만) |

- **CSS**: `.card-hd .hd-mini.hd-nav { font-size: 9px }`, `.card-hd .hd-mini.disabled { opacity:.32; cursor:default }` (+ hover 무효화)
- **설계 메모**: 잠금 카드가 제자리 반응(book/chapter 불변)하면 `recordHistory`가 no-op이므로 안전. 비활성 버튼은 `pointer-events`를 유지 → 클릭은 바운드 가드로 no-op, 동시에 `.hd-mini` 히트가 헤더 드래그(이동) 오발동을 막음.

### Phase 2 — 디바운스 기반 레이아웃 자동 저장 최적화

기존 `saveLayout()`은 이미 400ms 디바운스였고 드래그/리사이즈 **도중에는 호출되지 않으며**(매 프레임은
`applyGeom`만 — 스토리지 I/O 없음) `onUp`에서만 저장했다. 유일한 누수는 제스처 시작 시 `bringToFront()`가
부르는 `saveLayout` 1회였다(긴 드래그면 도중 1회 기록 가능). 이를 막아 **제스처당 정확히 1회** 저장으로 정리.

| 구분 | 내용 |
|---|---|
| 디바운스 | 400ms → **300ms** (`SAVE_DEBOUNCE_MS` 상수화) |
| 제스처 중 쓰기 차단 | `interacting` 플래그. `startMove`/`startResizeCard` 시작에서 `true`, 각 `onUp`에서 `false`. `saveLayout()`은 `interacting`이면 즉시 return(스케줄 안 함) → 드래그 프레임은 100% 렌더에만 사용 |
| 저장 로그 | 디바운스 콜백에서 `console.log("[BibleClip] 레이아웃 저장 완료")` — 손 뗀 뒤 300ms에 1번만 출력(검증용) |

### 5차 테스트 체크리스트

- [ ] 카드별 ◀ ▶ 가 서로 독립적으로 동작(한 카드 뒤로가기가 다른 카드에 영향 없음)
- [ ] 히스토리 양 끝에서 버튼 비활성(흐려짐)
- [ ] 책/장 변경·이전/다음 장·클립보드 이동 모두 히스토리에 기록됨
- [ ] 드래그/리사이즈 중 렉 없이 부드러움, 손 뗀 뒤 300ms에 "레이아웃 저장 완료" 1번만 콘솔 출력

### 5차 검증 상태

- ✅ `node --check web/app.js` 문법 OK · NUL 0
- ✅ `python -X utf8 tests/test_webui_api.py` 전체 통과
- ⏳ 사용자 실창 테스트 대기

---

## 12. 6차 피드백 작업 (완료 — 최신, v1.0.2 대상)

> TODO.md 6차 명세 기준. Phase 1(엔진/포맷), Phase 2(활성 카드·절 단위 히스토리)로 격리.
> 변경 파일: `bibleclip/core/formatter.py`, `web/app.js`, `web/css/styles.css`, `web/css/tokens.css`, `tests/test_core.py`.

### Phase 1 — 불연속 구절 콤마 파싱 & 한 줄 출력 ` // ` 구분

| # | 항목 | 구현 |
|---|---|---|
| 작업 1 | 콤마 파싱 | **이미 구현되어 있었음**. `engine.py`의 `VERSE_PATTERN`/`KOREAN_STYLE_PATTERN` 정규식이 `(?:[,，]\d+(?:[-~]\d+)?)*`로 콤마 그룹을 포착하고 `parse_verses`가 `re.split(r'[,，]')` 후 합집합·정렬. `요 1:1-2,4-6` → `[1,2,4,5,6]` 검증 완료. **코드 변경 없음**(회귀 테스트만 추가) |
| 작업 2 | 한 줄 ` // ` | **`formatter.py`** `format_version_output`의 inline 분기 수정(명세는 library.py로 안내했으나 실제 절 결합부는 Formatter임). `all_verse_data`를 순회하며 `v_num != prev_v + 1`(불연속=콤마 경계)일 때만 ` // ` 삽입, 연속 절은 공백. 결과: `요 1:1-2,4` → `[1절] [2절] // [4절]` |

- **설계 메모**: `parse_verses`가 콤마 그룹 정보를 평탄화(set)하므로 그룹 경계는 보존되지 않음 → 출력 시 **절 번호 불연속(gap) 감지**로 ` // ` 위치를 복원(= 콤마 경계와 동치). `newline`(여러 줄) 모드는 미변경.

### Phase 2 — 활성 카드 시스템 & 절 단위 히스토리 복원

| # | 항목 | 구현 (web/app.js) |
|---|---|---|
| 작업 3 | 활성 카드 네온 | `activeId` 상태 + `setActive(card)`(다른 카드 `.active` 해제 후 대상에 주입). `bringToFront` 최상단에서 호출(z 불변이어도 포커스 갱신). `renderAll` 후 `.active` 재적용. CSS `.mcard.active { border-color:accent; box-shadow: 0 0 0 1px accent, 0 0 10px var(--accent-blur) }` (`tokens.css`에 `--accent-blur` 추가). `.moving`/`.locked` 뒤에 배치해 드래그 중에도 네온 유지 |
| 작업 4 | 키보드 ←/→ 활성 타겟 | `activeBibleCard()`(active가 성경 카드면 그것, 아니면 `primaryBible` 폴백) + `chapStepActive(delta)`. keydown 리스너를 `chapStepPrimary`→`chapStepActive`로 교체. 공개 API에 `chapStepActive` 노출 |
| 작업 5 | 절 단위 히스토리 | 히스토리 엔트리 `{book, chapter}` → **`{book, chapter, verse}`**로 승격. `seedHistory` verse=null, `recordHistory(card, verse)`(같은 장이면 엔트리 verse만 갱신), `goToRef`는 하이라이트 첫 절(`verses[0]`)을 앵커로 전달. **`syncInterlinFrom`이 스크롤 시 현재 엔트리 verse를 라이브 추적**(떠날 때의 스크롤 위치 기억). `cardHistoryNav`는 복원 후 `scrollVerseToTop`(`scrollIntoView({block:'start'})`)로 그 절을 패널 최상단에 안착 |

### 6차 테스트 체크리스트

- [ ] 클립보드 `요 1:1-2,4-6` 수신 시 1·2·4·5·6절 누락 없이 카드에 로드
- [ ] 한 줄 출력 모드에서 `요 1:1-2,4` 복사 시 `… // …` 구분 표기
- [ ] 카드 클릭/드래그 시 테두리 네온 퍼플 스트로크 즉시 표시(1개만 활성)
- [ ] 키보드 ←/→ 가 네온 들어온(활성) 카드의 장을 이동(활성 없으면 1번 카드)
- [ ] 3·5절 보던 중 이동 후 ◀ 누르면 그 절이 패널 최상단에 안착

### 6차 검증 상태

- ✅ `node --check web/app.js` 문법 OK · NUL 0
- ✅ `python -X utf8 tests/test_core.py` 통과(콤마 파싱·`//` 케이스 추가) · `tests/test_webui_api.py` 전체 통과
- ✅ 6차 실창 유저 테스트 올패스

---

## 13. 7차 피드백 작업 (완료 — 최신, v1.0.2 대상)

> TODO.md 7차 명세 기준. 6차 실창 테스트에서 드러난 **시각 혼선**과 **스크롤 상태머신**을 정리.
> 변경 파일: `web/css/styles.css`, `web/app.js`.

### Phase 1 — 잠금/활성 카드 시각 분리 (작업 1)

**문제**: `.mcard.locked`(inset 스트로크)와 `.mcard.active`(아웃셋 네온 스트로크)가 둘 다 테두리를 써서, 잠금+포커스가 겹치면 혼동.

| 구분 | 변경 (styles.css) |
|---|---|
| 스트로크 독점 | `.mcard.locked { box-shadow: inset 0 0 0 1px var(--accent) }` **제거**. 외곽 스트로크는 이제 `.mcard.active` 전용 |
| 잠금 헤더 톤 | `.mcard.locked .card-hd { background: var(--seg-bg) }` — 차분한 톤으로 잠금 표시(테마 무관) |
| 자물쇠 칩 | `.card-lock` 기본 `opacity:.32`(흐린 회색) → hover 시 `opacity:1`. `.card-lock.on { color:#9A86FF; opacity:1 }`(네온 라벤더 점등). `.card-lock.disabled`는 `.38` 유지 |

- **결과**: 잠긴 카드는 외곽 스트로크가 전혀 없어 활성 네온과 절대 혼동되지 않고, 헤더 톤 + 점등된 자물쇠로 식별. 활성 네온은 그대로 유지.

### Phase 2 — 스크롤 라이브 추적 500ms 디바운스 (작업 2)

**문제**: 6차에서 `syncInterlinFrom`이 스크롤 매 프레임마다 `card.history[idx].verse`를 갱신 → 연산 낭비.

| 구분 | 변경 (app.js) |
|---|---|
| 관심사 분리 | `topVerseOf(body)` 헬퍼 추출. `syncInterlinFrom`은 **원어 카드 정렬만**(실시간 rAF 유지, history 미접근). history 기록은 신설 `lockHistoryVerse(card, body)`로 이전 |
| 500ms 디바운스 | 스크롤 리스너에 `scrollTimer` 추가. 스크롤 중엔 매 이벤트마다 `clearTimeout`으로 리셋 → **멈춘 뒤 500ms** 도달 시 1회만 `lockHistoryVerse` 실행(최상단 절을 현재 엔트리 verse에 락온 + `saveLayout()` 디바운스 연결) |

- **결과**: 휠 굴리는 내내 history 쓰기 동결, 정착 지점의 절만 기록. 원어 실시간 동기화는 영향 없음. `cardHistoryNav`의 프로그램 스크롤도 동일 경로로 멱등 처리.

### 7차 테스트 체크리스트

- [ ] 카드 잠가도 외곽 테두리 스트로크 없음 → 활성 네온과 혼동 불가
- [ ] 잠긴 카드: 헤더 톤 변화 + 자물쇠 네온 라벤더 점등 / 잠금 해제 시 자물쇠 흐려짐(.32)
- [ ] 스크롤 내리는 도중엔 이력 동결, 멈추고 0.5초 뒤 정착 절만 기록(◀로 복원 시 그 절)

### 7차 검증 상태

- ✅ `node --check web/app.js` 문법 OK · NUL 0
- ✅ `python -X utf8 tests/test_core.py` · `tests/test_webui_api.py` 전체 통과
- ⏳ 사용자 실창 테스트 대기
