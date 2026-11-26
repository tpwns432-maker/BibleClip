// BibleClip iOS — 아이폰에서만 다른 손동작. App.swift 가 mobile.js 뒤에 넣는다. web/ 는 고치지 않는다.
(function () {
  "use strict";

  // 절을 톡 → 그 절 복사(데스크톱과 같은 복사: 알림 · 반짝임 · 참조 기록).
  // 휴대폰 화면(IS_ANDROID)은 탭에 아무 일도 하지 않고 2초 길게 누르기로 메뉴를 열지만,
  // 아이폰은 1초쯤에 iOS 가 글자를 선택하고 팝업을 띄워 그 손동작이 겹친다. 그래서
  // 길게 누르기는 iOS 그대로(글자 선택 · 형광펜) 두고, 절 메뉴는 그 팝업의 '절 메뉴'로 연다.
  // 복사는 절 메뉴(cards.js BibleClipLongHold → search-notes.js showVerseMenu)의 '복사'를
  // 그대로 눌러서 한다 — 같은 함수(copyVersesFromCard)를 타게.
  // 스크롤을 멈추려고 누른 손가락에는 iOS 가 click 을 보내지 않는다.
  document.addEventListener("click", function (e) {
    const t = e.target;
    if (!t || !t.closest) return;
    const v = t.closest('.mcard[data-type="bible"] .v[data-v]');
    if (!v) return;
    // 원어 번호 · 머리 단추 · 칠한 형광펜(팔레트)은 cards.js 가 따로 처리한다.
    if (t.closest("[data-code], [data-act], .hl-mark")) return;
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) return;
    if (!window.BibleClipLongHold || !window.BibleClipLongHold(e.clientX, e.clientY)) return;
    const copy = document.querySelector('.ctx-menu .ctx-item[data-a="copy"]');
    if (copy) copy.dispatchEvent(new MouseEvent("mousedown", { bubbles: true, cancelable: true }));
  }, true);

  // iOS 글자 선택 팝업의 '절 메뉴'(App.swift) — 선택한 글자가 있는 절의 메뉴를 그 자리에 연다.
  window.BibleClipVerseMenuForSelection = function () {
    const sel = window.getSelection();
    if (!sel || !sel.rangeCount) return false;
    const rects = sel.getRangeAt(0).getClientRects();
    const r = rects.length ? rects[0] : sel.getRangeAt(0).getBoundingClientRect();
    return !!(window.BibleClipLongHold && window.BibleClipLongHold(r.left + 2, r.top + r.height / 2));
  };

  // 형광펜 색 줄(cards.js .hl-pal)은 선택한 글자 옆에 뜨는데, iOS 글자 선택 팝업(절 메뉴 · 복사 …)도
  // 같은 자리에 떠서 겹친다. 아이폰에서는 색 줄을 화면 아래 메뉴(nav.rail) 바로 위 가운데로 옮긴다.
  new MutationObserver(function (muts) {
    for (const m of muts) for (const n of m.addedNodes) {
      if (n.nodeType !== 1 || !n.classList.contains("hl-pal")) continue;
      const rail = document.querySelector("nav.rail");
      const floor = rail && rail.getBoundingClientRect().height ? rail.getBoundingClientRect().top : window.innerHeight;
      const r = n.getBoundingClientRect();
      n.style.left = Math.max(6, (window.innerWidth - r.width) / 2) + "px";
      n.style.top = Math.max(6, floor - r.height - 12) + "px";
    }
  }).observe(document.body, { childList: true });
})();
