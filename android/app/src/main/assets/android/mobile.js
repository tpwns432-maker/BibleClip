// BibleClip Android — phone-only behaviour that CSS alone can't do.
// MainActivity injects this after the page's own scripts.
(function () {
  "use strict";

  // The version chips scroll sideways in a fixed one-line row (mobile.css).
  // Fade the edge that hides more chips — only when something is actually
  // hidden there, so a row that fits stays crisp.
  function chipFades() {
    const box = document.getElementById("ver-chips");
    if (!box) return;
    const update = () => {
      const hidden = box.scrollWidth - box.clientWidth;
      box.classList.toggle("fade-l", box.scrollLeft > 1);
      box.classList.toggle("fade-r", hidden - box.scrollLeft > 1);
    };
    box.addEventListener("scroll", update, { passive: true });
    new MutationObserver(update).observe(box, { childList: true, subtree: true, characterData: true });
    if (window.ResizeObserver) new ResizeObserver(update).observe(box);
    update();
  }

  // On-screen keyboard up → the page shrinks and the bottom menu would ride on
  // top of the keyboard, eating the room the results need. Hide it while typing:
  // a text field has focus and the page is clearly shorter than its tallest
  // height in this orientation.
  function keyboardAware() {
    let tallest = window.innerHeight;
    let portrait = window.innerHeight > window.innerWidth;
    const typing = () => {
      const el = document.activeElement;
      return !!el && (el.tagName === "INPUT" || el.tagName === "TEXTAREA" || el.isContentEditable);
    };
    const update = () => {
      const p = window.innerHeight > window.innerWidth;
      if (p !== portrait) { portrait = p; tallest = window.innerHeight; }
      if (!typing()) tallest = Math.max(tallest, window.innerHeight);
      document.documentElement.classList.toggle("kb-open", typing() && window.innerHeight < tallest * 0.8);
    };
    window.addEventListener("resize", update);
    document.addEventListener("focusin", () => setTimeout(update, 300));
    document.addEventListener("focusout", () => setTimeout(update, 300));
  }

  // Desktop-only wording on a phone: no clipboard watching (#키워드 copy), no
  // 원어 codes. Point those elements at the phone strings (web/locales *Phone)
  // before i18n first applies — the page's boot is still awaiting the bridge.
  function phoneStrings() {
    const retarget = (el, attr, key) => { if (el) el.setAttribute(attr, key); };
    retarget(document.getElementById("search-input"), "data-i18n-placeholder", "search.placeholderPhone");
    retarget(document.querySelector('[data-i18n-html="search.empty"]'), "data-i18n-html", "search.emptyPhone");
  }

  function start() {
    phoneStrings();
    chipFades();
    keyboardAware();
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
