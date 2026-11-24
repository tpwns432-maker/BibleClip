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

  window.Site = { capi, me, logout, esc, ago, timeTag, renderText, goHref, toLogin };
})();
