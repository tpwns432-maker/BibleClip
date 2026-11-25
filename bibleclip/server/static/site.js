// BibleClip 웹판 — 홈 · 커뮤니티가 함께 쓰는 도움 함수(window.Site).
// 서버 호출(POST capi/<동작>), 로그인 · 테마, 글을 안전하게 그리기(구절 · 웹 주소 링크).
(function () {
  "use strict";

  const JSON_H = { "Content-Type": "application/json", "X-BibleClip": "1" };

  function toLogin() { location.href = "login"; }

  async function capi(action, args) {
    const r = await fetch("capi/" + encodeURIComponent(action), {
      method: "POST", headers: JSON_H, body: JSON.stringify(args || {}), credentials: "same-origin",
    });
    if (r.status === 401) { toLogin(); throw new Error("login"); }
    const b = await r.json().catch(() => ({}));
    if (!r.ok) {
      const e = new Error(b.error || ("HTTP " + r.status));
      e.code = b.error;
      e.detail = b.detail;
      throw e;
    }
    return b.value;
  }

  // 지금 들어온 사람 + 그 사람의 색 테마(성경 화면 설정과 같은 값)를 입힌다.
  async function me() {
    const r = await fetch("auth/me", { credentials: "same-origin" });
    if (r.status === 401) { toLogin(); throw new Error("login"); }
    const m = await r.json();
    try {
      const custom = m.custom_theme ? Theme.cleanCustom(m.custom_theme) : null;
      let t = Theme.fromSettings(m.theme, m.dark_mode);
      if (t === "custom" && !custom) t = m.dark_mode ? "dark" : "light";
      Theme.apply(t, custom);
    } catch (_) {}
    return m;
  }

  async function logout() {
    if (!confirm("로그아웃할까요?")) return;
    try {
      await fetch("logout", { method: "POST", headers: { "X-BibleClip": "1" }, credentials: "same-origin" });
    } finally { toLogin(); }
  }

  const ESC = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
  function esc(s) { return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => ESC[c]); }

  function ago(iso) {
    const t = new Date(iso);
    const s = (Date.now() - t.getTime()) / 1000;
    if (s < 60) return "방금";
    if (s < 3600) return Math.floor(s / 60) + "분 전";
    if (s < 86400) return Math.floor(s / 3600) + "시간 전";
    if (s < 172800) return "어제";
    if (s < 604800) return Math.floor(s / 86400) + "일 전";
    const n = new Date();
    return (t.getFullYear() === n.getFullYear() ? "" : t.getFullYear() + "년 ") +
      (t.getMonth() + 1) + "월 " + t.getDate() + "일";
  }
  function timeTag(iso) {
    return `<time datetime="${esc(iso)}" title="${esc(new Date(iso).toLocaleString("ko-KR"))}">${esc(ago(iso))}</time>`;
  }

  function goHref(r) { return "bible#go=" + r.book + "." + r.chapter + "." + r.verses.join(","); }

  // 웹 주소만 링크로. 나머지는 글자 그대로(HTML 로 해석하지 않는다).
  function linkify(t) {
    const re = /https?:\/\/[^\s<>"']+/g;
    let out = "", i = 0, m;
    while ((m = re.exec(t))) {
      const url = m[0].replace(/[.,!?;:)\]]+$/, "");
      out += esc(t.slice(i, m.index)) +
        `<a href="${esc(url)}" target="_blank" rel="noopener noreferrer">${esc(url)}</a>`;
      i = m.index + url.length;
      re.lastIndex = i;
    }
    return out + esc(t.slice(i));
  }

  // 글 → HTML. refs = 서버가 찾은 구절 [{s, e, book, chapter, verses}] (JS 문자열 위치).
  function renderText(text, refs) {
    text = String(text || "");
    let out = "", i = 0;
    for (const r of (refs || []).slice().sort((a, b) => a.s - b.s)) {
      if (r.s < i || r.e > text.length) continue;
      out += linkify(text.slice(i, r.s)) +
        `<a class="vref" href="${esc(goHref(r))}" title="${esc(r.label)} — 성경에서 열기">${esc(text.slice(r.s, r.e))}</a>`;
      i = r.e;
    }
    return out + linkify(text.slice(i));
  }

  // 글에 쓴 구절의 본문 카드 — 서버가 r.quote = {version, verses: [{n, text}], more} 를 붙여 준다.
  // 글(.body)은 pre-wrap 이라 카드 HTML 에는 줄바꿈 · 들여쓰기를 넣지 않는다.
  function quoteCard(r) {
    const q = r.quote;
    return `<div class="ref-quote"><a class="vq-label" href="${esc(goHref(r))}" title="성경에서 열기">📖 ${esc(r.label)}</a>` +
      `<blockquote>${q.verses.map((x) => `<sup>${x.n}</sup>${esc(x.text)}`).join(" ")}${q.more ? " …" : ""}` +
      `<cite>${esc(q.version)}</cite></blockquote></div>`;
  }

  // renderText + 구절 카드: 구절이 나온 줄 바로 아래에 본문을 보여 준다(그 줄의 줄바꿈은 카드가 대신).
  function renderRich(text, refs) {
    text = String(text || "");
    refs = (refs || []).filter((r) => r.s >= 0 && r.e <= text.length).sort((a, b) => a.s - b.s);
    const cuts = new Map();          // 줄 끝 위치 → 그 줄에 나온 구절들
    for (const r of refs) {
      if (!r.quote || !r.quote.verses || !r.quote.verses.length) continue;
      let k = text.indexOf("\n", r.e);
      if (k < 0) k = text.length;
      if (!cuts.has(k)) cuts.set(k, []);
      cuts.get(k).push(r);
    }
    if (!cuts.size) return renderText(text, refs);
    let out = "", i = 0;
    for (const k of [...cuts.keys()].sort((a, b) => a - b)) {
      const seg = refs.filter((r) => r.s >= i && r.e <= k).map((r) => Object.assign({}, r, { s: r.s - i, e: r.e - i }));
      out += renderText(text.slice(i, k), seg) + cuts.get(k).map(quoteCard).join("");
      i = k + 1;                     // 줄바꿈 하나는 카드가 대신한다
    }
    if (i <= text.length) {
      const seg = refs.filter((r) => r.s >= i).map((r) => Object.assign({}, r, { s: r.s - i, e: r.e - i }));
      out += renderText(text.slice(i), seg);
    }
    return out;
  }

  // ---- 테마 단추(홈 · 커뮤니티 위 막대) ----
  // 성경 화면 ⚙ 설정의 테마와 같은 값(theme · custom_theme)을 같은 저장 기능으로 바꾼다.

  function api(name, args) {
    return fetch("api/" + name, {
      method: "POST", headers: JSON_H, body: JSON.stringify({ args: args }), credentials: "same-origin",
    }).then((r) => { if (r.status === 401) toLogin(); return r.json(); });
  }

  const THEME_NAMES = { light: "라이트", dark: "다크", paper: "종이", sage: "숲", navy: "남색", black: "검정", custom: "직접" };

  function themeMenu(btn, m) {
    let theme = Theme.fromSettings(m.theme, m.dark_mode);
    let custom = m.custom_theme ? Theme.cleanCustom(m.custom_theme) : null;
    if (theme === "custom" && !custom) theme = m.dark_mode ? "dark" : "light";
    let pop = null, saveTimer = 0;

    const seeds = (name) => (name === "custom" ? (custom || Theme.seedsOf(theme, custom)) : Theme.PRESETS[name]);
    function swatch(name) {
      const s = seeds(name);
      return `<button type="button" class="tsw${name === theme ? " on" : ""}" data-theme="${name}" title="${THEME_NAMES[name]}">` +
        `<span class="tdot" style="--sw-bg:${s.bg};--sw-text:${s.text};--sw-accent:${s.accent}">가</span>` +
        `<span>${THEME_NAMES[name]}</span></button>`;
    }
    function render() {
      const names = Theme.supported() ? Theme.ORDER : ["light", "dark"];
      const c = custom || seeds(theme);
      const warn = theme === "custom" ? Theme.warnings(c) : [];
      pop.innerHTML = `<div class="tsws">${names.map(swatch).join("")}</div>` +
        (theme !== "custom" ? "" :
          `<div class="tedit">
            <div class="seg" data-role="base"><button type="button" data-base="light" class="${c.base === "light" ? "on" : ""}">밝게</button>` +
            `<button type="button" data-base="dark" class="${c.base === "dark" ? "on" : ""}">어둡게</button></div>
            <div class="tcolors">${[["bg", "배경"], ["text", "글자"], ["accent", "강조"]].map(([k, l]) =>
              `<label>${l}<input type="color" data-key="${k}" value="${c[k]}"></label>`).join("")}</div>
            ${warn.length ? `<p class="twarn">${warn.map((w) => w.kind === "text"
              ? "글자와 배경의 대비가 낮아 읽기 어려울 수 있습니다."
              : "강조색이 배경과 비슷해 링크 · 단추가 잘 안 보일 수 있습니다.").join("<br>")}</p>` : ""}
          </div>`);
    }
    function save(key, value) {
      return api("set_app_setting", [key, value]).catch(() => {});
    }
    function choose(name) {
      if (name === "custom" && !custom) custom = Object.assign({}, Theme.seedsOf(theme, custom));  // 보던 색에서 시작
      theme = name;
      Theme.apply(theme, custom);
      if (name === "custom") save("custom_theme", custom).then(() => save("theme", "custom"));
      else save("theme", name);
      render();
    }
    function updateCustom(patch) {
      custom = Object.assign({}, custom, patch);
      Theme.apply("custom", custom);
      clearTimeout(saveTimer);
      saveTimer = setTimeout(() => save("custom_theme", custom), 300);
    }
    function close() {
      if (!pop) return;
      pop.remove();
      pop = null;
      document.removeEventListener("pointerdown", outside, true);
    }
    function outside(e) { if (pop && !pop.contains(e.target) && e.target !== btn && !btn.contains(e.target)) close(); }

    btn.addEventListener("click", () => {
      if (pop) { close(); return; }
      pop = document.createElement("div");
      pop.className = "theme-pop";
      pop.setAttribute("role", "dialog");
      pop.setAttribute("aria-label", "테마");
      render();
      document.body.appendChild(pop);
      const r = btn.getBoundingClientRect();
      pop.style.top = (r.bottom + 8) + "px";
      pop.style.right = Math.max(8, window.innerWidth - r.right) + "px";
      pop.addEventListener("click", (e) => {
        const t = e.target.closest("[data-theme]");
        if (t) { choose(t.dataset.theme); return; }
        const b = e.target.closest("[data-base]");
        if (b) { updateCustom({ base: b.dataset.base }); render(); }
      });
      pop.addEventListener("input", (e) => {
        const k = e.target.dataset.key;
        if (k) updateCustom({ [k]: e.target.value.toLowerCase() });
      });
      pop.addEventListener("change", (e) => { if (e.target.dataset.key) render(); });   // 경고 다시 보기
      document.addEventListener("pointerdown", outside, true);
    });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });
  }

  window.Site = { capi, me, logout, esc, ago, timeTag, renderText, renderRich, goHref, toLogin, themeMenu };
})();
