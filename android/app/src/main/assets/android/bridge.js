// BibleClip Android — stands in for pywebview's js_api so web/ runs unchanged.
// MainActivity injects this before the first <script> of web/index.html.
// window.pywebview.api.<method>(...args) → Promise, answered by Bridge.kt
// through window.__bibleclipReply(id, ok, value).
(function () {
  "use strict";
  const pending = new Map();
  let nextId = 1;

  window.__bibleclipReply = function (id, ok, value) {
    const p = pending.get(id);
    if (!p) return;
    pending.delete(id);
    if (ok) p.resolve(value);
    else p.reject(new Error(value));
  };

  function call(method, args) {
    return new Promise(function (resolve, reject) {
      const id = nextId++;
      pending.set(id, { resolve: resolve, reject: reject });
      window.BibleClipNative.call(method, JSON.stringify(args), id);
    });
  }

  // Any method name is callable (unknown ones resolve to null on the Kotlin side),
  // so feature checks like `typeof api().save_cards_layout === "function"` pass.
  const api = new Proxy({}, {
    get: function (_, name) {
      if (typeof name !== "string") return undefined;
      return function () { return call(name, Array.prototype.slice.call(arguments)); };
    },
  });

  window.pywebview = { api: api, platform: "android" };
  document.documentElement.classList.add("platform-android");
})();
