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

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", chipFades);
  else chipFades();
})();
