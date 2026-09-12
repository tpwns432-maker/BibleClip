# BibleClip — Project Architecture Map (지명도 파일)

> **목적**: Claude가 컨텍스트 리프레시 시 전체 파일을 `cat`/`find`로 전수 조사하는 토큰 낭비를 막기 위한 **마스터 인덱스**. 새 기능/버그 추적 지시를 받으면 **이 파일을 먼저 읽고** 타깃 파일·함수를 조준한 뒤 해당 파일만 연다.
>
> **유지보수 규칙 (STRICT)**: `api.py`/`routes/*`에 API 추가, `app.js`(프론트)에 이벤트 디스패처/컴포넌트 추가, 파일 구조·경로 변경 시 **반드시 이 파일을 동시에 갱신**한다. 커밋·작업완료 보고 전 "지명도 파일 업데이트 완료 여부"를 체크포인트로 확인한다.

- **현재 버전**: v1.2.0 (`bibleclip/_version.py` = `__version__`, ASCII-only single source of truth)
- **killswitch**: `recommend_version` = 1.1.15 (직전 버전 규칙)
- **★ v1.2.0 내용(자막/PPT 화면 — 성경 구절을 문맥에 맞게 자동 줄바꿈해 투사)**: 예배 영상 송출 구조를 그대로 옮긴다 — 노트북=조작, 빔프로젝터=자막. 장바구니 팝아웃(FEAT-07)과 **같은 배관**(자체완결 HTML + `js_api` + `_child_windows` 추적 + `evaluate_js` 푸시). 신규 `web/subtitle.html`·**`web/js/versebreak.js`**·`webui/routes/slides.py`, 진입 = **F9**(즉석 구절 입력) / 레일 아이콘 `#subtitle-toggle`(창 열기) / 장바구니 순서. 🔑 **① 줄바꿈은 '그리는 쪽'이 푼다** — 어디서 줄을 나눌지는 실제 렌더 폭에 달렸고 그건 자기 글꼴·창 크기를 아는 자막 창만 잴 수 있다(Canvas `measureText`). 미리 구워두면 역본·글꼴·창 크기가 바뀔 때마다 어긋난다. 백엔드는 **'무슨 글자를 띄울지'까지만**(역본 텍스트 + 참조 문자열). 🔑 **② 한국어 성경은 절 경계 어미가 정형화돼 있어 규칙이 통한다**(4역본 319절 실측: 절당 내부 후보 평균 2.7개, 후보 있는 절 92~93%). 후보에 **등급**을 매기고(1 종결/절경계 → 2 연결 → 3 나열·쉼표 → 4 어절경계) **Knuth–Plass 식 DP**로 `Σ(줄 여백²) + Σ(등급 벌점)` 최소화. 나열문(계 21:8, 89자 한 덩어리)은 3등급 `…와/과`가 구제. 🔑 **③ 문장 경계는 '선호'가 아니라 '강제'** — 등급만으로는 폭이 아까울 때 DP 가 서로 다른 두 문장을 한 줄에 묶는다(창 1:10 이 대표 사례). `sentenceEnd()` 가 참이면 그 뒤는 반드시 줄이 끝난다. ⚠️ **강제라서 오탐이 그대로 보인다** — 실측으로 걸러냈다: 단독 `다`(부사 '모두', 최다 오탐 22회)·`아니라`(연결)·`것이요`/`아니요`(나열)·`바다`/`따라`/`것보다`(명사·조사·비교). `아니라`는 빼되 `아니니라`는 살려야 해서 **접미사가 아니라 정확히 일치할 때만** 제외. 정리 후 60개 어절 전부가 실제 문장 끝이었다. 문장부호로 끝나면 어미와 무관하게 문장 끝(현대어 역본용). 🔑 **④ 외부 데이터는 답이 아니었다(조사 완료, 되풀이 금지)** — (a) 동봉 16역본 중 **14개에 문장부호가 있지만** 문장 경계가 **역본마다 다르다**(개역한글 창1:12 = 1문장 ↔ 새번역 = 2문장). 다른 역본을 정답지로 쓰면 없는 경계를 집어넣어 **개악**된다. (b) **Kiwi**(requirements 에 있음)는 현대 한국어 학습이라 고어체에서 우리 규칙보다 못하다(내부 경계 탐지 **71곳 vs 25곳**, `칭하시니라`의 `니라`를 연결어미 EC 로 오판). (c) 원어 데이터에 히브리어 캔틸레이션 악센트 없음. (d) **개역한글은 2012년 저작권 만료(퍼블릭 도메인), 개역개정은 저작권 유효**. 남은 가능성은 USFM `\q`(시가서 행 구분)뿐. 🔑 **⑤ 긴 본문 자동 분할** — `paginate()`. 투사 기준 '읽을 수 있는 바닥'(28px) 밑으로 내려갈 상황이면 우겨넣지 않고 장을 넘긴다. **절 경계에서만** 나눈다. 장수는 자막 창만 알 수 있어(`report_slide_pages`) 백엔드가 받아 `◀▶`가 **장 안에서 먼저** 움직이고 끝에서 다음 구절로 간다. 뒤로 갈 땐 **`page = -1` = 마지막 장** 약속(큰 수 sentinel 은 payload 에 `1000001/1` 로 새어 나감). 🔑 **⑥ 성능 — 병목은 측정이 아니라 DP 였다** — 시편 119편 최초 **3255ms** → 어절 폭 누적합 770ms → 측정 캐시 835ms(**효과 없음 = 측정이 병목이 아니라는 신호**) → **`memo.clear()` 제거 157ms**. 줄 수 `k` 를 1부터 늘리며 매 회 memo 를 비워 DP 를 통째로 21번 다시 돌고 있었다(키가 `(i,k)` 라 지울 이유가 없다). 일반 슬라이드 **0.2ms**. 🔑 **⑦ 겉모습** — `subtitle_preset`(green/navy/black/white/theme) ⚠️ **`DEFAULT_SETTINGS`+`_APP_KEYS` 동반 등록 필수**(v1.1.4 교훈). 자막 창은 자체완결이라 메인이 주입한 커스텀 글꼴을 물려받지 못해 **같은 브리지(`get_font`)로 base64 를 받아 제 문서에 `@font-face` 를 따로 심는다**; 글꼴이 바뀌면 글자 폭이 달라지므로 **줄바꿈을 다시 계산**. 설정 변경 시 `set_app_setting` 이 `_broadcast_subtitle_style()` 로 창에 푸시. ⚠️ **미구현**: 장바구니 `◀▶` 제어 UI(사용자 판단으로 보류 — 자막 창에 포커스를 두면 `←/→` 로 장바구니 순서 탐색은 됨).
- **★ v1.1.15 내용(F11 진짜 전체화면 + 최대화 크기 저장 차단)**: ① **F11 이 창 안에서만 전체화면이던 문제** — HTML `requestFullscreen()` 은 **웹뷰 뷰포트 안에서만** 전체화면이라 제목표시줄·작업표시줄이 그대로 남았다. 브라우저는 브라우저가 제 창을 OS 전체화면으로 바꿔주지만 **임베드된 WebView2 에는 그 주인이 없다**. → 브리지 **`Api.set_native_fullscreen(on)`**(pywebview `window.toggle_fullscreen()`) 신설. ⚠️ pywebview 의 것은 **세터가 아니라 토글**이라 현재 상태를 `Api._fullscreen` 에 들고 있다가 같은 상태 요청은 무시한다(중복 호출로 어긋남 방지). `presentToggle()` 진입 시 **창을 먼저** 전체화면으로(뷰포트가 화면 전체가 되어야 그 위에서 카드가 채워진다 — 작은 창에서도 최대화 없이 바로 전체화면이 되는 이유), 실패 시 되돌림. 해제는 **`fullscreenchange` 한 곳에서만**(ESC·F11 어느 경로로 나가도 어긋나지 않음). ② **최대화 크기가 저장되던 문제** — 최대화한 채 종료하면 다음 실행이 '최대화 크기의 일반 창'으로 열려 복원이 안 됐다. **`_looks_maximized(w, h)`**(app.py): pywebview 가 창 상태를 이식성 있게 주지 않으므로 **크기로 판정**(모든 `webview.screens` 와 비교, 여유 96px). 걸리면 기하 저장을 통째로 건너뛰어 **직전 정상 크기를 보존**. 🔑 **`webview` 는 함수 안에서 지연 임포트해야 한다** — `app.py` 는 모듈 최상단에 `import webview` 가 **없다**. `_strip_motw()` 가 `import webview`→clr 보다 먼저 돌아야 v1.1.2 의 MOTW 수정(다운로드본 실행 실패)이 유지되기 때문. 최상단으로 올리면 **테스트는 통과하면서 배포본만 실행 불가**가 된다(작업 중 실제로 밟을 뻔했음).
- **★ v1.1.14 내용(F2 상대 참조 단축 입력 + F11 점프 강조 제거)**: ① **F2 단축 입력** — 책 이름을 생략하면 **'점프를 받을 카드'의 위치 기준**으로 해석. `22`·`22절`=현재 장의 절, `22-24`(`~`/전각 `－～`)=절 범위, `44:22`(전각 `：`)=현재 **책**의 장:절, `44장`=현재 책의 장. `relativeRef(q, ctx)`+`vRange`(search-notes.js)가 `resolve_reference` **앞단**에서 가로챈다. 🔑 **문맥은 반드시 goToRef 가 고를 카드와 같아야 한다** — 그래서 `goToRef` 의 대상 선정(우선순위 fs카드→일치 잠금카드→첫 비잠금)을 **`jumpTarget(book, chapter)`** 로 분리하고 **`CardManager.jumpContext()`**(={book,chapter})로 공개. 다른 카드를 기준으로 삼으면 엉뚱한 장의 22절로 간다. 🔑 **범위 밖은 무반응**(사용자 선택) — 키워드 검색으로 흘려보내면 `50`이 민수기 7:50 같은 곳으로 튄다. 같은 장 안의 절은 **DOM(`.v[data-v]`)으로 즉시 검증**해 브리지 왕복이 없다(`verseOnScreen`). 책 이름이 붙은 입력(`사 44:22`)·키워드는 파서가 `null` 을 돌려 기존 경로 그대로. 발견 가능성 위해 `present.qsPlaceholder` 에 힌트 추가(ko/en). ② **F11 점프 강조 제거** — `.mcard:fullscreen .scripture .v.hl` 에서 배경·좌측 액센트 바·`hl-flash` 애니메이션 + **`.scripture .v.hl` 의 음수 마진(-8px)/패딩까지 리셋**(발표 화면은 좌우 9vw 라 그 절만 튀어나오면 눈에 띔). ⚠️ **`.v.hl` 클래스 자체는 절대 지우면 안 된다** — 색칠 표식이자 `centerHighlightVerse()` 가 스크롤 목표 절을 찾는 **앵커**라서, 클래스를 빼면 점프해도 그 절로 이동하지 않는다. **보이는 것만** 죽인다. 테스트 `tests/test_quickjump_parse.js`(33건, node — 파서 정의를 소스에서 이름으로 잘라 eval).
- **★ v1.1.13 내용(F11 테마 적용 + 발표 화면 구역 구분)**: 🔑 **① 진범은 정의된 적 없는 토큰 `--bg`** — `.mcard:fullscreen { background: var(--bg) }`. 미정의 커스텀 속성은 **파스 오류가 아니라 '계산 시점 무효(invalid at computed-value time)'** 라서 `background` **숏핸드 전체가 `unset`(=transparent)** 이 되고, 그 결과 특이도가 더 낮은 `.card { background: var(--card-bg) }` 까지 덮어버려 **전체화면 본문만 테마를 전혀 따르지 못했다**. 라이트에서는 결과가 흰색으로 보여 **우연히 맞아 보인 탓에** 오래 묻혀 있었다. → `var(--app-bg)`. CSS 전체 커스텀 속성 감사 결과 미정의+폴백없음은 이것뿐(`--card-2`/`--danger`/`--mono`/`--reading-font`는 폴백 있어 정상). 🔑 **② 헤더 배경을 전용 토큰으로 분리** — `.present-banner` 가 `--seg-bg` 를 참조하고 있었으나 그건 **세그먼트 컨트롤·메뉴 호버 등 10곳이 공유**하는 토큰이라, 발표 화면 색을 조정하면 무관한 UI가 같이 바뀌는 구조였다. → **`--present-bar-bg`** 신설. 🔑 **③ 구역 3층화** — 발표 화면은 `틀고정 헤더 / 역본명 띠(.shead, split 모드의 sticky 행) / 본문` 세 구역인데 모두 같은 면이라 뭉쳐 보였다. 색 층을 `--present-bar-bg`(헤더) → `--card-bg`(역본명) → `--app-bg`(본문) 으로 내리고, 헤더와 역본명 띠에 **1px 선 + 얕은 그림자**를 준다. 신규 토큰 **`--present-bar-bg`/`--present-bar-line`/`--present-bar-shadow`**(라이트 `#F6F3FC`/`#E6E1F2`/`0 1px 2px .06`, 다크 `#1D1633`/`#322A49`/`0 1px 2px .35`). ⚠️ **다크에서 선은 면보다 밝아야 보인다**(면 `#1D1633`/`#171127`/`#0F0B1A` → 선 `#322A49`). 🔑 **④ 디자인 언어는 양 테마 공통** — 시행착오를 남긴다: 처음엔 `--card-shadow`(확산 `-14px` 라 거의 안 보임) → 큰 드롭섀도(`0 10~12px 24~28px -6px`)로 키웠더니 **라이트에서 즉시 촌스러워졌고**(흰 면 + 큰 그림자), '라이트는 선 / 다크는 그림자'로 방식을 갈랐더니 **두 테마가 서로 다른 디자인**이 되어 더 어색했다. 최종 = **양 테마 모두 선 주력 + 그림자는 이음새 제거용**. 선 두께도 **1px 이 정답**(1.5px=비정수 배율에서 반 픽셀 뭉개짐, 2px=발표 화면에서 굵음 — 둘 다 시도 후 되돌림). ⚠️ 이 구역 구분은 **F11 한정**(`.mcard:fullscreen .split-cols .shead`) — 작은 카드의 windowed 모드엔 과하다. 역본명 띠는 **병렬 독서(split)에만 존재**(절별 대조는 역본명이 줄 앞 인라인 `.vver`).
- **★ v1.1.12 내용(형광펜 = 절 내부 단어 하이라이트)**: 구절 안의 단어 구간에 색을 칠하고 영속 저장. 저장 단위 = **(책, 장, 절, 역본)** → 정렬된 비겹침 구간 `[{s,e,t,c}]`. `bibleclip/highlights.py`(`Highlights`, `userdata/user_highlights.json`, notes.py 미러·fail-soft) + `webui/routes/highlights.py`(`HighlightRoutes`) + `library.highlights`. 🔑 **① `.vtx` 텍스트 래퍼가 이 기능의 토대다** — 절 요소에는 절번호(`.vnum`)·역본명(`.vver`)·노트 배지(📄)가 섞여 있어 절 기준으로 문자 오프셋을 세면 장식 길이만큼 어긋난다. 렌더 3함수(`renderMultiVersesInto`/`renderSplitVersesInto`, 단일·다역본·split 전부)가 본문을 `<span class="vtx" data-ver="역본">`으로 감싸면 (a) 오프셋 = `.vtx` 안 순수 텍스트 위치, (b) 다시 칠할 때 `.vtx.innerHTML`만 교체하므로 절번호·배지 무손상, (c) `esc()`는 `& < >`만 바꾸므로 **`vtx.textContent === 원문`이 항상 성립** → 원문 캐시가 아예 불필요(DOM이 곧 진실). 🔑 **② 오프셋은 반드시 `esc()` 이전 원문 기준** — `&`가 `&amp;`로 5자가 되므로 이스케이프된 문자열에 오프셋을 적용하면 하이라이트가 밀린다. 원문을 구간 분할 → 조각별 esc → span 조립 순서. 🔑 **③ 역본별 독립 저장**(키에 version 포함) — 번역어가 달라 역본 간 오프셋 공유가 불가능. 개역개정에 칠한 게 KJV 셀의 엉뚱한 위치에 찍히는 것을 원천 차단. 🔑 **④ 오프셋 단독은 취약** — 성경 DB 갱신/역본 재동봉으로 본문이 밀리면 전 구간이 오작동. `t`(원문 조각)를 함께 저장해 그리기 전 검증, 불일치 시 `indexOf`로 재탐색, 그래도 없으면 **조용히 폐기**(발표 화면에 엉뚱한 곳이 칠해지는 것보다 사라지는 게 낫다). 🔑 **⑤ 기존 '드래그 → 걸친 절 복사'와 공존** — 그 제스처를 빼앗지 않는다. 복사+토스트는 그대로 두고 색상 팔레트를 **함께** 띄운다(색 고르면 하이라이트, 딴 데 클릭하면 복사만 된 셈). 회귀 0. 🔑 **⑥ F11 팝업은 fullscreen 요소 안에 append** — 전체화면 요소 밖의 DOM은 아예 렌더되지 않으므로 `document.body`에 붙이면 발표 중 안 보인다(`document.fullscreenElement || document.body`). 같은 함정에 빠져 있던 **절 우클릭 메뉴(`.ctx-menu`)와 묵상 노트 편집 모달(`.note-modal-back`)도 함께 고쳤다** — 둘 다 `document.body.appendChild` → `(document.fullscreenElement || document.body)`. 노트 모달은 우클릭 메뉴에서만 열리므로 메뉴만 고치면 막다른 길이 되어 반드시 같이 가야 한다. 이 패턴의 선례는 `openQuickSearch`(F2, search-notes.js). **의도적으로 남긴 것**: 토스트(`.toast-wrap`, index.html 정적)는 F11에서 계속 안 보인다 — 발표 화면에 뜨면 그게 곧 청중에게 보이는 소음이므로 안 보이는 게 맞다(사용자 확인). 부팅 시에만 뜨는 모달(`showForcedUpdate`/`maybePatchModal`)과 크롬 앵커 팝업(`openMenu`/`showTooltip`, 앵커가 F11에서 `display:none`)·`.lex-tip`(`.scripture`에서 스트롱코드 숨김)은 F11 도달 불가라 미변경. 프론트 `cards.js`: `decorateHighlights`(장 단위 fetch, `loadBibleCard`에서 `decorateNotes` 앞)/`paintHighlights`(캐시→DOM, 통신 없음·멱등)/`hlTextHTML`(오프셋→HTML+검증·재탐색)/`hlMark`/`vtxOffset`(Range로 실측)/`selectionRanges`(드래그를 (역본,절)별로 쪼갬 — 여러 절·여러 컬럼 걸침 지원, 앞뒤 공백 트림)/`normRanges`(정렬·같은색 병합·비겹침·**t 재계산**)/`mergeRange`(덧칠: 새 색 우선, 남는 쪽 보존, 가운데 덮으면 좌우 분리)/`subtractRange`(✕ 지우기, 가운데 지우면 분리)/`openHlPalette`/`applyHl`/`vtxFor`. 상태 `HL_COLORS=[y,g,b,p]`/`hlCache`/`hlPop`. CSS `.hl-mark[data-c]`(4색, `box-decoration-break:clone`으로 줄바꿈 조각마다 라운딩, `position:relative`로 절 호버 배경 위에 올림)·`.hl-pal`/`.hl-sw`(z-index 1300), 토큰 `--hl-{y,g,b,p}`(+다크 재정의)·`--hl-*-dot`(팔레트 스와치용 불투명). i18n `hl.{y,g,b,p,clear}`. **부수 수정**: F11에서 절 배경 강조 제거 — `.mcard:fullscreen .scripture .v:hover, .mcard:fullscreen .scripture .v.copied {background:none;box-shadow:none}`. 발표 화면에 조작 흔적이 뜨는 건 소음(노트 배지를 숨기는 것과 같은 이유). `.copied`(절 클릭 복사 시 초록 플래시)는 처음에 '의도한 동작의 피드백'이라 남겼다가 **실제 발표 화면에서 튀어 함께 껐다** — `copyVersesFromCard`가 async(백엔드 왕복 후 클래스 부착)라 클릭 순간이 아니라 **다음 입력 이벤트에 뒤늦게** 그려져 더 눈에 걸린다(호버를 끄기 전엔 호버 배경이 매 순간 깔려 초록이 묻혀 있었을 뿐). 그리고 F11에선 토스트(`.toast-wrap`)도 fullscreen 요소 밖이라 렌더되지 않아 **복사 피드백이 둘 다 사라지므로**, click 핸들러에 `if (document.fullscreenElement) return;` 가드를 넣어 **발표 중 절 클릭 복사를 차단**했다 (무심코 한 번 누르면 준비해 둔 클립보드가 무표시로 덮이던 문제). 의도적 제스처인 **드래그 복사와 우클릭 메뉴 복사는 유지**. ⚠️ **칠해진 부분 클릭은 절 복사가 아니라 팔레트**(색 변경/지우기)로 바뀐다 — 안 칠한 부분 클릭은 여전히 절 복사. ⚠️ `renderVersesInto`는 **호출처가 없는 사문(dead code)**이라 `.vtx`를 적용하지 않았다 — 되살려 쓸 경우 하이라이트가 동작하지 않는다.
- **★ v1.1.11 내용(BM25 랭킹 + 유의어 확장 검색)**: ① **BM25 랭킹** — `bible_db.py` `bm25_search(keyword, mode, limit, expand)` 신설. 기존 `_score`(매칭수×10+밀집도+짧은절)에 **IDF가 없어** '하나님'(수천 절)과 '연단'(수십 절)을 동가로 취급하던 것을 표준 BM25로 교체(k1=1.5, b=0.75, idf=ln(1+(N-df+.5)/(df+.5))). `search()`의 **1차 경로**(공백 유무·한/영 무관), 결과 0건이나 예외 시 기존 계단(smart_search→exact→형태소→trigram)으로 **100% 폴백**. 🔑 **FTS5를 쓰지 않았다** — df/tf/절 길이/N이 이미 메모리 역색인(`_inverted_index`+`_verse_tokens`, 부팅 시 백그라운드 워밍)에 다 있고, FTS5는 캐시 DB+최신성 관리+한국어 토크나이저 우회가 딸려오는데 31,103절에선 얻는 게 속도뿐이다. 목표는 수단(FTS5)이 아니라 IDF 랭킹이었다. 보조: `_ensure_bm25_stats()`(N/avgdl 1회), `_term_addrs(term)`(부분일치 조회 — smart_search와 동일 규칙), 밀집도 보너스(`PROX_WEIGHT`, BM25는 위치를 안 보므로 tiebreaker). ② **유의어 확장(고어↔현대어)** — 다역본 앱 고유 실패 모드 제거: 새번역으로 읽다 '이집트'를 기억하고 개역한글에서 검색하면 **0건**(새번역 690건). 사전 **`web/data/bible_synonyms.json`**(7,630 표제어, 317KB, `map[단어]=[[대체어,신뢰도],…]` 양방향 대칭) + 로더 **`bibleclip/data/synonyms.py`**(`SynonymDict`/`shared()`/`expand`/`words`/`expand_all`, **fail-soft** — 파일 없으면 확장 0개로 기존 동작 유지). ⚠️ **web/ 아래에 두는 이유**: 빌드 3곳(BibleClipWeb.spec·build_web.ps1·build.yml)이 모두 `--add-data web`이라 **빌드 스크립트 수정 없이** 자동 동봉(v1.1.7 읽기 글꼴과 같은 요령). 🔑 **가중치는 고정값이 아니라 신뢰도(Dice) 비례**여야 한다 — 전부 0.55로 두자 '이집트' 검색에서 오탐 '인도하여'(0.22)가 정답 '애굽'(0.91)보다 **위로 올라왔다**(오탐이 더 희귀해 IDF가 높음). `w = SYN_W_MIN(0.15) + (SYN_W_MAX(0.75)-SYN_W_MIN)·conf`. 질의 토큰마다 유의어를 '대체 후보 그룹'으로 묶어 AND는 그룹 단위 만족, 점수는 그룹 내 최고점만(중복 가산 방지). ③ **설정 토글 `search_synonyms`(기본 True)** — `DEFAULT_SETTINGS`+`_APP_KEYS`(None=boolean)+`get_initial`+`get_app_settings`, 프론트 `state.searchSyn`(core.js)·`#opt-search-syn`(index.html 검색 그룹)·i18n `modal.searchSyn`/`search.synExpanded`. ④ **API 계약** — `search()`가 `matched_tokens`(질의어 어근, **기존 계약 유지**)와 **`highlight_tokens`**(질의어+확장어, 프론트 강조용)·**`expanded`**({질의어:[확장어]}, 메타 줄 표기용)를 분리 반환. 확장어를 matched_tokens에 섞으면 test_webui_api가 깨지고 의미도 흐려진다. 프론트는 `res.highlight_tokens || res.matched_tokens` 폴백. **사전 생성은 비배포** `_local/synonym_experiment/`(`build_v5.py` 추출·`export_for_app.py` 앱 포맷 변환·`impact_v5.py` 효과 측정).
- **★ v1.1.10 내용(병렬 독서 = 절 단위 행 정렬)**: 병렬 독서(`view_mode='split'`)에서 역본마다 줄 수가 달라 같은 절의 **시작점이 어긋나던** 문제. 구조를 뒤집어 해결 — 기존 **역본별 독립 스크롤 컬럼 `.scol` N개 + 절 앵커 스크롤 싱크** → **본문 단일 스크롤러 + 절 1개 = 한 행**. `renderSplitVersesInto(body, versions, chapDataArr, highlight)` 재작성: 전 역본 절 번호의 **합집합**을 행으로 잡고(`nums` Set, 오름차순), 행 = `<div class="v srow" data-v=n>` + 역본별 셀 `<div class="scell">`(없는 절 = `.scell.empty` 빈 칸, 임의 병합 안 함), 상단 = sticky 헤더 행 `.srow.shead`. CSS `.split-cols .srow{display:flex}` + `.scell{flex:1 1 0;min-width:0}` → **행 높이 = 최장 셀** 이므로 절 시작점이 구조적으로 일치. **격자선(테두리)은 그리지 않는다** — 정렬만 격자, 시각적으로는 선 없이 셀 padding으로만 분리(사용자 요청). `.v` 기본 여백/라운드/후광 그림자/`.hl` 음수 마진은 격자를 어긋내므로 split에서 무효화. **부수 정리**: 스크롤러가 1개가 되어 컬럼↔컬럼 싱크가 불필요 → `scriptureScrollers(card)`=`[body]`, scroll 핸들러의 `.scol` 캐치 제거(`.scripture`만), `progScroll`/`syncFrom`/`snapshotAnchors`/`realignAnchors`는 형태 유지(카드→연동 원어 싱크는 그대로 필요). `decorateNotes`는 split 행에 배지를 붙이면 flex 칸이 하나 늘어나므로 **첫 내용 셀 안**(`.scell:not(.empty)`)에 삽입. 전체화면(F11) 오버라이드도 flex 컬럼 → block 스크롤 + 셀 여백으로 교체.
- **★ v1.1.9 내용(장 넘기기 화살표의 책 경계 이월)**: 책의 첫/마지막 장에서 장 넘기기 화살표가 무반응이던 문제(`cardChapStep`이 현재 책의 장 목록 범위를 벗어나면 그냥 `return`). **`neighborBookChapter(version, book, delta)`** 신설 → 첫 장 `←`=앞 책의 **마지막** 장(출 1장→창 50장), 마지막 장 `→`=다음 책의 **첫** 장(창 50장→출 1장). 창세기 1장 `←`/요한계시록 마지막 장 `→`는 성경 양 끝이라 no-op 유지. ⚠️ 책 이동은 `booksFor(navVer)`의 정경 순서(`db.book_list`) **배열 인덱스** 기준 — 책 `num`이 10,20,… 비연속이라 `num` 산술 불가. 장이 없는 책은 스킵(신약만 있는 역본 방어), 역본에 없는 장을 들고 있던 카드는 첫 장으로 클램프. 책 변경 시 `card.book`도 갱신되어 기존 경로(`loadBibleCard`→헤더 책 pill, `reloadDependents`, `recordHistory`, `note_position`, `saveLayout`)가 그대로 따라옴 → ◀▶ 히스토리·읽던 위치 보존 정상. 키보드 ←/→(search-notes.js)와 헤더 `‹ ›`가 같은 함수를 타므로 cards.js 한 곳 수정으로 양쪽 적용.
- **★ v1.1.8 내용(레일 패널 슬라이드 애니메이션 = TODO Part3-3 보류분 완료)**: 로그/장바구니/노트 공용 `.drawer`의 열기(20px 팝+페이드)·닫기(`display:none` 즉시) → **transform 트랜지션 + `.open` 클래스** 양방향 슬라이드로 교체. 닫힘=`translateX(100%)`/열림=`translateX(0)`, ~0.45s. 열기=ease-out-back `cubic-bezier(.34,1.2,.64,1)`(끝 살짝 오버슈트), 닫기=시간-역재생 미러 `cubic-bezier(.36,0,.66,-.2)`. **core.js 전역 공용 헬퍼 `slideOpen(el)`/`slideClose(el)`(`.open` 제거→`transitionend`에 `hidden=true`, +600ms 폴백)/`drawerOpen(el)`(=`.open` 클래스)** 신설 → `openDrawer`/`closeDrawer`(core.js)·`openCart`/`closeCart`·`openNotes`/`closeNotes`(search-notes.js) 6개 + 토글·unread 배지·retranslate 재렌더 판정이 모두 이를 사용(`.hidden` 읽기 제거). **스크롤바 깜빡임 수정**: 드로어가 `translateX(100%)`로 화면 밖까지 나가 문서 가로 오버플로→윈도우 스크롤바 반짝이던 것을 드로어 앵커 `.app`에 `overflow:hidden` 추가로 클립(모달·토스트·메뉴는 `.app` 바깥 body 직계라 무영향). cards.js 미변경.
- **★ v1.1.7 내용(읽던 위치 보존 + 기본 글꼴 동봉)**: ① **읽기 위치 보존 확대** — 카드 재렌더 시 보던 절 유지(장 맨 위 튐 방지). BUG-01 인프라(`snapshotAnchors`/`realignAnchors`, v1.1.6 컬럼 일반화) 적용처 확대: 역본 추가/제거(`updateViewerVersions`)·순서 변경(`commitChipDrag`)·보기모드 전환(view_mode setSeg) — 모두 `snapshot→await reloadAllBible→realign`. **`CardManager.reloadAllBible()`이 Promise 반환**으로 변경(`Promise.all(loadBibleCard)`)해 재렌더 완료 후 복원 가능. ② **F11 전체화면 위치 보존** — 진입 시 폰트 확대 reflow로 보던 절이 앞쪽으로 밀리던 문제. `presentToggle`이 진입 전 `snapshotAnchors`→`requestFullscreen().then`에서 한 프레임 더 대기 후 `realignAnchors`; `fullscreenchange`(ESC/F11 해제)는 마지막 읽던 절(`card.verse`)로 `scriptureScrollers`+`alignInterlin` 복원. ③ **기본 읽기 글꼴 동봉(나눔고딕/나눔명조, OFL)** — `web/fonts/reading/나눔고딕.ttf`·`나눔명조.ttf`(+OFL.txt/README). `web/`가 `--add-data "web;web"`(CI build.yml Win/mac 공통)로 통째 번들이라 **빌드 스크립트 추가 수정 불필요**. 백엔드 `list_fonts`/`get_font`가 `_builtin_fonts_dir()`(=`get_resource_dir()/web/fonts/reading`)와 `_user_fonts_dir()`(=`get_base_dir()/fonts`)를 함께 스캔(built-in 우선·dedup, `{family,file,builtin}`). family=파일명 stem → 한글 파일명이 곧 한글 메뉴 라벨. 프론트(`loadFontsList`/`injectFont` base64) 변경 없음.
- **★ v1.1.6 내용(본문 보기 모드 + 장바구니 명칭 정리)**: ① **View Mode 신설(`view_mode`)** — 설정 ▸ 읽기 ▸ [본문 보기] 세그먼트(`opt-view-mode`)로 멀티 역본 표출 전환. `'interleave'`(절별 대조; 기존 `renderMultiVersesInto` 세로 교차, 기본) / `'split'`(병렬 독서; 역본별 좌우 컬럼 `.scol` 분할). `DEFAULT_SETTINGS`+`_APP_KEYS`({'interleave','split'})+`get_initial`+`get_app_settings`에 등재, 프론트 `state.viewMode`(core.js), 변경 시 즉시 `CardManager.reloadAllBible()`. **view-only — 복사/클립보드 출력 무관**. `loadBibleCard`가 `state.viewMode==='split' && viewer>1`이면 `renderSplitVersesInto`(역본명 sticky 헤더 `.scol-head` + `.v`), 아니면 기존 경로. CSS `.card-body.scripture.split-cols`(flex 행, overflow hidden) + `.scol`(flex:1, min-width:200px, 독립 스크롤) + 전체화면 split 오버라이드. ② **병렬 독서 스크롤 싱크 일반화** — 단일 body 가정을 컬럼 N개로 확장. `syncInterlinFrom`→**`syncFrom(card, scrollEl)`**(스크롤된 컬럼이 드라이버 → 형제 컬럼 + 연동 원어를 절 앵커/분율로 추종, 완전 양방향), 헬퍼 `scriptureScrollers(card)`(split→`.scol`들, 아니면 body 1개)/`primaryScroller`(첫 컬럼=히스토리·점프 정규 앵커)/`linkedInterlinScrollers`/`alignInterlin`. `scrollBodyToVerse`→**`scrollElToVerse(el,n,guard,align)`**(요소 단위, `guard` boolean)+`findVerseEl`(결손 절=가장 가까운 절 fallback). `progScroll`을 **카드 id→스크롤 요소 단위** 가드로 변경(컬럼↔컬럼+카드→원어 두 레이어 피드백 차단). scroll 핸들러가 `.scol` 또는 `.scripture` 캐치, `snapshotAnchors`/`realignAnchors`/`scrollVerseToTop`/`goToRef`/`cardHistoryNav` 전 컬럼 처리. **사전(lexicon) 카드는 원문 경유라 무영향(검증 완료)**. ③ **카드별 [대조] 토글(FEAT-04) 제거** — `card.parallel`/`parallelVersion`, 헤더 pill, `handleAction "parallel"`, serialize/restore 영속화, `updateBibleHeader` 갱신, `cardVersions` 단순화(→`state.viewer`만). 구버전 레이아웃 `parallel:true`는 `restore`가 조용히 무시(마이그레이션). i18n `card.parallelOff`/`card.tip.parallel` 삭제. ④ **'설교 장바구니'→'장바구니' 명칭 정리** — 노출 문자열(`nav.cart`/`cart.title`/`cart.add`/`cart.windowTitle` ko·en + index.html·cart.html 폴백)만 변경, 백엔드 식별자(`sermon_cart.json`/`cart.py`/주석)는 유지.
- **★ v1.1.5 내용(다중 창 확장 · 발표 개선 · DnD 재구축 = TODO Part 3)**: ① **FEAT-07 설교 장바구니 팝아웃 창**(`web/cart.html` 신설, 자체완결 미니멀) — 메인과 실시간 양방향 동기화(`set_cart`→`_broadcast_cart`가 메인 `onCartChanged`+팝아웃 `renderCartItems` 동시 푸시), 창 성구 클릭→`cart_goto`→메인 `onReference`로 점프(F11 포함). 자식 창 `_child_windows` 추적(좀비방지). 브리지 `open_cart_window`/`cart_goto`(+`get_cart`/`set_cart`). app.py `_cart_window_factory`/`api._cart_window`. ② **F11 틀고정 헤더** — `.present-banner`(flex `order:-1` 고정, `{book_full} {chap}장`), `cards.js presentBannerText/updatePresentBanner`를 `loadBibleCard` 종료부에 연결. ③ **장바구니 DnD 재구축** — HTML5 native(드래그중 `insertBefore`→WebView2 드래그중단)를 **transform 프리뷰+drop 커밋**(역본 칩과 동일)으로 교체. `wireCartDnD`(위임)/`layoutCartGap`/`commitCartDrag`/`flipCartSettle`, `.cart-item{transition:transform .18s}`. 메인+팝아웃. ④ **사전 언어 표면별 선택**(Part3-1) — toolbar 토글+설정 ⚙ 사전언어 **제거**, 기본=프로그램 언어(`lexLang=I18N.getLang()`), 사전 카드 `한/영` pill(`data-act="lexlang"`, 전역 공유, `setLexLang`) + 사전 팝업 창 드롭다운(`dicthtml._dict_page_html` ko·en 임베드+JS show/hide, 항상 노출). `open_dict_window`가 양 언어 조회. ⑤ **노트 배지 위치**(Part3-2) — `decorateNotes`가 `el.appendChild`(절 끝), F11 `.note-badge{display:none}`. ⑥ **노트 export 구분선**(Part3-5) — `buildNotesText(list, true)`. ⑦ **창 off-screen 수정** — `app.py _onscreen()`가 `(-32000,-32000)`(최소화 sentinel) 복원·저장 차단. (Part3-3 레일 패널 애니는 **보류**, Part3-4가 ③.)
- **★ v1.1.4 내용(안정화 분리 배포)**: ① **설교 장바구니 영속성(FEAT-08)** — 장바구니를 백엔드 파일(`userdata/sermon_cart.json`, `bibleclip/cart.py` `Cart`)에 저장. 기존 `localStorage`는 pywebview 랜덤 loopback 포트로 origin이 매번 바뀌어 재시작 시 고아가 되던 문제(진짜 원인). `get_initial.cart`로 부팅 복구 + 추가/삭제/재정렬마다 `set_cart` write-through. 브리지 `get_cart`/`set_cart`(NoteRoutes), 프론트 `restoreCart`/`saveCart`(search-notes.js). ② **좀비 자식 창 수정(BUG-SYS)** — `app.py`가 생성 자식 창을 `_child_windows`로 추적, 메인 `closing` 시 일괄 `destroy()`(자식이 먼저 닫히면 `closed` 이벤트로 자동 해제). ③ **설정값 재시작 복귀 수정** — `library.load_settings`: (a) 폰트 클램프 `min(30)`→**`min(400)`**(set_font_size와 정렬; 30 초과 저장이 매 실행 30으로 되돌려지던 버그), (b) **`DEFAULT_SETTINGS`에 `ui_lang`/`reading_font`/`auto_copy_top_result` 추가**(load는 기본값에 있는 키만 수용 → 누락 키는 저장돼도 드롭되어 복귀했음), (c) core.js boot의 `ui_lang` 동기화를 프론트→백엔드에서 **백엔드 권위**(`init.ui_lang`→`I18N.setLang`)로 뒤집음(localStorage 휘발분이 올바른 백엔드 값을 덮던 문제). v1.1.5 예정: FEAT-07 장바구니 팝아웃(실시간 양방향 동기화) + Part 3 UI/UX.
- **v1.1.3 내용**: **KJV+ 성경 기본 동봉**. `bible_versions/KJV+.SQLite3`(KJV 1769+Strong's, 퍼블릭 도메인)가 `.gitignore`로 미추적이라 CI checkout에 없어 그동안 릴리즈에서 빠졌었음(로컬 build_web.ps1만 동봉). `.gitignore` 예외로 추적 + CI `build.yml` Windows/macOS Assemble에 KJV+ 복사 추가 + exe.config CI 동봉. ⚠️ **빌드 정의가 둘(local `build_web.ps1`/`build_mac.sh` ↔ CI `.github/workflows/build.yml`)이라 동봉물 변경 시 양쪽 다 고쳐야 함**(이번 드리프트의 교훈).
- **★ v1.1.2 내용(일부 PC "런타임 에러" 진범 해결)**: 다운로드 zip의 **MOTW(Zone.Identifier=3)** 가 번들 `Python.Runtime.dll`에 묻어 .NET이 "인터넷 어셈블리" 로드를 거부(`Failed to resolve Python.Runtime.Loader.Initialize`)하던 문제. **로컬 복사본은 표식 없어 정상, 다운로드본만 실패** → startup_error.log로 확진(ZoneId=3 + ReferrerUrl=zip). 수정: `app.py _strip_motw`(clr import 전 번들 .dll/.pyd/.exe의 Zone.Identifier ADS 1회 제거, `.motw_cleared` 마커) + `BibleClipWeb.exe.config`의 `loadFromRemoteSources`(읽기전용 위치 백스톱, build_web.ps1 동봉). .NET·WebView2·Python 버전·보안SW 전부 무죄였음.
- **v1.1.1 내용**: 실행 실패 의심으로 CI Windows 빌드 Python 3.12→3.13 + `requirements.txt` 정확 버전 핀(재현성). 시작 실패 안내·로깅: 실제 .NET/WebView2/보안SW 탐지 후 원인별 분기(_diagnostics) + `userdata/startup_error.log` 기록 + 안내 페이지. (실제 진범은 v1.1.2의 MOTW였음 — 이 로깅 덕에 잡음.)
- **v1.1.0 내용**: FEAT-01 장바구니 DnD+FLIP / FEAT-02 매직 포맷터 매크로+태그칩 / FEAT-03 묵상 노트 **슬라이딩 레일 패널**(독립 카드에서 전환) / FEAT-04 카드별 대조 토글(역본 쌍 고정) / FEAT-05 병렬 복사 부스터 / BUG-01·BUG-i18n·FIX-01 핫픽스 / KJV+ 동봉 + 원전 분해 소스 선택
- **마지막 맵 동기화**: 2026-09-12 (v1.2.0 자막/PPT 화면 + 자동 줄바꿈 엔진 반영)

---

## 1. 디렉토리 트리 구조 요약

```
BibleClip Project/
├─ bibleclip/                      # Python 패키지 (백엔드 + UI)
│  ├─ _version.py                  # 버전 단일 소스 ("1.1.3")
│  ├─ config.py                    # 플랫폼/폰트/경로/GitHub URL/리소스 해석
│  ├─ constants.py                 # 자모맵 + 책이름 테이블(한/영) + 영어역본 set
│  ├─ userconfig.py                # 라이선스 게이트(is_premium) — UI설정과 분리
│  ├─ usage.py                     # 익명 실행 핑(fire-and-forget)
│  ├─ killswitch.py                # 원격 킬스위치(비활성/강제업뎃) — fail-open
│  ├─ korean.py                    # 순수파이썬 한국어 검색 정규화(조사제거/토큰화)
│  ├─ morph.py                     # Kiwi 형태소 토큰화(frozen 빌드 비활성)
│  ├─ i18n.py                      # 백엔드측 i18n (web/locales/*.json 공유)
│  ├─ notes.py                     # 묵상 노트(절-단위 저장, user_notes.json)
│  ├─ highlights.py                # 형광펜(절 내부 문자구간·역본별, user_highlights.json)
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
│     ├─ api.py                    #   Api 브리지 파사드(5개 라우트 믹스인 조합)
│     ├─ dicthtml.py               #   렉시콘 마크업 → HTML 헬퍼
│     ├─ __main__.py               #   python -m bibleclip.webui
│     └─ routes/                   #   JS-호출 가능 브리지 메서드(HTTP 아님)
│        ├─ bible.py               #     성경 탐색/검색/렉시콘 (BibleRoutes)
│        ├─ notes.py               #     묵상 노트 CRUD (NoteRoutes)
│        ├─ highlights.py          #     형광펜 CRUD (HighlightRoutes)
│        ├─ slides.py              #     자막(PPT) 슬라이드·장 탐색·겉모습 (SlideRoutes)
│        └─ system.py              #     부트/설정/업뎃/폰트/출력포맷 (SystemRoutes)
├─ web/                            # ★ 프론트엔드 SPA (vanilla JS, 프레임워크 없음)
│  ├─ index.html                   #   DOM 셸(.rail/.main/뷰/드로어/모달)
│  ├─ cart.html                    #   FEAT-07 설교 장바구니 팝아웃 창(자체완결, v1.1.5)
│  ├─ subtitle.html                #   ★ 자막(PPT) 창(자체완결, v1.2.0) — 빔프로젝터용
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
  - 상태: `dbs`{name:BibleDB}, `bethlehem_strongs`/`bethlehem_wonjun`, `lexicon_ko`/`lexicon_en`, `settings`, `user_config`, `is_premium`, `notes`(Notes), `cart`(Cart, v1.1.4 설교 장바구니 영속성), `_monitor`
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
| `highlights.py` | 형광펜(절 내부 문자구간, v1.1.12) | `HIGHLIGHTS_FILE="user_highlights.json"`, `COLORS=('y','g','b','p')`, `MAX_RANGES=64`, `_norm(ranges)`(정렬·비겹침·색검증·캡); **class `Highlights`**: `get/set_verse/clear_verse(book,chapter,verse,version)`, `for_chapter(book,chapter,version)`, `all()`. 키=`book:chapter:verse:version`(version에 `:` 있어도 `split(':',3)`로 안전). 값=`[{s,e,t,c,ts}]` — s/e=**그 역본 원문**의 문자 오프셋, t=검증용 조각 |
| `cart.py` | 설교 장바구니 영속성(FEAT-08, v1.1.4) | `CART_FILE="sermon_cart.json"`; `_sanitize(items)`; **class `Cart`**: `all()`, `replace(items)`(write-through). localStorage가 랜덤 포트로 휘발하던 문제를 백엔드 파일로 대체 |
| `text_utils.py` | 한글조합/정제/검색 | `convert_qwerty_to_hangul(text)`/`assemble_hangul(jamo)`/`clean_text(text)`/`despace(s)`/`trigrams(s)` |
| `constants.py` | 정적 데이터 | `QWERTY_TO_HANGUL`, `CHOSEONG`/`JUNGSEONG`/`JONGSEONG`, `KOREAN_BOOK_MAP`{name→(id,abbr,full)}, `ENGLISH_BOOK_MAP`, `ENGLISH_VERSIONS`(set) |
| `theme.py` | 색상 팔레트 | `LIGHT_THEME`/`DARK_THEME`/`CTK`(각 (light,dark) 튜플) |
| `update.py` | GitHub 업뎃 체크 | `parse_version(s)`/`urlopen_resilient(req, timeout)`/`fetch_latest_release(timeout=8)`/`select_platform_asset(assets)` |
| `_version.py` | 버전 단일 소스 | `__version__="1.1.5"` |

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
- 기타: `_index_path()`, `_blocked_html`, `_conn_error_html(lang)`, `_on_closing()`(geometry 저장 + **자식 창 일괄 destroy=BUG-SYS v1.1.4**), `_open_popup(title, html)`(생성 창을 `_child_windows`에 추적+`closed`로 자동 해제, 반환), `_conn_watchdog()`(15s ERR_CONNECTION_REFUSED 가이드)
- 상수: `DOTNET_PAGE_URL`, `WEBVIEW2_PAGE_URL`(설치본 자동다운 대신 안내 페이지), `_SECURITY_KW`
- locale: `dotnet.errTitle/errBody`, `webview2.errTitle/errBody`, `secblock.errTitle/errBody`

### webui/api.py — Api 브리지 파사드
- **class `Api(SystemRoutes, BibleRoutes, NoteRoutes, HighlightRoutes, SlideRoutes)`** — `__init__(library)`; `set_window(window)`/`set_popup_factory(factory)`/`_push(fn, *args)`
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
| `get_cart` | `()` | 영속 장바구니 [{book_num,chapter,verses,short_name}] (FEAT-08, v1.1.4) |
| `set_cart` | `(items)` | 전체 교체+저장(write-through) + `_broadcast_cart`로 모든 창 동기화 {ok, items} (FEAT-08/07) |
| `open_cart_window` | `()` | 설교 장바구니 팝아웃 창 열기/포커스 {ok} (FEAT-07, v1.1.5) |
| `cart_goto` | `(book, chapter, verses)` | 팝아웃→메인 뷰어 점프(`_push('cartGoto')`) {ok} (FEAT-07, v1.1.5) |

**HighlightRoutes (`routes/highlights.py`) — 형광펜 CRUD (v1.1.12):**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `get_chapter_highlights` | `(book, chapter, versions)` | {version→{verse→[ranges]}} — **표시 중 역본 전체를 1왕복**(대조/병렬 모드) |
| `get_verse_highlights` | `(book, chapter, verse, version)` | 한 절+역본의 구간 목록 (없으면 `[]`) |
| `set_verse_highlights` | `(book, chapter, verse, version, ranges)` | 전체 교체+저장(빈 목록=삭제). 병합/지우기 의미는 프론트 소유(장바구니와 동일 방식) {ok, ranges} |
| `clear_verse_highlights` | `(book, chapter, verse, version)` | {ok} |
| `get_all_highlights` | `()` | 전체 [{book,chapter,verse,version,s,e,t,c,ts}] (향후 모아보기 훅) |

**SlideRoutes (`routes/slides.py`) — 자막(PPT) 화면 (v1.2.0):**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `open_subtitle_window` / `close_subtitle_window` / `subtitle_window_open` | `()` | 자막 창 열기·닫기·상태 (팩토리 없으면 no-op) |
| `get_slides` | `()` | 띄울 수 있는 슬라이드 = 장바구니 순서 그대로 |
| `get_slide` | `(index=None)` | 슬라이드 → 띄울 글자 `{ref, verses:[{n,text}], version, index, total, page, pages}`. 즉석(F9)이 걸려 있으면 우선(`index:-1`) |
| `set_slide` | `(index)` | 현재 슬라이드 지정(즉석 해제 + 장 초기화) |
| `slide_step` | `(delta)` | ◀▶ — **장 안에서 먼저**, 끝에서 다음 구절. 뒤로는 `page=-1`(=마지막 장) |
| `report_slide_pages` | `(pages)` | 자막 창이 '몇 장인지' 보고(글꼴·창 크기에 달려 백엔드가 알 수 없음) → `page` 클램프 |
| `show_slide_ref` / `clear_slide_adhoc` | `(book, chapter, verses)` / `()` | F9 즉석 슬라이드 설정·해제 |
| `get_subtitle_style` | `()` | `{preset, font_family, font_file}` — 창이 배색·글꼴을 받아간다 |
| `_resolve_slide` / `_broadcast_slide` / `_broadcast_subtitle_style` | (내부) | 장바구니 항목→텍스트 / 슬라이드·겉모습 푸시 |

**SystemRoutes (`routes/system.py`) — 부트/설정/업뎃/폰트/출력포맷:**
| 메서드 | 인자 | 역할 |
|---|---|---|
| `get_initial` | `()` | ★부트 1회 페이로드(versions/primary/viewer/books/last/dark_mode/font_size/lex_lang/ui_lang/reading_font/**view_mode**(v1.1.6)/interlin_sources/is_premium/web_cards_layout/**cart**(v1.1.4)/version…), `_booted` set |
| `get_locale` | `(lang)` | 프론트 i18n 문자열 테이블 |
| `list_fonts` / `get_font` | `()` / `(file)` | 읽기폰트 목록(번들 built-in 나눔고딕/나눔명조 + 사용자 fonts, v1.1.7) / base64 폰트 바이트. 헬퍼 `_builtin_fonts_dir`/`_user_fonts_dir` |
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

- **`_APP_KEYS`**: auto_update_check, search_click_navigates, auto_copy_top_result, lex_lang('ko'/'en'), ui_lang('ko'/'en'), **view_mode('interleave'/'split', v1.1.6)**, reading_font, poll_interval(0.1~2.0), web_cards_layout
- **`_FORMAT_KEYS`**: book_name, chapter_verse_format, bracket_style, ref_position, range_symbol, ref_body_separator, output_mode, newline_show_cv, show_version_header, hide_reference, **custom_format_enabled**, **custom_format_template**(≤500자, FEAT-02)

---

## 8. 프론트엔드 SPA (`web/` — vanilla JS, 프레임워크 없음)

**스크립트 로드 순서(필수)**: `i18n.js` → `core.js` → `cards.js` → `search-notes.js`(끝에서 boot()). ※ **`versebreak.js` 는 이 순서에 들어가지 않는다** — 메인 SPA 가 쓰지 않고 자막 창(`subtitle.html`)만 직접 로드한다(자체완결). 전역 네임스페이스 `window.BC`, `window.I18N`, `CardManager`. 백→프론트 푸시: `window.bibleclip.{onReference, onKeyword, onUpdateProgress, onUpdateReady, onUpdateError}`.

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
- 장 넘기기 책 경계 이월(v1.1.9): `neighborBookChapter(version, book, delta)` — `cardChapStep`이 현재 책의 장 목록을 벗어나면 앞/뒤 책으로 이월(첫 장 `←`→앞 책 **마지막** 장, 마지막 장 `→`→다음 책 **첫** 장). `booksFor`의 정경 순서 **배열 인덱스**로 이동(책 `num`이 10,20,… 비연속이라 산술 불가), 장 없는 책은 스킵, 성경 양 끝은 no-op
- 잠금(N-1 규칙): `toggleLock(card)`/`normalizeLocks()`/`refreshLockStates()`
- 싱크(BUG-01 픽스 + v1.1.6 컬럼 일반화): `anchorVerseOf(el)`/`verseTopFraction(el, n)`/`findVerseEl(el, n)`(결손 절 fallback)/`scrollElToVerse(el, n, guard, align)`(요소 단위·boolean guard)/`syncFrom(card, scrollEl)`(스크롤된 컬럼 드라이버→형제 컬럼+연동 원어 양방향 추종)/`scriptureScrollers(card)`/`primaryScroller(card)`/`linkedInterlinScrollers(card)`/`alignInterlin(card,n,frac)`/`snapshotAnchors()`/`realignAnchors(anchors)`/`lockHistoryVerse(card, el)`(500ms 디바운스). `progScroll`=스크롤 **요소** 단위 가드. 본문 점프 시 원어 카드 타깃 절 추종(1절 고정 버그 해소)
- 렌더: `headerHTML(card)`/`skeleton(card)`/`updateBibleHeader`/`handleAction(card, act, actEl)`/`renderVersesInto(...)`/`renderMultiVersesInto(...)`(절별 대조 세로 교차)/**`renderSplitVersesInto(body, versions, chapDataArr, highlight)`**(v1.1.10 병렬 독서 = 절 단위 행 정렬 `.srow`/`.scell`/sticky `.shead`; v1.1.6~1.1.9의 독립 스크롤 컬럼 `.scol` 대체)/`cardVersions(card)`(=`state.viewer`, 렌더·복사 공유)/`renderInterlinearInto`/`renderLexEntryInto`/`renderMorph` (※ FEAT-04 대조 pill·`"parallel"` 케이스 v1.1.6 제거, `renderNotesInto`/`wireNotes` 폐기)
- **형광펜(v1.1.12)**: `decorateHighlights(card)`(장 단위 fetch→캐시→칠하기, `loadBibleCard`에서 `decorateNotes` **앞**에 호출)/`paintHighlights(card)`(캐시→DOM, 통신 없음·멱등)/`vtxHTML(version, text)`(**`.vtx[data-ver]` 텍스트 래퍼** — 오프셋 기준점)/`hlTextHTML(raw, ranges)`(오프셋→HTML, `t` 검증·재탐색·폐기)/`hlMark`/`hlColor`/`vtxOffset(tx, node, off)`(Range 실측)/`selectionRanges(sec, range)`(드래그→(역본,절)별 구간, 다중 절·다중 컬럼·공백 트림)/`normRanges(list, raw)`/`mergeRange(list, add, raw)`/`subtractRange(list, del, raw)`/`openHlPalette`/`closeHlPalette`/`applyHl(card, targets, color)`/`vtxFor(body, n, ver)`. 상태 `HL_COLORS`/`hlCache`(cardId→{version:{verse:[ranges]}})/`hlPop`. 팔레트는 `document.fullscreenElement || document.body`에 append(F11 필수)
- 이벤트 위임: `wireContainer()` (클릭/스크롤/드래그/contextmenu/hover 단일 핸들러). **드래그 mouseup = 걸친 절 복사(기존) + 형광펜 팔레트(v1.1.12) 동시**, **`.hl-mark` 클릭 = 절 복사 대신 팔레트**(색 변경/지우기)
- public: `{init, addCard, addCardWithLink, goToRef, primaryVersion, primaryBible, bibleCards, lexiconCards, bodyEl, linkedBibleFor, chapStepPrimary, chapStepActive, reloadAllBible, relabel, presentToggle, ensureInterlinearFor, decorateNotesFor:decorateNotes, snapshotAnchors, realignAnchors, **jumpContext**}` — `jumpContext()`(v1.1.14)는 `jumpTarget()`(goToRef 의 대상 선정 로직 분리)이 고른 카드의 `{book, chapter}`

### versebreak.js — ★ 성경 구절 자동 줄바꿈 엔진 (v1.2.0, IIFE `window.VerseBreak`)
자막 창만 로드한다(메인 SPA 무관). **`measure` 를 주입받는 순수 계산 모듈**이라 브라우저 없이 node 로 테스트된다.
- `tokenize(verses)` → `{words, tiers, hard}` — 어절별 끊기 등급 + **문장 경계(강제)** 표시. 절과 절 사이는 최상급 후보
- `wordTier(word)` → 1 종결/2 연결/3 나열·쉼표/4 어절경계. `sentenceEnd(word)` → 강제 줄바꿈 여부(보수적 목록 + 정확일치 예외 + 문장부호)
- `layout(words, tiers, {measure, maxWidth, maxLines, hard})` → DP. **어절 폭 누적합**(`pre[]`)으로 구간 폭 O(1), `hard[j]` 면 그 줄은 거기서 끝
- `plan(verses, o)` = tokenize+layout / `fit(verses, {measureAt, maxWidth, maxHeight, lineHeight, min, max})` = 들어가는 **가장 큰** 글자 크기 이분 탐색
- `paginate(verses, {…, minSize})` → `[{lines, size, verses}]` — 읽을 수 있는 바닥 아래로 내려갈 상황이면 **절 경계에서** 장을 나눔. 호출 수명 측정 캐시(⚠️ 원본 `measureAt` 을 먼저 붙잡아야 함 — `o` 재할당 시 자기 자신을 불러 무한 재귀)
- 상수: `TIER_PENALTY{1:0, 2:60, 3:300, 4:1200}`(⚠️ `||` 폴백 금지 — 최상급이 0 이라 falsy), `RAGGED`(**비율 정규화 필수** — px 로 두면 여백²이 등급 벌점을 압도), `WIDOW_PENALTY`, `SENT_FINAL`/`SENT_EXCEPT`/`SENT_MIN_LEN`

### subtitle.html — 자막(PPT) 창 (v1.2.0, 자체완결)
- 백엔드 푸시 수신: `window.renderSlide(payload)` / `window.applySubtitleStyle({preset, font_family, font_file})`
- `draw()`(paginate→현재 장 렌더→`report_slide_pages`)/`measureAt`(Canvas)/`applyFont`(get_font base64 → 제 문서에 `@font-face`)/`cssFontName`(**화이트리스트** — 블랙리스트는 이스케이프 실수로 정규식이 깨진 적 있음)/`redraw`
- 배색은 `body[data-preset]` CSS 변수. `#page` 는 여러 장일 때만 `2 / 8`. 창 크기 변경 시 줄바꿈 재계산(디바운스 80ms)
- 창 포커스 시 `←/→`·PageUp/Down → `slide_step`

### search-notes.js (~1682줄) — ★ 검색/노트/설정/카트/업뎃/폰트/약칭/라이브i18n
- 노트/절메뉴: `showVerseMenu(card, verse, x, y)`/`openNoteEditor(card, verse)`/`addVerseToCart(card, verse)`/`openOriginalFor(card, verse)`
- **묵상 노트 레일 패널(FEAT-03, 카드→레일 전환)**: `renderNotes()`(API에서 전체 노트 fetch·렌더)/`openNotes()`/`closeNotes()`(로그·카트와 상호배타)/`wireNotesRail()`(토글·새로고침·복사·내보내기·전체선택 바인딩)/`buildNotesText(list)`/`notesTargets()`(선택분 없으면 전체)/`syncNotesSelAll()`/`noteRowKey(n)`. 상태: `notesData[]`/`notesSel`(Set). DOM: `#notes-drawer`/`#notes-list`/`#notes-foot`/`#notes-toggle`/`#notes-close`/`#notes-reload`/`#notes-selall-cb`/`#notes-copy`/`#notes-export`. API: `get_all_notes()`/`copy_text(text)`/`export_text_file(text, filename)`
- 호버툴팁: `scheduleTip(code, verse, book, chapter, x, y)`(400ms)/`hideTip()`
- 업뎃/패치: `checkUpdate(silent)`/`showForcedUpdate(r)`/`maybePatchModal()`/`onUpdateProgress`/`onUpdateReady`/`onUpdateError`/`wireUpdate()`
- 앱설정모달: `openAppSettings()`/`closeAppSettings()`/`setSeg(...)`/`setSwitch(...)`/`wireAppSettings()`/`wireSettingsActions()`
- 버전칩(FLIP애니): `renderVerChips()`/`flipChips(prev)`/`updateViewerVersions(newViewer)`/`wireChipDrag()`/`layoutChipGap(insertIdx)`/`commitChipDrag()`
- 모니터링: `setStatus(active)`/`wireMonitor()`/`logReference(entry)`/`renderLog()`/`flagUnread()`
- **장바구니(FEAT-01 DnD+FLIP, +FEAT-08 영속성 v1.1.4)**: `addToCart(item)`/`removeFromCart(i)`/`clearCart()`/`saveCart()`(**백엔드 `set_cart` write-through + localStorage 캐시**)/`restoreCart(items)`(부팅 시 `get_initial.cart`로 복구, core.js boot에서 호출)/`cartKey(it)`/`renderCart()`/`wireCartDnD(list)`/`flipReorder(list, mutate)`(드래그 중 FLIP 실시간 위치 애니메이션)/`commitCartFromDOM(list)`(DnD 후 DOM 순서→카트 배열 동기화, dragend)/`extractCart(items, allMode)`/`extractAllCart()`/`extractSelectedCart()`/`toggleSelectAll(on)`/`openCart()`/`closeCart()`/`wireCart()`
- **자막(v1.2.0)**: `openSlideInput()`(**F9** — 입력 구절을 자막 창에 즉시 송출, 창이 없으면 함께 열림)/`wireSubtitleToggle()`(레일 `#subtitle-toggle`)/`slideState`(백엔드 `onSlideChanged` 수신). 설정 세그 `#opt-subtitle-preset`
- F2 빠른검색: `openQuickSearch(opts)`(**v1.2.0 일반화** — `{placeholder, onSubmit}`, F2·F9 가 같은 입력창을 공유)/`closeQuickSearch()`/`quickJump(q)`/**`resolveRefInput(q)`**(F2·F9 공통 참조 해석기)/**`relativeRef(q, ctx)`**(v1.1.14 상대 참조 파서 — `resolve_reference` 앞단 가로채기)/`vRange(a,b)`/`verseOnScreen(n)`(DOM 절 존재 확인)
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
- `test_highlights.py` — 형광펜 store(`_norm` 정렬·비겹침·캡, CRUD, **역본 격리**, 장/책 경계, `:` 포함 역본명, 손상 파일·쓰기불가 fail-soft)
- `test_versebreak.js` — 자동 줄바꿈 엔진(**node**, 12개 절: 등급 판정/절 경계/기준 사례(마 18:19-20 = 사람이 만든 슬라이드와 줄 단위 일치)/나열문 구제/**문장 경계 강제 + 오탐 목록**/자동 분할(절 누락·중복 없음, 무한 재귀 방지))
- `test_quickjump_parse.js` — F2 상대 참조 파서(**node**, 33건: 절/범위/장:절/장, 전각 문자, 역순 입력, **건드리면 안 되는 입력 14종이 `null` 로 빠지는지**)
- `test_highlight_ranges.js` — 형광펜 구간 대수(**node**, `node tests/test_highlight_ranges.js`). cards.js 소스에서 `hlColor`/`hlMark`/`hlTextHTML`/`normRanges`/`mergeRange`/`subtractRange` 정의를 **이름으로 잘라 eval** — 로직 복사본을 만들지 않아 갈라지지 않는다. 함수명을 바꾸면 이 테스트가 먼저 실패한다
