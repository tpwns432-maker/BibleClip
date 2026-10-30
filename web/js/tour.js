// BibleClip web frontend — 첫 실행 안내 투어(스포트라이트 + 설명 말풍선). v1.2.1
// core.js 다음에 로드. 처음 실행하면 자동으로 뜨고, 왼쪽 레일의 ? 아이콘으로 다시 본다.
// "봤음" 표시는 앱 설정 tour_done(bibleclip_settings.json)에 저장한다. 기존 사용자는
// 백엔드가 tour_done=True 로 올려 두므로 업데이트만으로는 뜨지 않는다.
// (맥 테스터가 만든 투어를 바탕으로, 단축키·문구를 OS 별로 나눴다.)
//
// 처음 쓰는 사람 기준: 1부(기본 사용법)는 모니터링 켜기 → 복사 → 붙여넣기를
// 말풍선 안에서 '직접 해 보게' 하고, 끝에서 2부(더 알아보기)로 갈지 고르게 한다.
// 문구의 {copy} {paste} 같은 자리는 render 때 OS 별 키(KEYS)·문장(PLAT)으로 바뀐다.

"use strict";

window.Tour = (() => {
  const KEYS = I18N.IS_MAC ? {
    mod: "<kbd>⌘ command</kbd>", copy: "<kbd>⌘</kbd>+<kbd>C</kbd>", paste: "<kbd>⌘</kbd>+<kbd>V</kbd>",
    present: "<kbd>⌘</kbd>+<kbd>return</kbd>", quick: "<kbd>⌘</kbd>+<kbd>K</kbd>",
    subtitle: "<kbd>⌘</kbd>+<kbd>J</kbd>", enter: "<kbd>return</kbd>", esc: "<kbd>esc</kbd>",
  } : {
    mod: "<kbd>Ctrl</kbd>", copy: "<kbd>Ctrl</kbd>+<kbd>C</kbd>", paste: "<kbd>Ctrl</kbd>+<kbd>V</kbd>",
    present: "<kbd>F11</kbd>", quick: "<kbd>F2</kbd>",
    subtitle: "<kbd>F9</kbd>", enter: "<kbd>Enter</kbd>", esc: "<kbd>Esc</kbd>",
  };
  // OS 마다 다른 문장. 맥만 오른쪽 클릭 방법을 따로 알려 준다.
  const PLAT = {
    ko: {
      rclick: I18N.IS_MAC ? "<b>맥에서 오른쪽 클릭 하는 법:</b> 트랙패드를 <b>두 손가락으로</b> 누르거나, " +
                            "<kbd>control</kbd> 키를 누른 채 클릭하세요.<br>" : "",
    },
    en: {
      rclick: I18N.IS_MAC ? "<b>How to right-click on a Mac:</b> click the trackpad with <b>two fingers</b>, " +
                            "or hold <kbd>control</kbd> and click.<br>" : "",
    },
  };
  const fill = (html) => {
    const plat = PLAT[isEn() ? "en" : "ko"];
    return html.replace(/\{(\w+)\}/g, (m, k) => (k in KEYS ? KEYS[k] : k in plat ? plat[k] : m));
  };

  // target: CSS 선택자 하나 또는 배열(여러 요소를 감싸는 영역). 없으면 화면 가운데.
  // side: 말풍선 위치(bottom/right). optional: 대상이 없으면 그 단계는 건너뜀.
  // part: 1 = 기본 사용법, 2 = 더 알아보기.
  // wait: 직접 해 보기 — "monitor"(모니터링 켜기) / "reference"(구절 인식) / "paste"(붙여넣기).
  //   done 은 성공했을 때 덧붙는 문구. choice: 1부 끝 갈림길(마치기 / 계속).
  const STEPS = [
    // ---------------- 1부: 기본 사용법 ----------------
    {
      part: 1, skipToPart2: true,
      title: "BibleClip에 오신 것을 환영합니다 👋",
      body: "BibleClip은 <b>성경 구절 위치만 복사하면, 그 구절의 말씀 전체로 바꿔 주는</b> 앱입니다.<br>" +
            "예를 들어 <code>요 3:16</code> 을 복사하면 \"하나님이 세상을 이처럼 사랑하사…\" 말씀이 대신 복사돼요. " +
            "설교 원고나 카카오톡에 성경을 일일이 찾아 옮겨 적지 않아도 됩니다.<br><br>" +
            "지금부터 <b>직접 해 보면서</b> 하나씩 알려 드릴게요. 아래 <b>[다음]</b> 버튼을 누르세요.",
      en: { title: "Welcome to BibleClip 👋",
        body: "BibleClip <b>turns a copied Bible reference into the full verse text</b>.<br>" +
              "For example, copy <code>Jn 3:16</code> and \"For God so loved the world…\" is copied instead. " +
              "No more looking up verses and typing them into your sermon notes or chats.<br><br>" +
              "We'll go through it <b>step by step, trying it as we go</b>. Press <b>[Next]</b> below." },
    },
    {
      part: 1, target: ".rail", side: "right",
      title: "화면 둘러보기 ① 왼쪽 메뉴",
      body: "화면 왼쪽의 세로 줄은 <b>메뉴</b>입니다. 아이콘마다 다른 화면이 열려요.<br>" +
            "아이콘 위에 마우스를 잠깐 올려 두면 이름이 나타납니다.<br>" +
            "지금 보고 있는 화면은 맨 위 <b>책 모양</b> 아이콘(성경 보기)입니다.",
      en: { title: "A quick look ① The menu on the left",
        body: "The vertical bar on the left is the <b>menu</b>. Each icon opens a different screen.<br>" +
              "Rest the mouse on an icon for a moment to see its name.<br>" +
              "You are now on the top <b>book</b> icon (the Bible viewer)." },
    },
    {
      part: 1, target: "#panels-container", side: "right", optional: true,
      title: "화면 둘러보기 ② 성경 읽는 곳",
      body: "가운데 넓은 곳에서 성경을 읽습니다. 네모난 칸 하나하나를 <b>카드</b>라고 불러요.<br>" +
            "왼쪽 카드에 <b>성경 본문</b>이, 오른쪽 카드에 <b>원어</b>와 <b>사전</b>이 나옵니다. " +
            "원어와 사전은 몰라도 괜찮아요. 본문만 보셔도 됩니다.",
      en: { title: "A quick look ② Where you read",
        body: "The large area in the middle is where you read. Each box is called a <b>card</b>.<br>" +
              "The left card shows the <b>Bible text</b>; the right cards show the <b>original language</b> and a <b>lexicon</b>. " +
              "You can ignore those two for now — the text card is all you need." },
    },
    {
      part: 1, target: "#monitor-btn", side: "bottom", wait: "monitor",
      title: "직접 해 보기 ① 모니터링 켜기",
      body: "BibleClip이 복사한 글을 알아보려면 먼저 <b>모니터링</b>을 켜야 합니다.<br>" +
            "밝게 표시된 <b>[모니터링 시작]</b> 버튼을 지금 눌러 보세요.",
      done: "✓ 잘하셨어요! 옆의 표시가 초록색 <b>모니터링 중</b>으로 바뀌었죠? " +
            "이제 BibleClip이 복사하는 글을 지켜보고 있습니다.",
      en: { title: "Try it ① Turn on monitoring",
        body: "For BibleClip to notice what you copy, <b>monitoring</b> must be on first.<br>" +
              "Press the highlighted <b>[Start Monitoring]</b> button now.",
        done: "✓ Well done! The badge next to it turned green — <b>Monitoring</b>. " +
              "BibleClip is now watching what you copy." },
    },
    {
      part: 1, wait: "reference",
      title: "직접 해 보기 ② 구절 복사하기",
      body: "이제 구절 위치를 복사해 볼게요. 아래 칸의 글자가 미리 <b>선택</b>되어 있습니다.<br>" +
            "키보드의 {mod} 키를 누른 채로 <kbd>C</kbd> 를 누르세요. 이것이 <b>복사</b>입니다.",
      done: "✓ 성공! BibleClip이 구절을 알아보고, 복사해 둔 내용(클립보드)을 " +
            "<b>말씀 본문으로 바꿨어요</b>. 뒤쪽 성경 카드도 요한복음 3장으로 이동했습니다.",
      en: { title: "Try it ② Copy a reference",
        body: "Now let's copy a reference. The text in the box below is already <b>selected</b>.<br>" +
              "Hold the {mod} key and press <kbd>C</kbd>. That is <b>copy</b>.",
        done: "✓ It worked! BibleClip recognized the reference and <b>replaced what you copied " +
              "(the clipboard) with the verse text</b>. The Bible card behind also moved to John 3." },
    },
    {
      part: 1, wait: "paste",
      title: "직접 해 보기 ③ 붙여넣기",
      body: "이제 붙여넣어 볼게요. 아래 빈칸을 <b>한 번 클릭</b>한 뒤, " +
            "{mod} 키를 누른 채로 <kbd>V</kbd> 를 누르세요. 이것이 <b>붙여넣기</b>입니다.",
      done: "✓ 보이시나요? <code>요 3:16</code> 대신 <b>말씀 전체</b>가 들어왔습니다.<br>" +
            "메모, 카카오톡, 한글, 워드 등 <b>어디에서나 똑같이</b> 됩니다.",
      en: { title: "Try it ③ Paste",
        body: "Now let's paste. <b>Click once</b> in the empty box below, " +
              "then hold {mod} and press <kbd>V</kbd>. That is <b>paste</b>.",
        done: "✓ See? Instead of <code>Jn 3:16</code>, the <b>whole verse</b> came in.<br>" +
              "It works the same way <b>anywhere</b> — Notes, chat apps, Pages, Word." },
    },
    {
      part: 1,
      title: "이런 표기를 알아봅니다",
      body: "• 한 절: <code>요 3:16</code> · <code>요3:16</code> · <code>요한복음 3장 16절</code><br>" +
            "• 여러 절: <code>창 1:1-3</code> · <code>시 23:1~6</code><br>" +
            "• 띄엄띄엄: <code>요 1:1-2,4-6</code><br>" +
            "• 영어: <code>John 3:16</code> · <code>Gen 1:1</code><br>" +
            "평범한 문장이나 시간(<code>3:30에 만나요</code>)은 건드리지 않으니 안심하세요.<br><br>" +
            "모니터링은 <b>켜 두기만</b> 하면 됩니다. 끄고 싶을 때는 같은 버튼(<b>모니터링 중지</b>)을 누르세요.",
      en: { title: "References it understands",
        body: "• One verse: <code>Jn 3:16</code> · <code>John 3:16</code> · <code>요 3:16</code><br>" +
              "• Several verses: <code>Gen 1:1-3</code> · <code>Ps 23:1~6</code><br>" +
              "• Gaps: <code>Jn 1:1-2,4-6</code><br>" +
              "Ordinary sentences and times (<code>see you at 3:30</code>) are left alone.<br><br>" +
              "Just <b>leave monitoring on</b>. To turn it off, press the same button (<b>Stop Monitoring</b>)." },
    },
    {
      part: 1, target: '.mcard[data-type="bible"] .card-hd', side: "bottom", optional: true,
      title: "성경 넘겨 보기",
      body: "카드 맨 위 줄에서 <b>책 이름</b>(예: <code>요</code>)을 누르면 성경 66권 목록이, " +
            "<b>장</b>(예: <code>3장</code>)을 누르면 장 번호 목록이 나옵니다.<br>" +
            "<b>‹ ›</b> 는 이전 장 · 다음 장, <b>◀ ▶</b> 는 방금 보던 곳으로 돌아가기입니다.<br>" +
            "키보드 <kbd>←</kbd> <kbd>→</kbd> 로도 장을 넘길 수 있어요.",
      en: { title: "Turning pages",
        body: "In the top line of the card, press the <b>book name</b> to pick from all 66 books, " +
              "or the <b>chapter</b> to pick a chapter.<br>" +
              "<b>‹ ›</b> go to the previous / next chapter; <b>◀ ▶</b> go back to where you just were.<br>" +
              "The <kbd>←</kbd> <kbd>→</kbd> keys also turn chapters." },
    },
    {
      part: 1, target: '.mcard[data-type="bible"] .card-body', side: "right", optional: true,
      title: "읽다가 바로 복사하기",
      body: "본문에서 마음에 드는 절을 <b>한 번 클릭</b>하면 그 절이 바로 복사됩니다.<br>" +
            "여러 절을 마우스로 <b>끌어서 선택</b>하면 그 범위가 한꺼번에 복사돼요.<br>" +
            "복사되면 화면 아래에 \"복사됨\" 알림이 잠깐 뜹니다.",
      en: { title: "Copy while you read",
        body: "<b>Click a verse once</b> and it is copied right away.<br>" +
              "<b>Drag across</b> several verses to copy them all at once.<br>" +
              "A short \"Copied\" message appears at the bottom when it works." },
    },
    {
      part: 1, target: ["#ver-chips", "#ver-add"], side: "bottom",
      title: "다른 번역 같이 보기",
      body: "<b>＋</b> 를 누르면 개역개정, 영어 성경 같은 <b>다른 번역</b>을 더할 수 있어요. " +
            "목록은 언어별로 묶여 있습니다.<br>" +
            "더한 번역은 절마다 나란히 보이고, 번역 이름 옆 <b>✕</b> 로 다시 뺄 수 있습니다.",
      en: { title: "Read other translations side by side",
        body: "Press <b>＋</b> to add <b>another translation</b> (other Korean or English Bibles, …). " +
              "The list is grouped by language.<br>" +
              "Added translations appear verse by verse side by side; press <b>✕</b> on a name to remove it." },
    },
    {
      part: 1, choice: true,
      title: "기본은 여기까지예요 🎉",
      body: "지금까지 배운 것만으로도 BibleClip을 충분히 쓸 수 있습니다.<br>" +
            "<b>① 모니터링 시작 → ② 구절 복사({copy}) → ③ 붙여넣기({paste})</b><br><br>" +
            "검색, 설교 장바구니, 예배 자막 같은 기능도 이어서 볼까요?<br>" +
            "나중에 왼쪽 아래 <b>?</b> 아이콘을 누르면 언제든 다시 볼 수 있어요.",
      en: { title: "That's the basics 🎉",
        body: "What you've learned is enough to use BibleClip every day.<br>" +
              "<b>① Start Monitoring → ② copy a reference ({copy}) → ③ paste ({paste})</b><br><br>" +
              "Would you like to see search, the sermon cart and worship subtitles too?<br>" +
              "You can replay this tour any time with the <b>?</b> icon at the bottom left." },
    },

    // ---------------- 2부: 더 알아보기 ----------------
    {
      part: 2, target: "#nav-search", side: "right",
      title: "단어로 찾기 (검색)",
      body: "<b>돋보기</b> 아이콘을 누르면 검색 화면이 열립니다.<br>" +
            "<code>사랑</code> 처럼 단어를 넣고 {enter} 키를 누르면 그 단어가 나오는 구절이 모두 나와요. " +
            "결과를 클릭하면 그 구절이 복사됩니다.<br>" +
            "팁: 모니터링 중에 <code>#사랑</code> 처럼 앞에 <b>#</b>을 붙여 복사해도 바로 검색됩니다.",
      en: { title: "Find by word (search)",
        body: "The <b>magnifying glass</b> icon opens search.<br>" +
              "Type a word like <code>love</code> and press {enter} to list every verse with it. " +
              "Click a result to copy that verse.<br>" +
              "Tip: while monitoring, copying a word with <b>#</b> in front (<code>#love</code>) searches too." },
    },
    {
      part: 2, target: "#nav-settings", side: "right",
      title: "복사되는 모양 바꾸기 (출력 설정)",
      body: "<b>슬라이더</b> 모양 아이콘에서 복사될 글의 모양을 정합니다.<br>" +
            "예: 책 이름을 <code>요</code> 로 쓸지 <code>요한복음</code> 으로 쓸지, 절마다 줄을 바꿀지 등.<br>" +
            "화면 아래 <b>미리보기</b>에 결과가 바로 보이니, 하나씩 눌러 보며 마음에 드는 모양을 고르세요.",
      en: { title: "Change how verses are copied (Output Settings)",
        body: "The <b>sliders</b> icon sets how copied verses look.<br>" +
              "For example: short or full book names, one line per verse, and so on.<br>" +
              "The <b>preview</b> at the bottom updates right away, so try options until you like it." },
    },
    {
      part: 2, target: "#log-toggle", side: "right",
      title: "복사 기록 다시 보기",
      body: "<b>클립보드</b> 모양 아이콘을 누르면 지금까지 알아본 구절이 목록으로 나옵니다.<br>" +
            "목록의 구절을 누르면 다시 복사되고 그 본문으로 이동해요.",
      en: { title: "See what you copied",
        body: "The <b>clipboard</b> icon lists every reference recognized so far.<br>" +
              "Click one to copy it again and jump to that passage." },
    },
    {
      part: 2, target: "#cart-toggle", side: "right",
      title: "설교 장바구니",
      body: "설교에 쓸 구절을 미리 모아 두는 곳입니다.<br>" +
            "본문에서 절을 <b>오른쪽 클릭</b>한 뒤 <b>장바구니에 담기</b>를 고르세요.<br>" +
            "{rclick}" +
            "장바구니 아이콘을 누르면 담은 구절을 보고, <b>전체 추출</b>로 한 번에 복사할 수 있어요.",
      en: { title: "Sermon cart",
        body: "Collect the verses you'll use in a sermon.<br>" +
              "<b>Right-click</b> a verse and choose <b>Add to cart</b>.<br>" +
              "{rclick}" +
              "The cart icon shows what you collected; <b>Extract all</b> copies everything at once." },
    },
    {
      part: 2, target: "#notes-toggle", side: "right",
      title: "묵상 노트 · 형광펜",
      body: "절을 오른쪽 클릭 → <b>묵상 노트 쓰기</b>로 그 절에 메모를 남길 수 있고, " +
            "이 <b>노트</b> 아이콘에서 모아 봅니다.<br>" +
            "본문 글자를 마우스로 <b>끌어서 선택</b>하면 색깔 동그라미가 나타나요. " +
            "색을 누르면 <b>형광펜</b>이 칠해집니다.",
      en: { title: "Meditation notes · highlighter",
        body: "Right-click a verse → <b>Write a note</b> to attach a note to it; " +
              "this <b>notes</b> icon gathers them all.<br>" +
              "<b>Drag across</b> some text and coloured dots appear — " +
              "pick a colour to <b>highlight</b> it." },
    },
    {
      part: 2, target: "#subtitle-toggle", side: "right",
      title: "예배 자막 띄우기",
      body: "<b>프로젝터</b> 모양 아이콘을 누르면 <b>자막 창</b>이 열립니다. " +
            "이 창을 빔프로젝터(바깥 화면) 쪽으로 끌어다 놓으세요.<br>" +
            "{subtitle} 키를 누르고 <code>마 18:19-20</code> 처럼 입력한 뒤 {enter} 키를 누르면 " +
            "그 구절이 자막에 뜹니다.<br>" +
            "자막 창을 클릭한 뒤 <kbd>←</kbd> <kbd>→</kbd> 로 다음 화면으로 넘겨요. 장바구니에 담은 순서대로도 넘어갑니다.",
      en: { title: "Worship subtitles",
        body: "The <b>projector</b> icon opens the <b>subtitle window</b>. " +
              "Drag that window onto the projector (external) screen.<br>" +
              "Press {subtitle}, type a reference like <code>Mt 18:19-20</code> and press {enter} " +
              "to show it as a subtitle.<br>" +
              "Click the subtitle window and use <kbd>←</kbd> <kbd>→</kbd> to move on — it also steps through your cart in order." },
    },
    {
      part: 2, target: '.mcard[data-type="bible"]', side: "right", optional: true,
      title: "본문을 화면 가득 띄우기 (발표)",
      body: "성경 카드를 한 번 클릭해 고른 뒤 {present} 키를 누르면 " +
            "그 본문이 <b>화면 가득</b> 커집니다. 나갈 때는 {esc} 키.<br>" +
            "크게 띄운 상태에서 {quick} 키를 누르고 구절을 입력하면 바로 그 구절로 이동합니다. " +
            "<kbd>+</kbd> <kbd>−</kbd> 로 글자 크기를 바꿔요.",
      en: { title: "Show the text full screen (presentation)",
        body: "Click a Bible card once, then press {present} " +
              "to fill the <b>whole screen</b> with it. Press {esc} to exit.<br>" +
              "While full screen, press {quick} and type a reference to jump straight to it. " +
              "<kbd>+</kbd> <kbd>−</kbd> change the text size." },
    },
    {
      part: 2, target: ["#add-bible", "#add-inter", "#add-lex", "#font-dec", "#font-inc"], side: "bottom",
      title: "카드 더하기 · 글자 크기",
      body: "<b>＋ 본문 · ＋ 원어 · ＋ 사전</b> 으로 카드를 더 띄울 수 있어요(본문 카드는 4개까지).<br>" +
            "카드 맨 위 줄을 끌면 카드가 옮겨지고, 카드 가장자리를 끌면 크기가 바뀝니다. " +
            "카드 오른쪽 위 <b>✕</b> 로 닫아요.<br>" +
            "<b>A− / A+</b> 는 본문 글자 크기입니다.",
      en: { title: "More cards · text size",
        body: "<b>＋ Text · ＋ Original · ＋ Lexicon</b> open more cards (up to 4 text cards).<br>" +
              "Drag a card's top line to move it, drag its edges to resize it, " +
              "and press <b>✕</b> at its top right to close it.<br>" +
              "<b>A− / A+</b> change the text size." },
    },
    {
      part: 2, target: '.mcard[data-type="interlinear"]', side: "right", optional: true,
      title: "원어 공부",
      body: "원어 카드에는 단어마다 <b>H…</b>(히브리어) / <b>G…</b>(헬라어) 번호가 붙어 있어요(스트롱 번호).<br>" +
            "번호를 누르면 <b>사전</b> 카드에 그 단어의 뜻이 나옵니다. " +
            "단어에 마우스를 올리면 짧은 미리보기가 떠요.",
      en: { title: "Original-language study",
        body: "The interlinear card puts an <b>H…</b> (Hebrew) / <b>G…</b> (Greek) number on each word (Strong's numbers).<br>" +
              "Click a number to see the word's meaning in the <b>Lexicon</b> card. " +
              "Rest the mouse on a word for a quick preview." },
    },
    {
      part: 2, target: ["#theme-toggle", "#nav-app-settings"], side: "right",
      title: "화면 색 · 앱 설정 · 성경 추가",
      body: "<b>달</b> 아이콘으로 밝은 화면 / 어두운 화면을 바꿉니다.<br>" +
            "<b>톱니바퀴</b> 아이콘에서 화면 언어(한국어/English), 글꼴 등을 바꿔요.<br>" +
            "새 성경 파일(.SQLite3)을 넣으려면: <b>설정 ▸ [데이터 폴더 열기]</b>로 열린 폴더의 " +
            "<b>bible_versions</b> 폴더(없으면 만드세요)에 넣고, <b>출력 설정 ▸ [DB 새로고침]</b>을 누르세요.",
      en: { title: "Colours · app settings · adding Bibles",
        body: "The <b>moon</b> icon switches between a light and a dark screen.<br>" +
              "The <b>gear</b> icon changes the display language (한국어/English), fonts and more.<br>" +
              "To add a Bible file (.SQLite3): open <b>Settings ▸ [Open data folder]</b>, put it in the " +
              "<b>bible_versions</b> folder there (create it if missing), then press <b>Output Settings ▸ [Refresh DB]</b>." },
    },
    {
      part: 2, target: "#tour-help", side: "right",
      title: "다 보셨습니다! 🎉",
      body: "이 <b>?</b> 아이콘을 누르면 이 안내를 언제든 다시 볼 수 있습니다.<br>" +
            "더 자세한 설명은 함께 드린 <b>사용법</b> 문서를 참고하세요.<br>" +
            "자주 쓰는 순서: <b>모니터링 시작</b> → 구절 복사 {copy} → 붙여넣기 {paste}",
      en: { title: "You're all set! 🎉",
        body: "Press this <b>?</b> icon to see this tour again at any time.<br>" +
              "For more details, see the included <b>user guide</b>.<br>" +
              "Everyday flow: <b>Start Monitoring</b> → copy a reference {copy} → paste {paste}" },
    },
  ];

  // 화면 언어(설정 ▸ 표시 언어)를 따라간다. 단계 문구는 en 이 있으면 영어, 없으면 한국어.
  const UI = {
    ko: { skip: "건너뛰기", prev: "이전", next: "다음", done: "시작하기", part1: "기본 사용법", part2: "더 알아보기",
          finish: "여기서 마치기", more: "더 알아보기 →", toPart2: "이미 알아요 · 더 알아보기로",
          copyFallback: "잘 안 되면 여기를 눌러 대신 복사하기", pastePh: "여기를 클릭하고 " + (I18N.IS_MAC ? "⌘ + V" : "Ctrl + V"),
          waitMonitor: "※ 먼저 앞 단계에서 <b>모니터링 시작</b>을 눌러야 해요. [이전]으로 돌아가 켜 주세요.",
          practice: "요 3:16" },
    en: { skip: "Skip", prev: "Back", next: "Next", done: "Get started", part1: "Basics", part2: "More features",
          finish: "Finish here", more: "More features →", toPart2: "I know the basics · skip ahead",
          copyFallback: "Not working? Click here to copy it for you", pastePh: "Click here, then " + (I18N.IS_MAC ? "⌘ + V" : "Ctrl + V"),
          waitMonitor: "※ <b>Start Monitoring</b> must be on first. Go [Back] and turn it on.",
          practice: "Jn 3:16" },
  };
  const isEn = () => !!(window.I18N && I18N.getLang() === "en");
  const ui = () => UI[isEn() ? "en" : "ko"];

  let idx = 0, active = [], els = null, doneFlag = false, poll = null;

  function rectOf(target) {
    const sels = Array.isArray(target) ? target : [target];
    const rs = sels.map((s) => document.querySelector(s))
      .filter((el) => el && el.offsetParent !== null)
      .map((el) => el.getBoundingClientRect())
      .filter((r) => r.width > 0 && r.height > 0);
    if (!rs.length) return null;
    const l = Math.min(...rs.map((r) => r.left)), t = Math.min(...rs.map((r) => r.top));
    const r = Math.max(...rs.map((x) => x.right)), b = Math.max(...rs.map((x) => x.bottom));
    return { left: l, top: t, width: r - l, height: b - t, right: r, bottom: b };
  }

  function build() {
    const back = document.createElement("div");
    back.className = "tour-back";
    const spot = document.createElement("div");
    spot.className = "tour-spot";
    const tip = document.createElement("div");
    tip.className = "tour-tip";
    tip.setAttribute("role", "dialog");
    document.body.append(back, spot, tip);
    back.addEventListener("mousedown", (e) => e.preventDefault());
    tip.addEventListener("click", (e) => {
      const act = e.target.closest("[data-tour]");
      if (!act) return;
      const a = act.dataset.tour;
      if (a === "next") go(1);
      else if (a === "prev") go(-1);
      else if (a === "part2") jumpToPart(2);
      else if (a === "copy") copyPractice();
      else finish();
    });
    return { back, spot, tip };
  }

  // 복사 키가 어려운 사람용 '대신 복사하기'. 맥 WKWebView 는 document.execCommand("copy")
  // 를 막아서, 앱의 복사 경로(copy_reference)로 요 3:16 본문을 직접 클립보드에 넣고
  // 인식됐을 때와 같은 결과(카드 이동 + 성공 표시)를 보여 준다.
  async function copyPractice() {
    try { await api().copy_reference(500, 3, [16]); } catch (_) {}
    CardManager.goToRef(500, 3, [16]);
    markDone();
  }

  function stopWait() {
    if (poll) { clearInterval(poll); poll = null; }
    document.removeEventListener("bc:reference", onRef);
  }
  function markDone() {
    if (doneFlag || !els) return;
    doneFlag = true;
    stopWait();
    render();
  }
  function onRef() { markDone(); }

  function startWait(step) {
    stopWait();
    doneFlag = false;
    if (step.wait === "monitor") {
      if (state.monitoring) { doneFlag = true; return; }
      poll = setInterval(() => { if (state.monitoring) markDone(); }, 250);
    } else if (step.wait === "reference") {
      document.addEventListener("bc:reference", onRef);
      // 모니터링이 꺼져 있으면 '먼저 켜세요' 안내를 보인다(켜지면 숨김).
      poll = setInterval(() => {
        const h = els && els.tip.querySelector(".tour-hint");
        if (h) h.hidden = !!state.monitoring;
      }, 500);
    }
  }

  function render() {
    const step = active[idx];
    const r = step.target ? rectOf(step.target) : null;
    const { spot, tip, back } = els;
    const t = isEn() && step.en ? step.en : step;
    const u = ui();
    const partSteps = active.filter((s) => s.part === step.part);
    const pos = partSteps.indexOf(step) + 1;
    const last = idx === active.length - 1;

    let practice = "";
    if (step.wait === "reference" && !doneFlag) {
      practice =
        `<input class="tour-practice" type="text" readonly value="${u.practice}">` +
        `<button class="tour-link" data-tour="copy">${u.copyFallback}</button>` +
        `<div class="tour-hint"${state.monitoring ? " hidden" : ""}>${u.waitMonitor}</div>`;
    } else if (step.wait === "paste") {
      practice = `<textarea class="tour-paste" rows="3" placeholder="${u.pastePh}"></textarea>`;
    }
    const doneHtml = step.wait && doneFlag && t.done ? `<div class="tour-done">${fill(t.done)}</div>` : "";

    let foot;
    if (step.choice) {
      foot = `<button class="btn" data-tour="skip">${u.finish}</button>` +
             `<span class="tour-spacer"></span>` +
             `<button class="btn" data-tour="prev">${u.prev}</button>` +
             `<button class="btn primary" data-tour="next">${u.more}</button>`;
    } else {
      foot = (last ? "" : `<button class="btn tour-skip" data-tour="skip">${u.skip}</button>`) +
             (step.skipToPart2 ? `<button class="btn tour-skip" data-tour="part2">${u.toPart2}</button>` : "") +
             `<span class="tour-spacer"></span>` +
             (idx > 0 ? `<button class="btn" data-tour="prev">${u.prev}</button>` : "") +
             `<button class="btn primary${step.wait && doneFlag ? " tour-pulse" : ""}" data-tour="next">${last ? u.done : u.next}</button>`;
    }

    // 붙여넣기 단계는 성공 문구를 그릴 때 이미 붙여넣은 글을 지우지 않게 값을 보존한다.
    const prevPaste = tip.querySelector(".tour-paste");
    const keepPaste = prevPaste ? prevPaste.value : "";

    tip.innerHTML =
      `<div class="tour-count">${step.part === 1 ? u.part1 : u.part2} · ${pos} / ${partSteps.length}</div>` +
      `<div class="tour-title">${t.title}</div>` +
      `<div class="tour-body">${fill(t.body)}</div>` +
      practice + doneHtml +
      `<div class="tour-foot">${foot}</div>`;

    const pa = tip.querySelector(".tour-paste");
    if (pa && keepPaste) pa.value = keepPaste;

    // 직접 해 보기(모니터링 버튼 누르기) 단계는 강조된 버튼을 실제로 누를 수 있어야 한다.
    back.style.pointerEvents = step.wait === "monitor" ? "none" : "";

    // 대상 없음 → 어둡게 깐 배경 + 가운데 말풍선. 대상 있음 → 구멍 뚫린 스포트라이트.
    back.classList.toggle("dim", !r);
    spot.hidden = !r;
    const pad = 6, gap = 14, W = window.innerWidth, H = window.innerHeight;
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let left, top;
    if (!r) {
      left = (W - tw) / 2; top = (H - th) / 2;
    } else {
      Object.assign(spot.style, {
        left: r.left - pad + "px", top: r.top - pad + "px",
        width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px",
      });
      if (step.side === "right" && r.right + pad + gap + tw < W) {
        left = r.right + pad + gap; top = r.top + r.height / 2 - th / 2;
      } else if (r.bottom + pad + gap + th < H) {
        left = r.left + r.width / 2 - tw / 2; top = r.bottom + pad + gap;
      } else if (r.top - pad - gap - th > 0) {
        left = r.left + r.width / 2 - tw / 2; top = r.top - pad - gap - th;
      } else {
        // 큰 대상(카드 영역 등): 위·아래에 자리가 없으면 대상 안쪽 아래에 겹쳐 둔다.
        left = r.left + r.width / 2 - tw / 2; top = r.bottom - th - 16;
      }
    }
    tip.style.left = Math.max(12, Math.min(left, W - tw - 12)) + "px";
    tip.style.top = Math.max(12, Math.min(top, H - th - 12)) + "px";

    // 연습 칸 포커스: 복사 단계는 글자를 미리 선택해 ⌘C 만 누르면 되게, 붙여넣기 단계는
    // 빈칸에 커서를 둔다. 그 밖에는 [다음] 버튼에 포커스(return 키로 넘기기).
    const pr = tip.querySelector(".tour-practice");
    if (pr) { pr.focus(); pr.select(); }
    else if (pa && !doneFlag) {
      pa.focus();
      pa.addEventListener("input", () => { if (pa.value.trim().length > 12) markDone(); });
    } else {
      const nextBtn = tip.querySelector('[data-tour="next"]');
      if (nextBtn) nextBtn.focus();
    }
  }

  function show(n) {
    idx = n;
    startWait(active[idx]);
    render();
  }

  function go(d) {
    const n = idx + d;
    if (n >= active.length) { finish(); return; }
    if (n < 0) return;
    show(n);
  }

  function jumpToPart(p) {
    const n = active.findIndex((s) => s.part === p);
    if (n >= 0) show(n);
  }

  function onKey(e) {
    // 연습 칸에서는 ⌘C / ⌘V 와 글자 입력을 그대로 통과시킨다.
    const inField = e.target.closest && e.target.closest(".tour-practice, .tour-paste");
    if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); finish(); }
    else if (inField) return;
    else if (e.key === "ArrowRight" || e.key === "Enter") {
      if (e.metaKey) return;
      e.preventDefault(); e.stopPropagation(); go(1);
    }
    else if (e.key === "ArrowLeft") { e.preventDefault(); e.stopPropagation(); go(-1); }
  }
  const onResize = () => { if (els) render(); };

  function start() {
    if (els) return;
    // 투어는 성경 보기 화면 기준으로 설명한다.
    const viewer = document.getElementById("nav-viewer");
    if (viewer && !viewer.classList.contains("on")) viewer.click();
    if (typeof closeMenus === "function") closeMenus();
    // 카드를 닫는 등 hover 대상이 사라지면 앱 말풍선이 남아 투어 위에 겹친다.
    if (typeof hideTooltip === "function") hideTooltip();
    active = STEPS.filter((s) => !s.optional || rectOf(s.target));
    els = build();
    // capture 단계에서 키를 먼저 잡아 카드의 ←/→ 장 넘김과 겹치지 않게 한다.
    window.addEventListener("keydown", onKey, true);
    window.addEventListener("resize", onResize);
    show(0);
  }

  function finish() {
    if (!els) return;
    stopWait();
    Object.values(els).forEach((el) => el.remove());
    els = null;
    window.removeEventListener("keydown", onKey, true);
    window.removeEventListener("resize", onResize);
    if (!state.tourDone) {
      state.tourDone = true;
      try { api().set_app_setting("tour_done", true); } catch (_) {}
    }
  }

  // 첫 실행이면 자동 시작. 업데이트 안내 창(patch notes)이 떠 있으면 닫힐 때까지 기다린다.
  function maybeAutoStart() {
    if (state.tourDone) return;
    const wait = () => {
      if (document.querySelector(".note-modal-back")) setTimeout(wait, 500);
      else start();
    };
    setTimeout(wait, 600);
  }

  function wire() {
    const btn = document.getElementById("tour-help");
    if (btn) btn.addEventListener("click", start);
  }

  return { start, finish, maybeAutoStart, wire };
})();
