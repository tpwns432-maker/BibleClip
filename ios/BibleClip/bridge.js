// BibleClip iOS — pywebview 의 js_api 대신. web/ 를 고치지 않고 그대로 돌린다.
// App.swift 가 web/index.html 의 첫 <script> 앞에 넣는다(android/…/bridge.js 와 같은 일).
// window.pywebview.api.<method>(...args) → Promise. Bridge.swift 가 답한다.
// 인자와 답은 JSON 글로 오간다 — WebKit 의 값 변환(null · bool · 숫자)에 기대지 않으려고.
(function () {
  "use strict";
  const native = window.webkit.messageHandlers.api;

  function call(method, args) {
    return native.postMessage({ method: method, args: JSON.stringify(args) })
      .then(function (r) { return r === undefined || r === null ? null : JSON.parse(r); });
  }

  // 어떤 이름이든 부를 수 있다(모르는 것은 Swift 가 null 로 답한다) — 그래서
  // `typeof api().save_cards_layout === "function"` 같은 기능 확인이 통과한다.
  const api = new Proxy({}, {
    get: function (_, name) {
      if (typeof name !== "string") return undefined;
      return function () { return call(name, Array.prototype.slice.call(arguments)); };
    },
  });

  // 화면은 안드로이드 휴대폰 화면을 그대로 쓴다(core.js IS_ANDROID, mobile.css · mobile.js).
  window.pywebview = { api: api, platform: "android" };
  document.documentElement.classList.add("platform-android", "platform-ios");
})();
