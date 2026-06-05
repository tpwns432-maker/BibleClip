// BibleClip web frontend — i18n engine (v1.0.6 Phase 1 뼈대).
// Classic script (file:// safe, no ESM/CORS); LOADS FIRST, before core.js, so
// window.I18N is available to every later module. Locale tables are real JSON
// files under web/locales/<lang>.json — file:// blocks fetch() of local JSON,
// so they're read by the Python bridge (api.get_locale) and registered here.
//
// 설계 원칙:
//  - 기본 언어(ko)는 HTML/JS에 작성된 원문 자체가 폴백이다. 번역 테이블이 아직
//    로드되지 않았거나 해당 키가 없으면 DOM 스윕은 엘리먼트 원문을 건드리지 않는다
//    → ko 기본 화면은 테이블 없이도 그대로 정상 렌더된다.
//  - boot()은 ko 테이블을 항상 먼저 로드한다. ko→en→ko 복귀 시 ko 테이블이 있어야
//    영어로 바뀐 텍스트를 한국어로 되돌릴 수 있기 때문(없으면 영어가 남는다).
//  - 언어 전환은 재시작 없이 즉시(웹 DOM 재번역). 네이티브 크래시와 무관.

"use strict";
(function () {
  const STORE_KEY = "bibleclip_ui_lang";
  const DEFAULT_LANG = "ko";
  // 지원 언어 목록 — web/locales/<lang>.json 추가 시 여기에만 코드 한 줄 더한다.
  const SUPPORTED = ["ko", "en"];

  const tables = {};        // lang -> { key: "translated string" }
  let current = DEFAULT_LANG;

  try {
    const saved = localStorage.getItem(STORE_KEY);
    if (saved && SUPPORTED.indexOf(saved) !== -1) current = saved;
  } catch (_) {}

  function register(lang, dict) {
    if (!dict || typeof dict !== "object") return;
    tables[lang] = Object.assign(tables[lang] || {}, dict);
  }

  // Raw lookup in one language (no fallback). undefined when missing.
  function rawLookup(lang, key) {
    const t = tables[lang];
    return t ? t[key] : undefined;
  }

  // DOM-sweep lookup: current → ko, but NO key/literal fallback. Returns
  // undefined when untranslated so the sweep leaves the authored text intact.
  function lookup(key) {
    let v = rawLookup(current, key);
    if (v == null && current !== DEFAULT_LANG) v = rawLookup(DEFAULT_LANG, key);
    return v;
  }

  // Programmatic translate (for JS-built strings). `vars`:
  //   • object → substitute {name} placeholders, e.g.
  //       t("update.available", { latest: "1.0.6", current: "1.0.5" })
  //   • string → fallback used only when the key is missing
  // Template fallback chain: current → ko → (string fallback) → key.
  function t(key, vars) {
    let v = lookup(key);
    if (v == null) v = (typeof vars === "string" ? vars : key);
    if (vars && typeof vars === "object") {
      v = v.replace(/\{(\w+)\}/g, (m, k) => (k in vars ? vars[k] : m));
    }
    return v;
  }

  function applyAttr(el, attr, key) {
    const v = lookup(key);
    if (v != null) el.setAttribute(attr, v);
  }

  // Translate a DOM subtree in place. Supported markers:
  //   data-i18n="key"             → textContent
  //   data-i18n-html="key"        → innerHTML (strings that contain markup)
  //   data-i18n-title="key"       → title attribute (native tooltip)
  //   data-i18n-tip="key"         → data-tip attribute (app's custom tooltip —
  //                                 re-read on every hover, so live switches show)
  //   data-i18n-placeholder="key" → placeholder attribute
  //   data-i18n-aria="key"        → aria-label attribute
  function apply(root) {
    root = root || document;
    root.querySelectorAll("[data-i18n]").forEach((el) => {
      const v = lookup(el.dataset.i18n);
      if (v != null) el.textContent = v;
    });
    root.querySelectorAll("[data-i18n-html]").forEach((el) => {
      const v = lookup(el.dataset.i18nHtml);
      if (v != null) el.innerHTML = v;
    });
    root.querySelectorAll("[data-i18n-title]").forEach((el) =>
      applyAttr(el, "title", el.dataset.i18nTitle));
    root.querySelectorAll("[data-i18n-tip]").forEach((el) =>
      applyAttr(el, "data-tip", el.dataset.i18nTip));
    root.querySelectorAll("[data-i18n-placeholder]").forEach((el) =>
      applyAttr(el, "placeholder", el.dataset.i18nPlaceholder));
    root.querySelectorAll("[data-i18n-aria]").forEach((el) =>
      applyAttr(el, "aria-label", el.dataset.i18nAria));
  }

  function getLang() { return current; }

  // Load a language table from the Python bridge (no-op without the bridge or
  // on any failure — the authored ko text remains as fallback).
  async function load(lang) {
    if (tables[lang]) return tables[lang];
    try {
      if (window.pywebview && window.pywebview.api && window.pywebview.api.get_locale) {
        const dict = await window.pywebview.api.get_locale(lang);
        register(lang, dict);
      }
    } catch (_) {}
    return tables[lang] || {};
  }

  // Ensure ko (fallback) + the active language are loaded, then sweep the page.
  // Called from core.js boot() once the bridge is ready.
  async function boot() {
    await load(DEFAULT_LANG);
    if (current !== DEFAULT_LANG) await load(current);
    document.documentElement.lang = current;
    apply(document);
  }

  // Live language switch — no restart. Loads the table if needed, re-sweeps the
  // whole document, and fires "i18n:changed" so dynamic views can re-render.
  async function setLang(lang) {
    if (!lang || lang === current || SUPPORTED.indexOf(lang) === -1) return;
    current = lang;
    try { localStorage.setItem(STORE_KEY, lang); } catch (_) {}
    await load(lang);
    document.documentElement.lang = lang;
    apply(document);
    try {
      window.dispatchEvent(new CustomEvent("i18n:changed", { detail: { lang } }));
    } catch (_) {}
  }

  window.I18N = {
    register, t, lookup, apply, getLang, setLang, load, boot,
    SUPPORTED, DEFAULT_LANG,
  };

  // Initial sweep with whatever is registered (nothing yet → leaves authored
  // Korean). boot() re-sweeps once the locale tables load.
  if (document.readyState !== "loading") apply(document);
  else document.addEventListener("DOMContentLoaded", () => apply(document));
})();
