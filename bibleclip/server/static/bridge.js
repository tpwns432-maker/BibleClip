// BibleClip 웹판 — pywebview 의 js_api 자리를 대신해 web/ 가 그대로 돌게 한다.
// 서버가 index.html 의 첫 <script> 앞에 끼운다(bibleclip/server/app.py).
// window.pywebview.api.<기능>(...인자) → Promise. POST /api/<기능> {args} → {value}.
// 폰판(android/bridge.js)과 같은 모양이다.
(function () {
  "use strict";

  function call(method, args) {
    return fetch("api/" + encodeURIComponent(method), {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-BibleClip": "1" },
      body: JSON.stringify({ args: args }),
      credentials: "same-origin",
    }).then(function (res) {
      if (res.status === 401) toLogin();     // 로그인이 풀림(비밀번호 변경 · 30일 지남)
      return res.json().catch(function () { return {}; }).then(function (body) {
        if (!res.ok) throw new Error(body.error || ("HTTP " + res.status));
        return body.value === undefined ? null : body.value;
      });
    });
  }

  // ---- 브라우저가 맡는 일: 클립보드 · 파일 저장 · 새 창 ----

  function copyToClipboard(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      // 권한 묻기 등으로 답이 늦으면 옛 방식으로(복사 단추가 멈춘 듯 보이지 않게).
      const late = new Promise(function (r) { setTimeout(function () { r("late"); }, 1500); });
      return Promise.race([navigator.clipboard.writeText(text).then(function () { return true; }), late])
        .then(function (r) { return r === "late" ? fallbackCopy(text) : true; },
          function () { return fallbackCopy(text); });
    }
    return Promise.resolve(fallbackCopy(text));
  }
  function fallbackCopy(text) {       // http(보안 연결 아님)에서도 되게
    const ta = document.createElement("textarea");
    ta.value = text;
    ta.setAttribute("readonly", "");
    ta.style.cssText = "position:fixed;top:-1000px;opacity:0";
    document.body.appendChild(ta);
    ta.select();
    let ok = false;
    try { ok = document.execCommand("copy"); } catch (_) {}
    ta.remove();
    return ok;
  }

  function download(text, name) {
    const url = URL.createObjectURL(new Blob([text], { type: "text/plain;charset=utf-8" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = name || "bibleclip.txt";
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(function () { URL.revokeObjectURL(url); }, 1000);
  }

  function fillWindow(w, title, html) {
    w.document.open();
    w.document.write(html);
    w.document.close();
    if (title) w.document.title = title;
  }

  const local = {
    // 서버는 글만 만들고, 클립보드에는 브라우저가 넣는다.
    copy_reference: function () {
      return call("copy_reference", [].slice.call(arguments)).then(function (r) {
        return r && r.ok ? copyToClipboard(r.text).then(function () { return r; }) : r;
      });
    },
    copy_references: function () {
      return call("copy_references", [].slice.call(arguments)).then(function (r) {
        return r && r.ok ? copyToClipboard(r.text).then(function () { return r; }) : r;
      });
    },
    copy_text: function (text) {
      text = String(text || "");
      if (!text) return Promise.resolve({ ok: false });
      return copyToClipboard(text).then(function (ok) { return { ok: !!ok }; });
    },
    export_text_file: function (text, name) {
      download(String(text || ""), name);
      return Promise.resolve({ ok: true });
    },
    // 창은 우클릭한 그 순간에 먼저 연다 — 서버 답을 기다린 뒤에 열면 브라우저가
    // '사용자가 누르지 않은 팝업'으로 보고 막는다. 내용은 답이 오면 채운다.
    open_dict_window: function () {
      const w = window.open("", "_blank", "width=460,height=560");
      if (!w) return Promise.resolve({ ok: false, error: "popup-blocked" });
      return call("open_dict_window", [].slice.call(arguments)).then(function (r) {
        if (r && r.ok) { fillWindow(w, r.title, r.html); return { ok: true }; }
        w.close();
        return { ok: false };
      }, function (e) { w.close(); throw e; });
    },
    // 발표(F11)는 브라우저 전체화면이 대신한다 — 창 자체를 키우는 기능은 없다.
    set_native_fullscreen: function () { return Promise.resolve(null); },
  };

  // 어떤 이름이든 부를 수 있다(서버가 허용하지 않는 이름은 null).
  // `typeof api().xxx === "function"` 같은 검사도 통과한다.
  const api = new Proxy({}, {
    get: function (_, name) {
      if (typeof name !== "string") return undefined;
      if (local[name]) return local[name];
      return function () { return call(name, [].slice.call(arguments)); };
    },
  });

  window.pywebview = { api: api, platform: "web" };
  document.documentElement.classList.add("platform-web");

  // ---- 로그인 · 로그아웃 ----

  let leaving = false;
  function toLogin() {
    if (leaving) return;
    leaving = true;
    location.href = "login";
  }

  // 왼쪽 레일의 테마 단추 위에 로그아웃 단추(누가 들어와 있는지 말풍선으로).
  function addLogoutButton(me) {
    const anchor = document.getElementById("theme-toggle");
    if (!anchor || document.getElementById("web-logout")) return;
    const b = document.createElement("div");
    b.className = "nav-icon";
    b.id = "web-logout";
    b.title = (me && me.name ? me.name + " · " : "") + "로그아웃";
    b.setAttribute("aria-label", b.title);
    b.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" ' +
      'stroke-linecap="round" stroke-linejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>' +
      '<path d="M16 17l5-5-5-5"/><path d="M21 12H9"/></svg>';
    b.addEventListener("click", function () {
      if (!confirm("로그아웃할까요?")) return;
      fetch("logout", { method: "POST", headers: { "X-BibleClip": "1" }, credentials: "same-origin" })
        .finally(toLogin);
    });
    anchor.parentNode.insertBefore(b, anchor);
  }

  document.addEventListener("DOMContentLoaded", function () {
    fetch("auth/me", { credentials: "same-origin" })
      .then(function (r) { if (r.status === 401) toLogin(); return r.ok ? r.json() : null; })
      .then(function (me) { if (me) addLogoutButton(me); })
      .catch(function () {});
  });
})();
