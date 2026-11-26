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
      copySelection();
    }
  }).observe(document.body, { childList: true });

  // 글자 선택 → 걸친 절들 복사(데스크톱의 '드래그 → 복사'와 같은 결과).
  // 데스크톱은 마우스를 뗄 때 복사하지만 손가락 선택은 손잡이로 늘이고 줄여서 그 순간이 없다 —
  // 선택이 멈춰 색 줄이 뜰 때(cards.js 가 selectionchange 를 0.45초 기다린 뒤) 복사한다.
  // 같은 절들이면 다시 복사하지 않는다(손잡이를 조금 움직일 때마다 알림이 뜨지 않게).
  // cards.js 의 copyVersesFromCard 는 밖에서 부를 수 없어 같은 일을 여기서 한다(참조 기록만 빠짐).
  let lastKey = "";
  document.addEventListener("selectionchange", function () {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed) lastKey = "";
  });
  async function copySelection() {
    const BC = window.BC, sel = window.getSelection();
    if (!BC || !BC.CardManager || !sel || sel.isCollapsed || !sel.rangeCount) return;
    const range = sel.getRangeAt(0);
    const node = range.commonAncestorContainer;
    const host = node.nodeType === 1 ? node : node.parentElement;
    const sec = host && host.closest('.mcard[data-type="bible"]');
    const card = sec && BC.CardManager.cardFor(sec.dataset.id);
    if (!card) return;
    const verses = [...new Set([...sec.querySelectorAll(".v[data-v]")]
      .filter(function (el) { return range.intersectsNode(el); })
      .map(function (el) { return +el.dataset.v; }))].sort(function (a, b) { return a - b; });
    if (!verses.length) return;
    const key = card.id + "|" + card.book + "|" + card.chapter + "|" + verses.join(",");
    if (key === lastKey) return;
    lastKey = key;
    const st = BC.state;
    const versions = st.viewer.length ? st.viewer.slice() : [st.viewer[0] || st.primary].filter(Boolean);
    let r;
    try { r = await BC.api().copy_reference(card.book, card.chapter, verses, versions); } catch (_) { return; }
    if (!r || !r.ok) return;
    const ref = (r.short_name || "") + " " + card.chapter + ":" + verses.join(",");
    const wrap = document.getElementById("toast-wrap");
    if (wrap) {
      const el = document.createElement("div");
      el.className = "toast";
      el.textContent = window.I18N ? window.I18N.t("toast.copiedRef", { ref: ref }) : ref;
      wrap.appendChild(el);
      setTimeout(function () { el.classList.add("fade"); setTimeout(function () { el.remove(); }, 320); }, 2400);
    }
    verses.forEach(function (v) {
      sec.querySelectorAll('.v[data-v="' + v + '"]').forEach(function (el) {
        el.classList.add("copied"); setTimeout(function () { el.classList.remove("copied"); }, 700);
      });
    });
  }
})();
