// BibleClip web frontend — core (bootstrap·state·api 래퍼·헬퍼·boot).
// Classic scripts (file:// safe, no ESM/CORS). core → cards → search-notes
// load in order and SHARE global scope; window.BC exposes principal handles.

"use strict";
window.BC = window.BC || {};

  const $ = (id) => document.getElementById(id);
  const root = document.documentElement;

  // ---- Preview interactions (work with or without the bridge) ----

  const themeBtn = $("theme-toggle");
  if (themeBtn) {
    themeBtn.addEventListener("click", () => {
      const dark = root.dataset.theme !== "dark";
      root.dataset.theme = dark ? "dark" : "light";
      if (window.pywebview && window.pywebview.api) window.pywebview.api.set_dark_mode(dark);
    });
  }

  document.querySelectorAll(".seg").forEach((seg) => {
    seg.addEventListener("click", (e) => {
      const opt = e.target.closest(".opt");
      if (!opt || !seg.contains(opt)) return;
      seg.querySelectorAll(".opt").forEach((o) => o.classList.remove("on"));
      opt.classList.add("on");
    });
  });

  // ---- Helpers ----

  const esc = (s) =>
    String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

  // Tears down the listeners (scroll/click) registered by the open menu, so they
  // don't leak across opens. (A stale scroll listener from a previous menu would
  // otherwise close the next one — its closed-over menu no longer contains the
  // new menu, so it'd treat an inside-scroll as a background scroll.)
  let menuCleanup = null;
  function closeMenus() {
    document.querySelectorAll(".menu").forEach((m) => m.remove());
    if (menuCleanup) { menuCleanup(); menuCleanup = null; }
  }

  // Anchored popup menu. items: [{label, value, on}], onPick(value).
  function openMenu(anchor, items, onPick, opts = {}) {
    closeMenus();
    const menu = document.createElement("div");
    menu.className = "menu" + (opts.grid ? " chapters" : "");
    items.forEach((it) => {
      const el = document.createElement("div");
      el.className = "menu-item" + (it.on ? " on" : "");
      el.textContent = it.label;
      el.addEventListener("click", () => {
        if (opts.multi) {
          // Menu stays open for more selections; reflect the actual result
          // (onPick returns the new on/off state, or undefined for no change).
          const res = onPick(it.value);
          if (res === true) el.classList.add("on");
          else if (res === false) el.classList.remove("on");
        } else {
          closeMenus();
          onPick(it.value);
        }
      });
      menu.appendChild(el);
    });
    document.body.appendChild(menu);
    const r = anchor.getBoundingClientRect();
    const top = Math.min(r.bottom + 5, window.innerHeight - menu.offsetHeight - 8);
    const left = Math.min(r.left, window.innerWidth - menu.offsetWidth - 8);
    menu.style.top = Math.max(8, top) + "px";
    menu.style.left = Math.max(8, left) + "px";
    // Close on background scroll (the anchored menu would detach), but NOT when
    // scrolling inside the menu itself (long book/chapter lists are scrollable).
    const onScroll = (e) => { if (!menu.contains(e.target)) closeMenus(); };
    const onDocClick = (e) => {
      if (!menu.contains(e.target) && e.target !== anchor) closeMenus();
    };
    // Registered (and torn down by closeMenus) as a pair so neither leaks.
    menuCleanup = () => {
      document.removeEventListener("click", onDocClick);
      window.removeEventListener("scroll", onScroll, true);
    };
    setTimeout(() => {
      document.addEventListener("click", onDocClick);
      window.addEventListener("scroll", onScroll, true);
    }, 0);
  }
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenus(); });

  // ---- Shared hover tooltip (lock icon + any [data-tip] element) ----

  let tooltipEl = null;
  function showTooltip(el) {
    const text = el.dataset.tip;
    if (!text) return;
    hideTooltip();
    tooltipEl = document.createElement("div");
    tooltipEl.className = "tooltip";
    tooltipEl.textContent = text;
    document.body.appendChild(tooltipEl);
    const r = el.getBoundingClientRect();
    let top = r.bottom + 6;
    // Flip above the anchor if it would overflow the viewport bottom.
    if (top + tooltipEl.offsetHeight > window.innerHeight - 6) {
      top = r.top - tooltipEl.offsetHeight - 6;
    }
    let left = r.left + r.width / 2 - tooltipEl.offsetWidth / 2;
    left = Math.max(8, Math.min(left, window.innerWidth - tooltipEl.offsetWidth - 8));
    tooltipEl.style.top = Math.max(8, top) + "px";
    tooltipEl.style.left = left + "px";
  }
  function hideTooltip() {
    if (tooltipEl) { tooltipEl.remove(); tooltipEl = null; }
  }
  document.addEventListener("mouseover", (e) => {
    const t = e.target.closest("[data-tip]");
    if (t) showTooltip(t);
  });
  document.addEventListener("mouseout", (e) => {
    if (e.target.closest("[data-tip]")) hideTooltip();
  });

  // ---- Activity log drawer + toast (UI only; work without the bridge) ----

  const drawer = $("log-drawer");
  function openDrawer() {
    if (!drawer) return;
    if (typeof closeCart === "function") closeCart();  // 상호배타: 장바구니 드로어 닫기
    if (typeof closeNotes === "function") closeNotes();  // 상호배타: 노트 레일 닫기
    drawer.hidden = false;
    $("log-toggle").classList.add("on");
    const dot = $("log-dot");
    if (dot) dot.hidden = true;
  }
  function closeDrawer() {
    if (!drawer) return;
    drawer.hidden = true;
    $("log-toggle").classList.remove("on");
  }
  if ($("log-toggle")) {
    $("log-toggle").addEventListener("click", () =>
      drawer.hidden ? openDrawer() : closeDrawer()
    );
  }
  if ($("log-close")) $("log-close").addEventListener("click", closeDrawer);

  function flagUnread() {
    if (drawer && drawer.hidden) {
      const dot = $("log-dot");
      if (dot) dot.hidden = false;
    }
  }

  function toast(msg) {
    const wrap = $("toast-wrap");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => {
      el.classList.add("fade");
      setTimeout(() => el.remove(), 320);
    }, 2400);
  }

  // ---- Live mode ----

  function hasBridge() {
    return window.pywebview && window.pywebview.api;
  }

  const api = () => window.pywebview.api;

  const state = {
    versions: [],          // [{name, display}]
    versionsNames: [],      // [name]
    viewer: [],            // active viewer version names (global, shown in all bible cards)
    primary: null,          // default version (first viewer / first DB)
    lastBook: null, lastChapter: null,  // last viewed position (bootstrap default)
    monitoring: false,
    fontSize: 11,
    readingFont: "",        // custom reading font family ('' = 기본 Pretendard)
    searchVersion: null,    // version used for keyword search (default = primary)
    searchClickNav: false,  // search hit click also jumps a bible card
    autoCopyTop: false,     // 검색 시 최고 점수 결과를 클립보드에 자동 복사
    booksCache: {},         // version -> [{num,short,long}]
    chapCache: {},          // "version:book" -> [chapters]
    primaryBooks: [],       // primary version's book list (for search autocomplete)
    lexAvail: { ko: false, en: false },  // installed dictionary modules (original_lang/)
    lexSources: [],         // 원전 분해 소스 후보 [{name, display, lang}] (name=''=개역한글S)
    isPremium: true,        // business guard (Phase 1): false → free-tier limits
  };

  function applyFontScale() {
    root.style.setProperty("--reading-scale", (state.fontSize / 11).toFixed(3));
  }

  // Per-version book / chapter lists (cached; each bible card may differ).
  async function booksFor(version) {
    if (!state.booksCache[version]) state.booksCache[version] = await api().get_books(version);
    return state.booksCache[version];
  }
  async function chaptersFor(version, book) {
    const k = version + ":" + book;
    if (!state.chapCache[k]) state.chapCache[k] = await api().get_chapters(version, book);
    return state.chapCache[k];
  }
  function bookLongFor(version, num) {
    const b = (state.booksCache[version] || []).find((x) => x.num === num);
    return b ? b.long : "?";
  }
  function bookShortFor(version, num) {
    const b = (state.booksCache[version] || []).find((x) => x.num === num);
    return b ? b.short : "?";
  }
  function displayName(name) {
    const v = state.versions.find((x) => x.name === name);
    return v ? v.display : name;
  }

  async function boot() {
    // i18n: load ko(fallback)+active locale via the bridge, then sweep the page.
    // Runs first so static UI is translated before the data-driven render starts.
    if (window.I18N) { try { await I18N.boot(); } catch (_) {} }
    const init = await api().get_initial();
    // Language persistence: the BACKEND settings file is authoritative. The
    // front-end's i18n stores its choice in localStorage, but pywebview serves
    // from 127.0.0.1 on a random port each launch, so that localStorage origin
    // changes every run and the saved language is orphaned → reverted to ko.
    // The backend (bibleclip_settings.json) survives, so apply ITS ui_lang to the
    // front-end when they diverged (was backwards: we used to push the front-end's
    // reverted value back, clobbering the correctly-persisted backend choice).
    if (window.I18N && init.ui_lang && init.ui_lang !== I18N.getLang()) {
      try { await I18N.setLang(init.ui_lang); } catch (_) {}
    }
    state.versions = init.versions;
    state.versionsNames = init.versions.map((v) => v.name);
    state.primary = init.primary || (state.versionsNames[0] || null);
    state.viewer = (init.viewer && init.viewer.length)
      ? init.viewer
      : [state.primary].filter(Boolean);
    state.lastBook = init.last.book;
    state.lastChapter = init.last.chapter;
    state.primaryBooks = init.books || [];
    state.lexSources = init.interlin_sources || [];  // 원전 분해 소스 후보(개역한글S + KJV+ 등)
    // Restore persisted UI prefs (shared with the desktop app).
    root.dataset.theme = init.dark_mode ? "dark" : "light";
    state.fontSize = init.font_size || 11;
    applyFontScale();
    bootReadingFont(init.reading_font || "");   // inject+apply saved custom reading font
    lexLang = init.lex_lang === "en" ? "en" : "ko";
    if (init.lex) state.lexAvail = init.lex;
    state.isPremium = init.is_premium !== false;  // default premium unless backend says false
    syncLangSeg();
    state.searchClickNav = !!init.search_click_navigates;
    state.autoCopyTop = !!init.auto_copy_top_result;
    const verLabel = $("app-ver");
    if (verLabel && init.version) verLabel.textContent = "v" + init.version;

    // Build the card workspace from the saved layout (or a sensible default).
    await CardManager.init(init.web_cards_layout);
    state.searchVersion = CardManager.primaryVersion();
    renderVerChips();

    // 라이브 UI 언어 전환은 search-notes.js 의 retranslateViewport(단일 진입점)가
    // 처리한다 — 카드 헤더 라벨/툴팁 + 동적 뷰를 한 곳에서 다시 그린다(훅 누락 방지).

    // FEAT-08: restore the backend-persisted sermon cart (survives restart;
    // replaces the localStorage fast-paint, which the random loopback port made
    // unreliable). Must run before/with wireCart so the drawer renders restored.
    restoreCart(init.cart || []);

    wireGlobalControls();
    wireMonitor();
    wireCart();
    wireNotesRail();
    wireTabs();
    wireUpdate();
    wireAppSettings();
    wireReadingFontMenu();
    wireAliasManager();
    if (init.auto_update_check) checkUpdate(true); // silent startup check
    maybePatchModal(); // first-run-after-update patch notes (Phase 4)
  }

  // ============================================================
  //  CardManager — modular multi-card workspace
  // ============================================================

  const MAX_BIBLE = 4;
  // 카드 타입 라벨. TYPE_LABEL은 ko 베이스(= i18n 폴백), typeLabel()은 렌더 시점의
  // 현재 언어 문자열을 돌려준다. card-title span은 data-i18n도 달아 언어 전환 시
  // apply() 재스윕으로 즉시 갱신된다(카드 재렌더 불필요).
  const TYPE_LABEL = { bible: "성경 본문", interlinear: "원전 분해", lexicon: "사전" };
  function typeLabel(type) {
    return window.I18N ? I18N.t("card.type." + type, TYPE_LABEL[type]) : TYPE_LABEL[type];
  }
  const ID_PREFIX = { bible: "bible", interlinear: "inter", lexicon: "lex" };
  const BODY_CLASS = { bible: "scripture", interlinear: "interlin", lexicon: "lex" };

  const LOCK_CLOSED = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
  const LOCK_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>';

