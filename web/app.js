// BibleClip web frontend.
// - Preview interactions (theme, segments) always run.
// - LIVE mode: when running inside pywebview (window.pywebview.api present),
//   pull real data from the Library bridge and render the modular card
//   workspace. In a plain browser the bridge is absent, so the viewer stays
//   empty (graceful fallback); the peripheral chrome still works.
//
// Modular cards (this build): the fixed 3-panel viewer was replaced by a
// CardManager that lays out a horizontal row of cards. Three card types —
// 'bible' (성경 본문), 'interlinear' (원어 분석), 'lexicon' (사전). Up to 4 bible
// cards, each with its own version·book·chapter. A bible card can be "locked"
// (조건부 수신): a locked card is excluded from clipboard auto-navigation. The
// N-1 rule keeps at least one bible card receiving (you can lock at most N-1 of
// N bible cards). The whole layout is persisted to web_cards_layout.

(function () {
  "use strict";

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
    searchVersion: null,    // version used for keyword search (default = primary)
    searchClickNav: false,  // search hit click also jumps a bible card
    booksCache: {},         // version -> [{num,short,long}]
    chapCache: {},          // "version:book" -> [chapters]
    primaryBooks: [],       // primary version's book list (for search autocomplete)
    lexAvail: { ko: false, en: false },  // installed dictionary modules (original_lang/)
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
    const init = await api().get_initial();
    state.versions = init.versions;
    state.versionsNames = init.versions.map((v) => v.name);
    state.primary = init.primary || (state.versionsNames[0] || null);
    state.viewer = (init.viewer && init.viewer.length)
      ? init.viewer
      : [state.primary].filter(Boolean);
    state.lastBook = init.last.book;
    state.lastChapter = init.last.chapter;
    state.primaryBooks = init.books || [];
    // Restore persisted UI prefs (shared with the desktop app).
    root.dataset.theme = init.dark_mode ? "dark" : "light";
    state.fontSize = init.font_size || 11;
    applyFontScale();
    lexLang = init.lex_lang === "en" ? "en" : "ko";
    if (init.lex) state.lexAvail = init.lex;
    state.isPremium = init.is_premium !== false;  // default premium unless backend says false
    syncLangSeg();
    state.searchClickNav = !!init.search_click_navigates;
    const verLabel = $("app-ver");
    if (verLabel && init.version) verLabel.textContent = "v" + init.version;

    // Build the card workspace from the saved layout (or a sensible default).
    await CardManager.init(init.web_cards_layout);
    state.searchVersion = CardManager.primaryVersion();
    renderVerChips();

    wireGlobalControls();
    wireMonitor();
    wireTabs();
    wireUpdate();
    wireAppSettings();
    if (init.auto_update_check) checkUpdate(true); // silent startup check
  }

  // ============================================================
  //  CardManager — modular multi-card workspace
  // ============================================================

  const MAX_BIBLE = 4;
  const TYPE_LABEL = { bible: "성경 본문", interlinear: "원어 분석", lexicon: "사전" };
  const ID_PREFIX = { bible: "bible", interlinear: "inter", lexicon: "lex" };
  const BODY_CLASS = { bible: "scripture", interlinear: "interlin", lexicon: "lex" };

  const LOCK_CLOSED = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 10 0v4"/></svg>';
  const LOCK_OPEN = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="11" width="18" height="11" rx="2"/><path d="M7 11V7a5 5 0 0 1 9.9-1"/></svg>';

  const CardManager = (() => {
    let cards = [];          // card descriptors (each carries free-form geometry)
    let saveTimer = null;
    let interacting = false; // true while a move/resize gesture is in flight
    let zTop = 1;            // highest z-index in use (click-to-front counter)
    let cascadeN = 0;        // cascade offset counter for newly added cards
    let activeId = null;     // id of the focused card (neon stroke + keyboard target)

    const SAVE_DEBOUNCE_MS = 300;  // layout autosave debounce (Phase 2)

    // Free-form workspace geometry. All card positions/sizes are stored as
    // PERCENTAGES of the workspace, so a window resize scales every card
    // proportionally while fonts (px-based) stay fixed.
    const MIN_W = 12, MIN_H = 15;   // minimum card size (%)
    const SNAP_PX = 8;              // snap threshold (px, converted per gesture)
    const GUTTER = 0.33;            // gap kept between adjacent cards when snapped (%)
    const ATTACH_EPS = 0.2;         // tolerance (%) for attachment / cross-overlap margins

    // Workspace divider snap lines (작업영역 분할 가이드): cards' edges snap to
    // these flush (no gutter). Card-to-card snaps take priority on ties.
    const DIV_X = [25, 100 / 3, 50, 200 / 3, 75];  // vertical guides (2·3·4등분)
    const DIV_Y = [100 / 3, 50, 200 / 3];          // horizontal guides (2·3등분)

    // ---- lookups ----
    const container = () => $("panels-container");
    const sectionEl = (id) => container() && container().querySelector(`.mcard[data-id="${id}"]`);
    const bodyEl = (id) => { const s = sectionEl(id); return s && s.querySelector(".card-body"); };
    const lockEl = (id) => { const s = sectionEl(id); return s && s.querySelector(".card-lock"); };
    const cardById = (id) => cards.find((c) => c.id === id) || null;
    const bibleCards = () => cards.filter((c) => c.type === "bible");
    const lexiconCards = () => cards.filter((c) => c.type === "lexicon");
    const firstBible = () => bibleCards()[0] || null;
    const primaryBible = () => firstBible();
    const linkedBible = (card) => cardById(card.link) || firstBible();

    function nextId(type) {
      const p = ID_PREFIX[type];
      const used = new Set(cards.filter((c) => c.type === type).map((c) => c.id));
      let n = 1;
      while (used.has(`${p}-${n}`)) n++;
      return `${p}-${n}`;
    }

    // ---- (de)serialization + restore ----
    const round1 = (n) => Math.round(n * 10) / 10;

    function serialize() {
      return cards.map((c) => {
        const o = {
          id: c.id, type: c.type,
          x: round1(c.x), y: round1(c.y), w: round1(c.w), h: round1(c.h), z: c.z,
        };
        if (c.type === "bible") {
          o.version = c.version; o.book = c.book; o.chapter = c.chapter; o.locked = !!c.locked;
        } else {
          o.link = c.link || null;
        }
        return o;
      });
    }

    // Debounced layout autosave (Phase 2). While a move/resize gesture is in
    // flight, storage writes are blocked OUTRIGHT so drag/resize frames spend
    // 100% on rendering (no I/O jank); the gesture's onUp clears the flag and
    // calls this once, so exactly one write lands ~300ms after the mouse is
    // released. Frame updates during a gesture go through applyGeom only.
    function saveLayout() {
      if (interacting) return; // drag/resize in progress → defer to its onUp
      if (saveTimer) clearTimeout(saveTimer);
      saveTimer = setTimeout(() => {
        saveTimer = null;
        if (hasBridge() && typeof api().save_cards_layout === "function") {
          api().save_cards_layout(serialize());
        }
        console.log("[BibleClip] 레이아웃 저장 완료");
      }, SAVE_DEBOUNCE_MS);
    }

    function defaultLayout() {
      const v = state.primary;
      // 본문 | 원어 | 사전 side by side, attached, filling the workspace.
      return [
        { id: "bible-1", type: "bible", version: v, book: state.lastBook, chapter: state.lastChapter,
          locked: false, x: 0, y: 0, w: 34, h: 100, z: 1 },
        { id: "inter-1", type: "interlinear", link: "bible-1", x: 34, y: 0, w: 33, h: 100, z: 2 },
        { id: "lex-1", type: "lexicon", link: "bible-1", x: 67, y: 0, w: 33, h: 100, z: 3 },
      ];
    }

    const clampNum = (x, lo, hi, dflt) =>
      (typeof x === "number" && isFinite(x) ? Math.max(lo, Math.min(hi, x)) : dflt);

    // Validate a saved layout: clamp bible count, fall back unknown versions,
    // re-assign clean ids (bible-1.., inter-1.., lex-1..), remap links, and
    // sanitize geometry (cards missing geometry → clean side-by-side layout).
    function restore(layout) {
      if (!Array.isArray(layout) || !layout.length) return defaultLayout();
      const out = [];
      let bibleN = 0;
      layout.forEach((raw) => {
        if (!raw || typeof raw !== "object") return;
        if (raw.type === "bible") {
          if (bibleN >= MAX_BIBLE) return;
          const version = state.versionsNames.includes(raw.version) ? raw.version : state.primary;
          out.push({
            rawId: raw.id, id: "", type: "bible", version,
            book: raw.book || state.lastBook, chapter: raw.chapter || state.lastChapter,
            locked: !!raw.locked,
            x: raw.x, y: raw.y, w: raw.w, h: raw.h, z: raw.z,
          });
          bibleN++;
        } else if (raw.type === "interlinear" || raw.type === "lexicon") {
          out.push({
            rawId: raw.id, id: "", type: raw.type,
            link: typeof raw.link === "string" ? raw.link : null,
            x: raw.x, y: raw.y, w: raw.w, h: raw.h, z: raw.z,
          });
        }
      });
      if (!out.length) return defaultLayout();
      // Geometry: only trust it if EVERY card has valid numbers (a layout saved
      // by an older build lacks x/y/w/h → re-lay out side by side).
      const allValid = out.every((c) =>
        [c.x, c.y, c.w, c.h].every((n) => typeof n === "number" && isFinite(n)));
      if (allValid) {
        out.forEach((c, i) => {
          c.w = clampNum(c.w, MIN_W, 100, 33); c.h = clampNum(c.h, MIN_H, 100, 100);
          c.x = clampNum(c.x, 0, 100 - c.w, 0); c.y = clampNum(c.y, 0, 100 - c.h, 0);
          c.z = clampNum(c.z, 1, 100000, i + 1);
        });
        // Renormalize z to 1..n (stacking order preserved) so saved layouts with
        // inflated z values can't overlap the UI overlay layers (menus etc.).
        [...out].sort((a, b) => a.z - b.z).forEach((c, i) => { c.z = i + 1; });
      } else {
        const w = Math.max(MIN_W, Math.floor(1000 / out.length) / 10);
        out.forEach((c, i) => {
          c.x = Math.min(i * w, 100 - w); c.y = 0; c.w = w; c.h = 100; c.z = i + 1;
        });
      }
      // Assign clean ids in order and build an old→new id map.
      const counters = { bible: 0, interlinear: 0, lexicon: 0 };
      const idMap = {};
      out.forEach((c) => {
        c.id = `${ID_PREFIX[c.type]}-${++counters[c.type]}`;
        if (c.rawId) idMap[c.rawId] = c.id;
      });
      const firstB = (out.find((c) => c.type === "bible") || {}).id || null;
      out.forEach((c) => {
        if (c.type !== "bible") {
          c.link = (c.link && idMap[c.link]) || firstB;
        }
        delete c.rawId;
      });
      return out;
    }

    // ---- lock state (조건부 수신 + N-1 rule) ----

    // Force the lock invariants after any change to the bible-card set: with <2
    // bible cards nothing can be locked; never leave more than N-1 locked.
    function normalizeLocks() {
      const bibles = bibleCards();
      const N = bibles.length;
      if (N < 2) { bibles.forEach((c) => (c.locked = false)); return; }
      let lockedN = bibles.filter((c) => c.locked).length;
      for (let i = bibles.length - 1; i >= 0 && lockedN > N - 1; i--) {
        if (bibles[i].locked) { bibles[i].locked = false; lockedN--; }
      }
    }

    function refreshLockStates() {
      const bibles = bibleCards();
      const N = bibles.length;
      const lockedN = bibles.filter((c) => c.locked).length;
      bibles.forEach((card) => {
        const el = lockEl(card.id);
        const sec = sectionEl(card.id);
        if (sec) sec.classList.toggle("locked", !!card.locked);
        if (!el) return;
        el.classList.toggle("on", !!card.locked);
        el.innerHTML = card.locked ? LOCK_CLOSED : LOCK_OPEN;
        let disabled = false, tip;
        if (N < 2) {
          disabled = true;
          tip = "성경 카드가 2개 이상일 때만 잠글 수 있습니다";
        } else if (!card.locked && lockedN >= N - 1) {
          // The last receiving card can't be locked (N-1 rule).
          disabled = true;
          tip = "최소 한 개의 성경 카드는 클립보드 구절을 수신해야 합니다";
        } else if (card.locked) {
          tip = "잠금 해제 — 이 카드도 클립보드 구절을 수신합니다";
        } else {
          tip = "잠금 — 이 카드는 클립보드 구절을 수신하지 않습니다";
        }
        el.classList.toggle("disabled", disabled);
        el.dataset.tip = tip;
      });
    }

    function toggleLock(card) {
      const bibles = bibleCards();
      const N = bibles.length;
      if (N < 2) return; // lock disabled with a single bible card
      if (card.locked) {
        card.locked = false; // unlocking is always allowed
      } else {
        const lockedN = bibles.filter((c) => c.locked).length;
        if (lockedN >= N - 1) {
          toast("최소 한 개의 성경 카드는 클립보드 구절을 수신해야 합니다");
          return;
        }
        card.locked = true;
      }
      refreshLockStates();
      saveLayout();
    }

    // ---- DOM building ----

    function headerHTML(card) {
      const grip = `<span class="card-grip" data-tip="드래그하여 이동">⠿</span>`;
      if (card.type === "bible") {
        return `<div class="card-hd">${grip}<span class="card-title">${TYPE_LABEL.bible}</span>` +
          `<span class="hd-mini hd-nav disabled" data-act="back" data-tip="이전 구절로">◀</span>` +
          `<span class="hd-mini hd-nav disabled" data-act="forward" data-tip="다음 구절로">▶</span>` +
          `<span class="card-hd-ctrls">` +
            `<span class="hd-pill dropdown" data-act="book">…</span>` +
            `<span class="hd-pill dropdown" data-act="chapter">${card.chapter || 1}장</span>` +
            `<span class="hd-mini" data-act="prev" data-tip="이전 장">‹</span>` +
            `<span class="hd-mini" data-act="next" data-tip="다음 장">›</span>` +
          `</span>` +
          `<span class="card-hd-spacer"></span>` +
          `<span class="card-lock" data-act="lock">${LOCK_OPEN}</span>` +
          `<span class="card-x" data-act="close" data-tip="카드 닫기">✕</span>` +
        `</div>`;
      }
      return `<div class="card-hd">${grip}<span class="card-title">${TYPE_LABEL[card.type]}</span>` +
        `<span class="card-hd-ctrls">` +
          `<span class="hd-pill dropdown" data-act="link" data-tip="연결할 성경 카드 선택">${esc(card.link || "연결 없음")}</span>` +
        `</span>` +
        `<span class="card-hd-spacer"></span>` +
        `<span class="card-x" data-act="close" data-tip="카드 닫기">✕</span>` +
      `</div>`;
    }

    function geomStyle(card) {
      return `left:${card.x}%;top:${card.y}%;width:${card.w}%;height:${card.h}%;z-index:${card.z}`;
    }

    function skeleton(card) {
      const locked = card.type === "bible" && card.locked ? " locked" : "";
      // 8-direction resize handles (edges + corners).
      const handles = ["n", "e", "s", "w", "ne", "se", "sw", "nw"]
        .map((d) => `<span class="rs rs-${d}" data-rs="${d}"></span>`).join("");
      return `<section class="card mcard${locked}" data-id="${card.id}" data-type="${card.type}" style="${geomStyle(card)}">` +
        headerHTML(card) +
        `<div class="card-body ${BODY_CLASS[card.type]}"><div class="panel-loading">불러오는 중…</div></div>` +
        handles +
      `</section>`;
    }

    function renderAll() {
      const c = container();
      if (!c) return;
      if (!cards.length) {
        c.innerHTML = `<div class="panels-empty">카드가 없습니다.<br>우측 상단의 <b>＋ 본문 · ＋ 원어 · ＋ 사전</b> 버튼으로 카드를 추가하세요.</div>`;
        return;
      }
      c.innerHTML = cards.map(skeleton).join("");
      normalizeLocks();
      refreshLockStates();
      // Re-apply the active highlight (innerHTML rebuild dropped the class).
      if (activeId && cardById(activeId)) setActive(cardById(activeId));
      cards.forEach((card) => loadCard(card));
    }

    // ---- content loaders ----

    function loadCard(card) {
      if (card.type === "bible") return loadBibleCard(card);
      if (card.type === "interlinear") return loadInterlinearCard(card);
      return loadLexiconCard(card);
    }

    async function loadBibleCard(card, highlight) {
      const body = bodyEl(card.id);
      if (!body) return;
      body.innerHTML = `<div class="panel-loading">불러오는 중…</div>`;
      const navVer = state.viewer[0] || state.primary;
      await booksFor(navVer);
      const chs = await chaptersFor(navVer, card.book);
      if (!chs.includes(card.chapter)) card.chapter = chs[0] || 1;
      // Load all active viewer versions in parallel.
      const viewerVers = state.viewer.length > 0 ? state.viewer : [navVer];
      const chapDataArr = await Promise.all(
        viewerVers.map((v) => api().get_chapter(v, card.book, card.chapter))
      );
      const b2 = bodyEl(card.id);
      if (b2) renderMultiVersesInto(b2, viewerVers, chapDataArr, highlight);
      updateBibleHeader(card);
      updateNavButtons(card);
    }

    async function loadInterlinearCard(card) {
      const body = bodyEl(card.id);
      if (!body) return;
      const src = linkedBible(card);
      updateLinkHeader(card);
      if (!src) {
        body.innerHTML = `<div class="panel-loading">연결된 성경 카드가 없습니다</div>`;
        return;
      }
      body.innerHTML = `<div class="panel-loading">불러오는 중…</div>`;
      const data = await api().get_interlinear(src.book, src.chapter);
      const b2 = bodyEl(card.id);
      if (b2) renderInterlinearInto(b2, data);
    }

    function loadLexiconCard(card) {
      const body = bodyEl(card.id);
      if (!body) return;
      updateLinkHeader(card);
      // Use the per-bible-link last-looked-up state (falls back to global lexCur).
      const lb = linkedBible(card);
      const cur = (lb && lexCurMap.get(lb.id)) || lexCur;
      if (cur) {
        body.innerHTML = `<div class="panel-loading">[${esc(cur.code)}] 불러오는 중…</div>`;
        api().lookup_strong(cur.code, lexLang, cur.book, cur.chapter, cur.verse || null)
          .then((res) => { const b = bodyEl(card.id); if (b) renderLexEntryInto(b, cur.code, res); });
      } else {
        body.innerHTML = `<div class="panel-loading">원어 단어의 스트롱 번호를 클릭하세요</div>`;
      }
    }

    function updateBibleHeader(card) {
      const s = sectionEl(card.id);
      if (!s) return;
      const navVer = state.viewer[0] || state.primary;
      const bp = s.querySelector('[data-act="book"]'); if (bp) bp.textContent = bookShortFor(navVer, card.book) || "…";
      const cp = s.querySelector('[data-act="chapter"]'); if (cp) cp.textContent = card.chapter + "장";
    }
    function updateLinkHeader(card) {
      const s = sectionEl(card.id);
      if (!s) return;
      const lp = s.querySelector('[data-act="link"]');
      const src = linkedBible(card);
      if (lp) lp.textContent = src ? src.id : "연결 없음";
    }

    // Reload interlinear cards that follow the given bible card (its book/chapter
    // changed). Lexicon cards are driven by clicks, so they aren't reloaded here.
    function reloadDependents(card) {
      cards.filter((c) => c.type === "interlinear" && linkedBible(c) === card)
        .forEach(loadInterlinearCard);
    }

    // ---- mutations (add / remove) ----
    // New cards appear at the CENTER of the workspace, on top of everything,
    // with a small cascade offset so consecutive adds don't perfectly overlap.
    // Existing cards keep their positions (the user rearranges manually).

    function addCard(type) {
      // Free tier (Phase 1): a single card only. Premium unlocks the workspace.
      if (!state.isPremium && cards.length >= 1) {
        toast("무료 버전은 카드를 1개만 사용할 수 있습니다 (프리미엄에서 자유 배치 해제)");
        return;
      }
      if (type === "bible" && bibleCards().length >= MAX_BIBLE) {
        toast(`성경 카드는 최대 ${MAX_BIBLE}개까지 추가할 수 있습니다`);
        return;
      }
      const id = nextId(type);
      const w = 33, h = 60;
      const off = (cascadeN++ % 4) * 4;
      const geom = {
        x: Math.min((100 - w) / 2 + off, 100 - w),
        y: Math.min((100 - h) / 2 + off, 100 - h),
        w, h, z: ++zTop,
      };
      let card;
      if (type === "bible") {
        const base = firstBible();
        card = {
          id, type: "bible",
          version: base ? base.version : state.primary,
          book: base ? base.book : state.lastBook,
          chapter: base ? base.chapter : state.lastChapter,
          locked: false, ...geom,
        };
        seedHistory(card);
      } else {
        card = { id, type, link: (firstBible() && firstBible().id) || null, ...geom };
      }
      cards.push(card);
      renderAll();
      saveLayout();
    }

    function removeCard(id) {
      const i = cards.findIndex((c) => c.id === id);
      if (i < 0) return;
      cards.splice(i, 1);
      renderAll();
      saveLayout();
    }

    // ---- per-card navigation history (카드별 독립 탐색 이력) ----
    // Each bible card remembers the {book, chapter} references it has visited so
    // its ◀ ▶ buttons step back/forward WITHOUT disturbing any other card. The
    // history is session-only (not serialized) and is seeded with the card's
    // initial reference on init/add. recordHistory() is called after any user
    // navigation; back/forward set the reference directly and DON'T record.

    function seedHistory(card) {
      if (!card || card.type !== "bible") return;
      card.history = [{ book: card.book, chapter: card.chapter, verse: null }];
      card.historyIndex = 0;
    }

    // Record the card's current reference (with the starting verse) as a new
    // history entry, dropping any forward entries — we're branching. When the
    // book+chapter already match the current entry, just refresh its verse (e.g.
    // a clipboard hit on the same chapter) without growing the stack. The verse
    // a user scrolled to before leaving is captured live by syncInterlinFrom.
    function recordHistory(card, verse) {
      if (!card || card.type !== "bible") return;
      if (!Array.isArray(card.history)) seedHistory(card);
      const h = card.history;
      const v = verse || null;
      const cur = h[card.historyIndex];
      if (cur && cur.book === card.book && cur.chapter === card.chapter) {
        cur.verse = v;
        return;
      }
      if (card.historyIndex < h.length - 1) h.splice(card.historyIndex + 1);
      h.push({ book: card.book, chapter: card.chapter, verse: v });
      card.historyIndex = h.length - 1;
      updateNavButtons(card);
    }

    // Enable/disable the ◀ ▶ buttons based on the card's position in its history.
    function updateNavButtons(card) {
      const s = sectionEl(card.id);
      if (!s) return;
      const len = Array.isArray(card.history) ? card.history.length : 0;
      const i = card.historyIndex || 0;
      const back = s.querySelector('[data-act="back"]');
      const fwd = s.querySelector('[data-act="forward"]');
      if (back) back.classList.toggle("disabled", i <= 0);
      if (fwd) fwd.classList.toggle("disabled", i >= len - 1);
    }

    // Scroll a bible card's body so the given verse sits at the TOP of the
    // scrollport (block:'start'). No-op for a falsy verse (stay at natural top).
    function scrollVerseToTop(card, verse) {
      if (!verse) return;
      const body = bodyEl(card.id);
      if (!body) return;
      const el = body.querySelector(`.v[data-v="${verse}"]`);
      if (el) el.scrollIntoView({ block: "start" });
    }

    // Step the card's reference along its own history (delta -1 back, +1 forward).
    // Restores the remembered verse to the top of the panel. Does NOT record a
    // new entry; other cards are untouched.
    async function cardHistoryNav(card, delta) {
      if (!card || card.type !== "bible" || !Array.isArray(card.history)) return;
      const j = card.historyIndex + delta;
      if (j < 0 || j >= card.history.length) return;
      card.historyIndex = j;
      const ref = card.history[j];
      card.book = ref.book;
      card.chapter = ref.chapter;
      await loadBibleCard(card);
      reloadDependents(card);
      scrollVerseToTop(card, ref.verse);   // restore scroll position (작업 5)
      if (card === primaryBible()) api().note_position(card.book, card.chapter);
      updateNavButtons(card);
      saveLayout();
    }

    // ---- chapter stepping ----

    async function cardChapStep(card, delta) {
      const chs = await chaptersFor(state.viewer[0] || state.primary, card.book);
      const j = chs.indexOf(card.chapter) + delta;
      if (j < 0 || j >= chs.length) return;
      card.chapter = chs[j];
      await loadBibleCard(card);
      reloadDependents(card);
      recordHistory(card);
      if (card === primaryBible()) api().note_position(card.book, card.chapter);
      saveLayout();
    }
    function chapStepPrimary(delta) {
      const pb = primaryBible();
      if (pb) cardChapStep(pb, delta);
    }
    // Keyboard ←/→ targets the ACTIVE card (falls back to the primary card).
    function chapStepActive(delta) {
      const card = activeBibleCard();
      if (card) cardChapStep(card, delta);
    }
    function linkedBibleFor(id) {
      const card = cardById(id);
      return card ? linkedBible(card) : null;
    }

    // ---- clipboard auto-navigation ----
    // Routing rule:
    //  1. A LOCKED card whose current book+chapter matches the incoming reference
    //     takes priority (it reacts in place — no navigation, just verse highlight).
    //  2. Otherwise the FIRST unlocked card (by index) receives and navigates.
    // Only ONE card reacts per clipboard event.

    async function goToRef(book, chapter, verses) {
      const bibles = bibleCards();
      // Priority 1: locked card that already shows this book+chapter.
      const matchedLocked = bibles.find(
        (c) => c.locked && c.book === book && c.chapter === chapter
      );
      // Priority 2: first unlocked card.
      const firstUnlocked = bibles.find((c) => !c.locked);
      const target = matchedLocked || firstUnlocked;
      if (!target) return;

      if (!target.locked) {
        // Navigate to the incoming position.
        target.book = book;
        const chs = await chaptersFor(state.viewer[0] || state.primary, book);
        target.chapter = chs.includes(chapter) ? chapter : (chs[0] || chapter);
      }
      // Render (highlight the specific verses).
      await loadBibleCard(target, verses && verses.length ? verses : null);
      reloadDependents(target);
      // A locked card reacts in place (book/chapter unchanged) → recordHistory
      // refreshes the entry's verse; an unlocked card that navigated records the
      // new reference, remembering the first highlighted verse as its anchor.
      const anchorVerse = verses && verses.length ? verses[0] : null;
      recordHistory(target, anchorVerse);

      const pb = primaryBible();
      if (pb) api().note_position(pb.book, pb.chapter);
      saveLayout();
    }

    // ---- header-control actions (delegated) ----

    async function handleAction(card, act, actEl) {
      if (!card) return;
      const navVer = state.viewer[0] || state.primary;
      switch (act) {
        case "book": {
          const bs = await booksFor(navVer);
          openMenu(actEl,
            bs.map((b) => ({ label: b.long, value: b.num, on: b.num === card.book })),
            async (num) => {
              card.book = num;
              const chs = await chaptersFor(navVer, num);
              card.chapter = chs[0] || 1;
              await loadBibleCard(card);
              reloadDependents(card);
              recordHistory(card);
              if (card === primaryBible()) api().note_position(card.book, card.chapter);
              saveLayout();
            });
          break;
        }
        case "chapter": {
          const chs = await chaptersFor(navVer, card.book);
          openMenu(actEl,
            chs.map((c) => ({ label: String(c), value: c, on: c === card.chapter })),
            async (c) => {
              card.chapter = c;
              await loadBibleCard(card);
              reloadDependents(card);
              recordHistory(card);
              if (card === primaryBible()) api().note_position(card.book, card.chapter);
              saveLayout();
            }, { grid: true });
          break;
        }
        case "prev": cardChapStep(card, -1); break;
        case "next": cardChapStep(card, 1); break;
        case "back": cardHistoryNav(card, -1); break;
        case "forward": cardHistoryNav(card, 1); break;
        case "lock": toggleLock(card); break;
        case "close": removeCard(card.id); break;
        case "link":
          openMenu(actEl,
            bibleCards().map((b) => ({ label: b.id, value: b.id, on: b.id === card.link })),
            (id) => { card.link = id; loadCard(card); saveLayout(); });
          break;
      }
    }

    // ---- free-form interaction engine (move · resize · snap · push · z-order) ----

    function applyGeom(card) {
      const el = sectionEl(card.id);
      if (!el) return;
      el.style.left = card.x + "%";
      el.style.top = card.y + "%";
      el.style.width = card.w + "%";
      el.style.height = card.h + "%";
      el.style.zIndex = card.z;
    }

    // Overlap allowed (free placement) — clicking/dragging a card raises it.
    // Card z-indexes are kept low (renormalized to 1..n once zTop passes a small
    // threshold) so they can NEVER climb above overlay layers — dropdown menus,
    // snap guides, tooltips, the log drawer (z-index 80+) — which previously got
    // hidden behind cards after enough clicks.
    function bringToFront(card) {
      setActive(card); // focus highlight updates even when z doesn't change
      if (card.z >= zTop) return;
      card.z = ++zTop;
      if (zTop > 50) {
        // Renormalize: preserve stacking order, reassign 1..n.
        const sorted = [...cards].sort((a, b) => (a.z || 0) - (b.z || 0));
        sorted.forEach((c, i) => { c.z = i + 1; });
        zTop = sorted.length;
        cards.forEach(applyGeom);
      } else {
        const el = sectionEl(card.id);
        if (el) el.style.zIndex = card.z;
      }
      saveLayout();
    }

    // ---- active (focused) card (활성 카드) ----
    // Exactly one card carries the .active neon stroke at a time; it is also the
    // target for keyboard ←/→ chapter stepping. Updated on every bringToFront
    // (click / drag / resize / programmatic raise).
    function setActive(card) {
      if (!card) return;
      activeId = card.id;
      const c = container();
      if (!c) return;
      c.querySelectorAll(".mcard.active").forEach((el) => {
        if (el.dataset.id !== card.id) el.classList.remove("active");
      });
      const el = sectionEl(card.id);
      if (el) el.classList.add("active");
    }

    // The bible card to target for keyboard stepping: the active card if it's a
    // bible card, else the primary (first) bible card as a fallback.
    function activeBibleCard() {
      const c = activeId && cardById(activeId);
      return (c && c.type === "bible") ? c : primaryBible();
    }

    // PowerPoint-style alignment guides (shown while a snap is active).
    // g.kind (optional, e.g. "div" for workspace dividers) becomes an extra class.
    function renderGuides(guides) {
      clearGuides();
      const c = container();
      if (!c) return;
      guides.forEach((g) => {
        const el = document.createElement("div");
        el.className = "snap-guide " + g.axis + (g.kind ? " " + g.kind : "");
        if (g.axis === "v") el.style.left = g.at + "%";
        else el.style.top = g.at + "%";
        c.appendChild(el);
      });
    }
    function clearGuides() {
      const c = container();
      if (c) c.querySelectorAll(".snap-guide").forEach((g) => g.remove());
    }

    // Snap a moving edge to the nearest target within the threshold.
    // Targets are numbers or {at, kind} objects. Strict "<" comparison means
    // earlier entries win ties → card targets (listed first) beat divider targets.
    function snapTo(edge, targets, th, guides, axis) {
      let best = th, hit = null;
      targets.forEach((t) => {
        const at = typeof t === "number" ? t : t.at;
        const d = Math.abs(edge - at);
        if (d < best) { best = d; hit = t; }
      });
      if (hit !== null) {
        const at = typeof hit === "number" ? hit : hit.at;
        guides.push({ axis, at, kind: typeof hit === "object" ? hit.kind : undefined });
        return at;
      }
      return edge;
    }

    // ---- push computation (joinAt 기반; 3차 작업 2) ----
    //
    // For a growing edge in direction `dir`, every card in the push path gets a
    // `joinAt`: the grow distance at which the edge (or the chain ahead of it)
    // makes GUTTER-spaced contact with that card.
    //   · already attached at gesture start → joinAt = 0
    //   · reached mid-gesture               → joinAt = pusher's joinAt + (gap − GUTTER)
    // Displacement of member i = max(0, grow − joinAt_i)   → no jumps, no snap-backs.
    // Boundary clamp           = grow ≤ min_i(joinAt_i + space_i)  (and own space).
    // grow is never clamped to the contact distance itself — contact only records joinAt.
    function computePush(dir, rawGrow, card, orig) {
      const horiz = dir === "e" || dir === "w";
      const fwd = dir === "e" || dir === "s";   // forward = increasing coordinate
      const g0 = orig.get(card);
      // geometry helpers on orig snapshots
      const lead = (g) => horiz ? (fwd ? g.x + g.w : g.x) : (fwd ? g.y + g.h : g.y);
      const trail = (g) => horiz ? (fwd ? g.x : g.x + g.w) : (fwd ? g.y : g.y + g.h);
      const gapBetween = (mG, oG) => fwd ? trail(oG) - lead(mG) : lead(mG) - trail(oG);
      const space = (g) => {
        if (dir === "e") return 100 - (g.x + g.w);
        if (dir === "w") return g.x;
        if (dir === "s") return 100 - (g.y + g.h);
        return g.y;
      };
      const crossOverlap = (a, b) => horiz
        ? (a.y < b.y + b.h - ATTACH_EPS && a.y + a.h > b.y + ATTACH_EPS)
        : (a.x < b.x + b.w - ATTACH_EPS && a.x + a.w > b.x + ATTACH_EPS);

      // Iteratively discover the push chain + each member's joinAt.
      const joinAt = new Map();   // card → joinAt distance
      let changed = true;
      while (changed) {
        changed = false;
        const movers = [{ g: g0, j: 0 }];
        joinAt.forEach((j, c) => movers.push({ g: orig.get(c), j }));
        cards.forEach((c) => {
          if (c === card || joinAt.has(c)) return;
          const cG = orig.get(c);
          if (!cG) return;
          let best = null;
          movers.forEach(({ g: mG, j }) => {
            const gap = gapBetween(mG, cG);
            if (gap < -ATTACH_EPS) return;            // behind the mover (or deep overlap)
            if (!crossOverlap(mG, cG)) return;
            const contact = j + Math.max(0, gap - GUTTER);
            if (best === null || contact < best) best = contact;
          });
          if (best !== null && best < rawGrow) {
            joinAt.set(c, best);
            changed = true;
          }
        });
      }

      // Boundary clamp: own free space, and joinAt_i + free space of every member.
      // (members sit in front of the growing edge, so their clamps are naturally
      // tighter than the own-space clamp whenever a chain exists)
      let grow = Math.min(rawGrow, space(g0));
      joinAt.forEach((j, c) => {
        grow = Math.min(grow, j + space(orig.get(c)));
      });
      grow = Math.max(0, grow);

      // Displacements with the final grow.
      const disp = new Map();
      joinAt.forEach((j, c) => {
        const d = grow - j;
        if (d > 0) disp.set(c, d);
      });
      return { grow, disp };
    }

    // Header-drag move with snap + alignment guides.
    // Card-to-card snaps land GUTTER apart; card-to-boundary snaps stay flush.
    function startMove(card, sec, e) {
      interacting = true; // block layout writes for the whole gesture (Phase 2)
      bringToFront(card);
      const cont = container().getBoundingClientRect();
      const sx = e.clientX, sy = e.clientY;
      const ox = card.x, oy = card.y;
      const others = cards.filter((c) => c !== card);
      const thX = (SNAP_PX / cont.width) * 100, thY = (SNAP_PX / cont.height) * 100;
      sec.classList.add("moving");
      let moved = false;
      const onMove = (ev) => {
        moved = true;
        let nx = ox + ((ev.clientX - sx) / cont.width) * 100;
        let ny = oy + ((ev.clientY - sy) / cont.height) * 100;
        nx = Math.max(0, Math.min(100 - card.w, nx));
        ny = Math.max(0, Math.min(100 - card.h, ny));
        const guides = [];

        // Directional snap targets: cards first (gutter-offset + align), then
        // workspace bounds (flush), then divider lines (flush; lowest tie priority).
        const xLeft = [], xRight = [], yTop = [], yBottom = [];
        others.forEach((o) => {
          xLeft.push(o.x + o.w + GUTTER, o.x);       // gutter-after + align-left
          xRight.push(o.x - GUTTER, o.x + o.w);      // gutter-before + align-right
          yTop.push(o.y + o.h + GUTTER, o.y);
          yBottom.push(o.y - GUTTER, o.y + o.h);
        });
        xLeft.push(0); xRight.push(100); yTop.push(0); yBottom.push(100);
        DIV_X.forEach((d) => { xLeft.push({ at: d, kind: "div" }); xRight.push({ at: d, kind: "div" }); });
        DIV_Y.forEach((d) => { yTop.push({ at: d, kind: "div" }); yBottom.push({ at: d, kind: "div" }); });

        const sl = snapTo(nx, xLeft, thX, guides, "v");
        if (sl !== nx) nx = sl;
        else { const sr = snapTo(nx + card.w, xRight, thX, guides, "v"); if (sr !== nx + card.w) nx = sr - card.w; }

        const st = snapTo(ny, yTop, thY, guides, "h");
        if (st !== ny) ny = st;
        else { const sb = snapTo(ny + card.h, yBottom, thY, guides, "h"); if (sb !== ny + card.h) ny = sb - card.h; }

        card.x = Math.max(0, Math.min(100 - card.w, nx));
        card.y = Math.max(0, Math.min(100 - card.h, ny));
        applyGeom(card);
        renderGuides(guides);
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        sec.classList.remove("moving");
        clearGuides();
        interacting = false;
        if (moved) saveLayout();
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }

    // Edge/corner resize with gutter-snap + joinAt-based PUSH (see computePush).
    //
    // Convention: all growth magnitudes ("grow"/"raw") are POSITIVE numbers.
    //   "e" grow: east edge moves right.   "w" grow: west edge moves left.
    //   "s" grow: south edge moves down.   "n" grow: north edge moves up.
    function startResizeCard(card, sec, dirs, e) {
      interacting = true; // block layout writes for the whole gesture (Phase 2)
      bringToFront(card);
      const cont = container().getBoundingClientRect();
      const sx = e.clientX, sy = e.clientY;
      // Idempotent: every frame resets to orig before re-applying.
      const orig = new Map(cards.map((c) => [c, { x: c.x, y: c.y, w: c.w, h: c.h }]));
      const o0 = orig.get(card);
      const thX = (SNAP_PX / cont.width) * 100, thY = (SNAP_PX / cont.height) * 100;

      sec.classList.add("resizing");
      const onMove = (ev) => {
        cards.forEach((c) => Object.assign(c, orig.get(c)));
        const dx = ((ev.clientX - sx) / cont.width) * 100;
        const dy = ((ev.clientY - sy) / cont.height) * 100;
        const guides = [];
        const others = cards.filter((c) => c !== card);

        // Snap targets per direction: cards first (gutter offset + edge align),
        // then workspace bounds, then divider lines (lowest tie priority).
        const xEast = [], xWest = [], ySouth = [], yNorth = [];
        others.forEach((o) => {
          const g = orig.get(o);
          xEast.push(g.x - GUTTER, g.x, g.x + g.w);
          xWest.push(g.x + g.w + GUTTER, g.x + g.w, g.x);
          ySouth.push(g.y - GUTTER, g.y, g.y + g.h);
          yNorth.push(g.y + g.h + GUTTER, g.y + g.h, g.y);
        });
        xEast.push(100); xWest.push(0); ySouth.push(100); yNorth.push(0);
        DIV_X.forEach((d) => { xEast.push({ at: d, kind: "div" }); xWest.push({ at: d, kind: "div" }); });
        DIV_Y.forEach((d) => { ySouth.push({ at: d, kind: "div" }); yNorth.push({ at: d, kind: "div" }); });

        if (dirs.includes("e")) {
          const snapped = snapTo(o0.x + o0.w + dx, xEast, thX, guides, "v");
          const raw = snapped - (o0.x + o0.w);
          if (raw > 0) {
            const { grow, disp } = computePush("e", raw, card, orig);
            disp.forEach((d, c) => { c.x = orig.get(c).x + d; });
            card.w = o0.w + grow;
          } else {
            card.w = Math.max(MIN_W, o0.w + raw);
          }
        }
        if (dirs.includes("w")) {
          const snapped = snapTo(o0.x + dx, xWest, thX, guides, "v");
          const eastFixed = o0.x + o0.w;
          const raw = o0.x - snapped;        // positive = west edge moving left (growing)
          if (raw > 0) {
            const { grow, disp } = computePush("w", raw, card, orig);
            disp.forEach((d, c) => { c.x = orig.get(c).x - d; });
            card.x = o0.x - grow;
          } else {
            card.x = Math.min(eastFixed - MIN_W, o0.x - raw);
          }
          card.w = eastFixed - card.x;
        }
        if (dirs.includes("s")) {
          const snapped = snapTo(o0.y + o0.h + dy, ySouth, thY, guides, "h");
          const raw = snapped - (o0.y + o0.h);
          if (raw > 0) {
            const { grow, disp } = computePush("s", raw, card, orig);
            disp.forEach((d, c) => { c.y = orig.get(c).y + d; });
            card.h = o0.h + grow;
          } else {
            card.h = Math.max(MIN_H, o0.h + raw);
          }
        }
        if (dirs.includes("n")) {
          const snapped = snapTo(o0.y + dy, yNorth, thY, guides, "h");
          const southFixed = o0.y + o0.h;
          const raw = o0.y - snapped;        // positive = north edge moving up (growing)
          if (raw > 0) {
            const { grow, disp } = computePush("n", raw, card, orig);
            disp.forEach((d, c) => { c.y = orig.get(c).y - d; });
            card.y = o0.y - grow;
          } else {
            card.y = Math.min(southFixed - MIN_H, o0.y - raw);
          }
          card.h = southFixed - card.y;
        }

        cards.forEach(applyGeom);
        renderGuides(guides);
      };
      const onUp = () => {
        document.removeEventListener("mousemove", onMove);
        document.removeEventListener("mouseup", onUp);
        sec.classList.remove("resizing");
        clearGuides();
        interacting = false;
        saveLayout();
      };
      document.addEventListener("mousemove", onMove);
      document.addEventListener("mouseup", onUp);
    }

    // ---- 본문 → 원어 실시간 스크롤 동기화 ----
    // Keyed to the topmost FULLY-visible verse in the bible card (a verse whose
    // top edge is cut off doesn't count); linked interlinear cards scroll so the
    // same verse sits at their top. One-way (bible → interlinear), rAF-throttled.

    let syncRaf = null;
    let scrollTimer = null;   // 500ms debounce for locking the history verse (7차-2)

    // The topmost fully-visible verse number in a scripture body (or null).
    function topVerseOf(body) {
      const bodyTop = body.getBoundingClientRect().top;
      for (const v of body.querySelectorAll(".v[data-v]")) {
        if (v.getBoundingClientRect().top >= bodyTop - 2) return +v.dataset.v;
      }
      return null;
    }

    // Real-time (every frame): keep linked interlinear cards aligned to the
    // bible card's top verse. Does NOT touch history — that's debounced (7차-2).
    function syncInterlinFrom(card, body) {
      const n = topVerseOf(body);
      if (!n) return;
      cards
        .filter((c) => c.type === "interlinear" && linkedBible(c) === card)
        .forEach((ic) => {
          const ib = bodyEl(ic.id);
          if (!ib) return;
          const target = ib.querySelector(`.v[data-v="${n}"]`);
          if (!target) return;
          ib.scrollTop += target.getBoundingClientRect().top - ib.getBoundingClientRect().top;
        });
    }

    // Debounced (500ms after scrolling stops): lock the settled top verse into
    // the card's current history entry so ◀ ▶ restore the scroll position. While
    // the wheel is moving, history writes are held off entirely (7차-2).
    function lockHistoryVerse(card, body) {
      const n = topVerseOf(body);
      if (!n) return;
      card.verse = n;
      if (Array.isArray(card.history) && card.history[card.historyIndex]) {
        card.history[card.historyIndex].verse = n;
      }
      saveLayout();
    }

    function wireContainer() {
      const c = container();
      if (!c) return;

      // Click: strong-code lookup, header actions, or verse copy.
      c.addEventListener("click", (e) => {
        const codeEl = e.target.closest("[data-code]");
        if (codeEl) { handleCodeClick(codeEl); return; }
        const actEl = e.target.closest("[data-act]");
        if (actEl) {
          const sec = e.target.closest(".mcard");
          if (sec) handleAction(cardById(sec.dataset.id), actEl.dataset.act, actEl);
          return;
        }
        // Verse click → copy (only when there's no active text selection).
        const sel = window.getSelection();
        if (sel && !sel.isCollapsed) return;
        const v = e.target.closest('.mcard[data-type="bible"] .v[data-v]');
        if (v) {
          const card = cardById(v.closest(".mcard").dataset.id);
          if (card) copyVersesFromCard(card, [+v.dataset.v]);
        }
      });

      // Drag-select across verses → copy the intersected range.
      c.addEventListener("mouseup", (e) => {
        const sel = window.getSelection();
        if (!sel || sel.isCollapsed || !sel.rangeCount || !sel.toString().trim()) return;
        const sec = e.target.closest('.mcard[data-type="bible"]');
        if (!sec) return;
        const card = cardById(sec.dataset.id);
        if (!card) return;
        const range = sel.getRangeAt(0);
        const verses = [...sec.querySelectorAll(".v[data-v]")]
          .filter((el) => range.intersectsNode(el))
          .map((el) => +el.dataset.v);
        if (verses.length) copyVersesFromCard(card, verses);
      });

      // Right-click an original-language word / cross-ref → independent window.
      c.addEventListener("contextmenu", (e) => {
        const t = e.target.closest("[data-code]");
        if (!t) return;
        e.preventDefault();
        hideTip();
        const sec = t.closest(".mcard");
        let book = lexCur && lexCur.book, chapter = lexCur && lexCur.chapter;
        if (sec && sec.dataset.type === "interlinear") {
          const src = linkedBible(cardById(sec.dataset.id));
          if (src) { book = src.book; chapter = src.chapter; }
        }
        api().open_dict_window(t.dataset.code, lexLang, book, chapter, t.dataset.v || null,
          root.dataset.theme || "light");
      });

      // Hover an interlinear word → delayed preview tooltip.
      c.addEventListener("mouseover", (e) => {
        const s = e.target.closest('.mcard[data-type="interlinear"] .strong[data-code]');
        if (!s) return;
        const src = linkedBible(cardById(s.closest(".mcard").dataset.id));
        scheduleTip(s.dataset.code, s.dataset.v, src && src.book, src && src.chapter, e.clientX, e.clientY);
      });
      c.addEventListener("mouseout", (e) => {
        if (e.target.closest(".strong[data-code]")) hideTip();
      });

      // Scroll inside a scripture body → hide tooltips + sync linked interlinear
      // cards to the topmost fully-visible verse (실시간 동기화). The history
      // verse is locked only once scrolling settles for 500ms (7차-2): the rAF
      // keeps the interlinear alignment live, the timer holds off history writes.
      c.addEventListener("scroll", (e) => {
        hideTip();
        const body = e.target;
        if (!body.classList || !body.classList.contains("scripture")) return;
        const sec = body.closest(".mcard");
        if (!sec || sec.dataset.type !== "bible") return;
        const card = cardById(sec.dataset.id);
        if (!card) return;
        if (syncRaf) cancelAnimationFrame(syncRaf);
        syncRaf = requestAnimationFrame(() => {
          syncRaf = null;
          syncInterlinFrom(card, body);
        });
        if (scrollTimer) clearTimeout(scrollTimer);
        scrollTimer = setTimeout(() => {
          scrollTimer = null;
          lockHistoryVerse(card, body);
        }, 500);
      }, true);

      // Mousedown: resize handles → resize, header → move, anywhere else → raise.
      c.addEventListener("mousedown", (e) => {
        const sec = e.target.closest(".mcard");
        if (!sec) return;
        const card = cardById(sec.dataset.id);
        if (!card) return;
        const rs = e.target.closest(".rs");
        if (rs) {
          e.preventDefault();
          startResizeCard(card, sec, rs.dataset.rs, e);
          return;
        }
        const hd = e.target.closest(".card-hd");
        if (hd && !e.target.closest("[data-act], .hd-pill, .hd-mini")) {
          e.preventDefault();
          startMove(card, sec, e);
          return;
        }
        bringToFront(card);
      });
    }

    function refreshSearchPrimary() {
      state.searchVersion = primaryVersion();
      updateSearchVerLabel();
    }

    // ---- public ----
    async function init(layout) {
      cards = restore(layout);
      // Free tier (Phase 1): collapse to a single card (prefer the first bible
      // card). Premium keeps the full saved workspace.
      if (!state.isPremium && cards.length > 1) {
        const keep = cards.find((c) => c.type === "bible") || cards[0];
        cards = [keep];
      }
      cards.forEach(seedHistory); // seed per-card nav history (bible cards only)
      normalizeLocks();
      zTop = Math.max(1, ...cards.map((c) => c.z || 1));
      // Preload the nav version's book list so headers fill at once.
      await booksFor(state.viewer[0] || state.primary);
      wireContainer();
      renderAll();
    }

    function primaryVersion() {
      return state.viewer[0] || state.primary;
    }
    function reloadAllBible() {
      bibleCards().forEach((card) => loadBibleCard(card));
    }
    // Add a non-bible card with a specific link (used by showStrong to create a
    // lexicon card pre-linked to the source bible).
    function addCardWithLink(type, linkId) {
      if (!state.isPremium && cards.length >= 1) {
        toast("무료 버전은 카드를 1개만 사용할 수 있습니다 (프리미엄에서 해제)");
        return null;
      }
      const id = nextId(type);
      const w = 33, h = 60;
      const off = (cascadeN++ % 4) * 4;
      const card = {
        id, type,
        link: linkId || (firstBible() && firstBible().id) || null,
        x: Math.min((100 - w) / 2 + off, 100 - w),
        y: Math.min((100 - h) / 2 + off, 100 - h),
        w, h, z: ++zTop,
      };
      cards.push(card);
      renderAll();
      saveLayout();
      return card;
    }

    return { init, addCard, addCardWithLink, goToRef, primaryVersion,
             primaryBible, bibleCards, lexiconCards, bodyEl, linkedBibleFor,
             chapStepPrimary, chapStepActive, reloadAllBible };
  })();

  // ---- Scripture / interlinear / lexicon rendering (into a card body) ----

  function renderVersesInto(body, verses, highlight) {
    if (!verses || !verses.length) {
      body.innerHTML = `<div class="panel-loading">본문 없음</div>`;
      return;
    }
    const hl = new Set(highlight || []);
    body.innerHTML = verses
      .map((v) => `<div class="v${hl.has(v.n) ? " hl" : ""}" data-v="${v.n}"><span class="vnum">${v.n}</span>${esc(v.text)}</div>`)
      .join("");
    if (hl.size) {
      const first = body.querySelector(".v.hl");
      if (first) first.scrollIntoView({ block: "center" });
    }
  }

  // Multi-version parallel rendering for bible cards.
  // versions: [name, ...], chapDataArr: [{verses:[{n,text}]}, ...] (parallel)
  function renderMultiVersesInto(body, versions, chapDataArr, highlight) {
    const verseMap = new Map();
    chapDataArr.forEach((ch, vi) => {
      ((ch && ch.verses) || []).forEach((v) => {
        if (!verseMap.has(v.n)) verseMap.set(v.n, { n: v.n, texts: {} });
        verseMap.get(v.n).texts[versions[vi]] = v.text;
      });
    });
    if (!verseMap.size) { body.innerHTML = `<div class="panel-loading">본문 없음</div>`; return; }
    const hl = new Set(highlight || []);
    const multi = versions.length > 1;
    body.innerHTML = [...verseMap.values()]
      .sort((a, b) => a.n - b.n)
      .map((v) => {
        let content;
        if (multi) {
          content = versions.map((ver) => {
            const text = v.texts[ver];
            if (!text) return "";
            return `<div class="vline"><span class="vver">${esc(ver)}</span>${esc(text)}</div>`;
          }).filter(Boolean).join("");
        } else {
          content = esc(v.texts[versions[0]] || "");
        }
        return `<div class="v${hl.has(v.n) ? " hl" : ""}${multi ? " multi" : ""}" data-v="${v.n}">` +
          `<span class="vnum">${v.n}</span>${content}</div>`;
      }).join("");
    if (hl.size) {
      const first = body.querySelector(".v.hl");
      if (first) first.scrollIntoView({ block: "center" });
    }
  }

  function renderInterlinearInto(body, data) {
    if (!data || !data.length) {
      body.innerHTML = `<div class="panel-loading">원어 데이터 없음</div>`;
      return;
    }
    body.innerHTML = data
      .map((row) => {
        const words = row.words
          .map((w) =>
            w.code
              ? `${esc(w.w)}<span class="strong" data-code="${esc(w.code)}" data-v="${row.n}">${esc(w.code)}</span>`
              : esc(w.w)
          )
          .join(" ");
        return `<div class="v" data-v="${row.n}"><span class="vnum">${row.n}</span>${words}</div>`;
      })
      .join("");
  }

  let lexLang = "ko";       // dictionary language (한글/영어 toggle)
  let lexCur = null;        // {code, verse, book, chapter} — global fallback
  // Per-bible-link state: bibleId → {code, verse, book, chapter}
  // Each lexicon card uses the entry for its linked bible, so distinct
  // bible cards keep independent dictionary histories.
  const lexCurMap = new Map();

  function renderMorph(morph) {
    if (!morph || !morph.length) return "";
    const rows = morph
      .map((w) => {
        let s = `<b>${esc(w.lemma)}</b>`;
        if (w.translit) s += ` ${esc(w.translit)}`;
        if (w.pos) s += ` · ${esc(w.pos)}`;
        if (w.gloss && w.gloss !== "_") s += ` · ${esc(w.gloss)}`;
        return s;
      })
      .join("<br>");
    return `<div class="morph"><div class="morph-h">형태소 분석</div>${rows}</div>`;
  }

  function renderLexEntryInto(body, code, res) {
    if (!res) {
      // No entry. Distinguish "no dictionary module installed" (guide the user
      // to add one — copyright-clean default ships without lexicons) from "this
      // code simply isn't in the installed dictionary".
      const noModule = state.lexAvail && !state.lexAvail.ko && !state.lexAvail.en;
      const msg = noModule
        ? `원어 사전 모듈이 없습니다.<br>한글/영어 사전 파일(<b>.dct</b>)을 <b>original_lang</b> 폴더에 넣으면 뜻풀이가 표시됩니다.`
        : `사전 항목 없음`;
      body.innerHTML = `<span class="chip">${esc(code)}</span><div class="lex-body">${msg}</div>`;
      return;
    }
    const head = res.headword
      ? `<div class="lex-head"><span class="heb">${esc(res.headword)}</span>` +
        `<span class="rom">${esc(res.reading)}</span></div>`
      : "";
    body.innerHTML =
      `<span class="chip">${esc(res.code)}</span>${head}${renderMorph(res.morph)}` +
      `<div class="lex-body">${res.html || "사전 항목 없음"}</div>`;
  }

  // Look up a Strong's code and render it into the lexicon card(s) linked to
  // `sourceBibleId`. If none exist, a new lexicon card is created pre-linked to
  // that bible. Cross-reference clicks inside a lexicon card update only that card.
  //
  // sourceBibleId = null → fall back to updating all lexicon cards (rare legacy path).
  async function showStrong(code, verse, book, chapter, sourceBibleId) {
    const cur = { code, verse: verse || null, book: book || null, chapter: chapter || null };
    lexCur = cur;  // global fallback (used by cards whose link resolves to null)
    if (sourceBibleId) lexCurMap.set(sourceBibleId, cur);

    // Determine which lexicon cards to update.
    let targets = sourceBibleId
      ? CardManager.lexiconCards().filter((c) => {
          const lb = CardManager.linkedBibleFor(c.id);
          return lb && lb.id === sourceBibleId;
        })
      : CardManager.lexiconCards();

    // If no lexicon card exists for this bible, create one linked to it.
    if (!targets.length) {
      const created = CardManager.addCardWithLink("lexicon", sourceBibleId);
      if (created) targets = [created];
    }

    targets.forEach((c) => {
      const b = CardManager.bodyEl(c.id);
      if (b) b.innerHTML = `<div class="panel-loading">[${esc(code)}] 불러오는 중…</div>`;
    });
    const res = await api().lookup_strong(code, lexLang, cur.book, cur.chapter, cur.verse);
    // Re-query in case a new card was just created and re-rendered.
    const finalTargets = sourceBibleId
      ? CardManager.lexiconCards().filter((c) => {
          const lb = CardManager.linkedBibleFor(c.id);
          return lb && lb.id === sourceBibleId;
        })
      : CardManager.lexiconCards();
    finalTargets.forEach((c) => {
      const b = CardManager.bodyEl(c.id);
      if (b) renderLexEntryInto(b, code, res);
    });
  }

  function handleCodeClick(el) {
    const sec = el.closest(".mcard");
    let book = null, chapter = null, verse = el.dataset.v || null;
    let sourceBibleId = null;

    if (sec && sec.dataset.type === "interlinear") {
      // Interlinear click: resolve the linked bible for book/chapter + routing.
      const src = CardManager.linkedBibleFor(sec.dataset.id);
      if (src) { book = src.book; chapter = src.chapter; sourceBibleId = src.id; }
    } else if (sec && sec.dataset.type === "lexicon") {
      // Lexicon cross-reference click: update only this card's bible link.
      const lb = CardManager.linkedBibleFor(sec.dataset.id);
      if (lb) sourceBibleId = lb.id;
      verse = null;  // cross-refs have no verse context
    }

    showStrong(el.dataset.code, verse, book, chapter, sourceBibleId);
  }

  async function copyVersesFromCard(card, verses) {
    if (!verses.length) return;
    const r = await api().copy_reference(card.book, card.chapter, verses, [card.version]);
    if (!r || !r.ok) return;
    toast(`${bookShortFor(card.version, card.book)} ${card.chapter}:${verses.join(",")} 복사됨`);
    const body = CardManager.bodyEl(card.id);
    if (!body) return;
    verses.forEach((n) => {
      const el = body.querySelector(`.v[data-v="${n}"]`);
      if (el) { el.classList.add("copied"); setTimeout(() => el.classList.remove("copied"), 700); }
    });
  }

  // ---- Hover tooltip over original-language words ----

  let tipTimer = null, tipEl = null, tipKey = null;

  function hideTip() {
    if (tipTimer) { clearTimeout(tipTimer); tipTimer = null; }
    if (tipEl) { tipEl.remove(); tipEl = null; }
    tipKey = null;
  }

  function scheduleTip(code, verse, book, chapter, x, y) {
    const key = code + ":" + verse;
    if (key === tipKey) return;
    hideTip();
    tipKey = key;
    tipTimer = setTimeout(async () => {
      const res = await api().hover_summary(code, book || null, chapter || null, verse || null);
      if (tipKey !== key) return; // pointer moved away while loading
      const head = res.headword
        ? `<div class="tip-head"><span class="tip-heb">${esc(res.headword)}</span>` +
          (res.reading ? `<span class="tip-rom">${esc(res.reading)}</span>` : "") + `</div>`
        : "";
      const lines = (res.lines || []).map(esc).join("<br>");
      tipEl = document.createElement("div");
      tipEl.className = "lex-tip";
      tipEl.innerHTML = `${head}<span class="tip-code">[${esc(code)}]</span>${lines ? "<br>" + lines : ""}`;
      document.body.appendChild(tipEl);
      const tx = Math.min(x + 14, window.innerWidth - tipEl.offsetWidth - 10);
      const ty = Math.min(y + 16, window.innerHeight - tipEl.offsetHeight - 10);
      tipEl.style.left = Math.max(8, tx) + "px";
      tipEl.style.top = Math.max(8, ty) + "px";
    }, 400);
  }

  // ---- Update check (GitHub releases) ----

  let updateInfo = null;

  async function checkUpdate(silent) {
    if (!silent) toast("업데이트 확인 중…");
    let r = null;
    try { r = await api().check_update(); } catch (e) { r = null; }
    if (!r || !r.ok) { if (!silent) toast("업데이트 확인 실패"); return; }
    if (r.has_update && !(silent && r.skipped)) {
      updateInfo = r;
      $("ub-text").textContent = `새 버전 v${r.latest} 사용 가능 — 현재 v${r.current}`;
      $("update-banner").hidden = false;
    } else if (!silent) {
      toast(`최신 버전입니다 (v${r.current})`);
    }
  }

  function wireUpdate() {
    if ($("update-btn")) $("update-btn").addEventListener("click", () => checkUpdate(false));
    if ($("ub-open")) $("ub-open").addEventListener("click", () => api().open_releases_page());
    if ($("ub-skip")) $("ub-skip").addEventListener("click", () => {
      if (updateInfo) api().skip_update(updateInfo.latest);
      $("update-banner").hidden = true;
    });
    if ($("ub-close")) $("ub-close").addEventListener("click", () => { $("update-banner").hidden = true; });
    if ($("ub-install")) $("ub-install").addEventListener("click", async () => {
      const r = await api().install_update();
      if (!r || !r.ok) { toast(r && r.error ? r.error : "자동 설치를 시작할 수 없습니다"); return; }
      $("ub-text").textContent = "업데이트 다운로드 준비 중…";
      $("ub-install").disabled = true;
    });
  }

  function onUpdateProgress(pct, kb, total) {
    const t = $("ub-text");
    if (t) t.textContent = total ? `다운로드 중… ${pct}% (${kb.toLocaleString()} / ${total.toLocaleString()} KB)`
                                 : `다운로드 중… ${kb.toLocaleString()} KB`;
  }
  function onUpdateReady() {
    const t = $("ub-text");
    if (t) t.textContent = "설치 적용 중… 앱이 곧 재시작됩니다.";
  }
  function onUpdateError(msg) {
    toast("업데이트 실패: " + msg);
    const b = $("ub-install");
    if (b) b.disabled = false;
  }

  // ---- App settings modal (⚙ gear) ----

  function syncLangSeg() {
    const seg = document.querySelector('.seg[data-seg="lang"]');
    if (!seg) return;
    const opts = seg.querySelectorAll(".opt");
    if (opts[0]) opts[0].classList.toggle("on", lexLang === "ko");
    if (opts[1]) opts[1].classList.toggle("on", lexLang === "en");
  }

  function setSeg(seg, current, onPick, eq) {
    if (!seg) return;
    const same = eq || ((a, b) => a === b);
    seg.querySelectorAll(".opt").forEach((opt) => {
      opt.classList.toggle("on", same(opt.dataset.val, current));
      opt.onclick = () => {
        seg.querySelectorAll(".opt").forEach((o) => o.classList.remove("on"));
        opt.classList.add("on");
        onPick(opt.dataset.val);
      };
    });
  }

  function setSwitch(row, on, onToggle) {
    if (!row) return;
    const sw = row.querySelector(".switch");
    sw.classList.toggle("on", !!on);
    row.onclick = () => {
      const next = !sw.classList.contains("on");
      sw.classList.toggle("on", next);
      onToggle(next);
    };
  }

  function closeAppSettings() {
    const m = $("settings-modal");
    if (m) m.hidden = true;
  }

  async function openAppSettings() {
    const m = $("settings-modal");
    if (!m) return;
    const s = await api().get_app_settings();
    const ver = $("set-version");
    if (ver) ver.textContent = "v" + s.version;

    setSeg($("opt-poll"), s.poll_interval,
      (val) => api().set_app_setting("poll_interval", parseFloat(val)),
      (a, b) => parseFloat(a) === parseFloat(b));

    setSeg($("opt-lex-lang"), s.lex_lang, (val) => {
      lexLang = val;
      syncLangSeg();
      if (lexCur) showStrong(lexCur.code, lexCur.verse, lexCur.book, lexCur.chapter);
      api().set_app_setting("lex_lang", val);
    });

    setSwitch($("opt-search-nav"), s.search_click_navigates, (on) => {
      state.searchClickNav = on;
      api().set_app_setting("search_click_navigates", on);
    });
    setSwitch($("opt-auto-update"), s.auto_update_check,
      (on) => api().set_app_setting("auto_update_check", on));

    wireSettingsActions();
    m.hidden = false;
  }

  function wireSettingsActions() {
    const df = $("act-data-folder");
    if (df) df.onclick = async () => {
      const r = await api().open_data_folder();
      if (!r || !r.ok) toast("폴더를 열 수 없습니다");
    };
    const gh = $("act-github");
    if (gh) gh.onclick = () => api().open_github();
    const rs = $("act-reset");
    if (rs) {
      rs.textContent = "설정 초기화";
      let armed = false;
      rs.onclick = async () => {
        if (!armed) { armed = true; rs.textContent = "한 번 더 누르면 초기화"; return; }
        await api().reset_settings();
        location.reload();   // re-read the fresh defaults
      };
    }
  }

  function wireAppSettings() {
    const gear = $("nav-app-settings");
    if (gear) gear.addEventListener("click", openAppSettings);
    const close = $("settings-close");
    if (close) close.addEventListener("click", closeAppSettings);
    const overlay = $("settings-modal");
    if (overlay) overlay.addEventListener("click", (e) => {
      if (e.target === overlay) closeAppSettings();
    });
    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeAppSettings();
    });
  }

  // ---- Global version chip management (ver-chips in the controls bar) ----
  // First chip = primary (drives book/chapter navigation + search default).
  // Chips are drag-reorderable with a LIVE gap: while dragging, every chip
  // slides in real time to preview where things will land.

  function renderVerChips() {
    const box = $("ver-chips");
    if (!box) return;
    box.innerHTML = state.viewer.map((name, i) => {
      const isPrimary = i === 0;
      return `<span class="pill sel${isPrimary ? " primary" : ""}" data-ver="${esc(name)}" draggable="true">` +
        `${esc(displayName(name))}<span class="x">✕</span></span>`;
    }).join("");
    box.querySelectorAll(".pill.sel .x").forEach((x) => {
      x.addEventListener("click", async (e) => {
        e.stopPropagation();
        const name = e.currentTarget.closest("[data-ver]").dataset.ver;
        if (state.viewer.length <= 1) { toast("최소 한 개의 역본은 유지해야 합니다"); return; }
        await updateViewerVersions(state.viewer.filter((v) => v !== name));
      });
    });
  }

  // FLIP settle: capture chip x-positions before a re-render, animate to rest after.
  function chipRects() {
    const m = new Map();
    const box = $("ver-chips");
    if (box) box.querySelectorAll(".pill.sel").forEach((el) => {
      m.set(el.dataset.ver, el.getBoundingClientRect().left);
    });
    return m;
  }
  function flipChips(prev) {
    const box = $("ver-chips");
    if (!box) return;
    const els = box.querySelectorAll(".pill.sel");
    els.forEach((el) => {
      const before = prev.get(el.dataset.ver);
      if (before == null) return;
      const dx = before - el.getBoundingClientRect().left;
      if (!dx) return;
      el.style.transition = "none";
      el.style.transform = `translateX(${dx}px)`;
    });
    requestAnimationFrame(() => {
      els.forEach((el) => {
        if (!el.style.transform) return;
        el.style.transition = "transform .22s cubic-bezier(.2,.8,.25,1)";
        el.style.transform = "";
      });
    });
  }

  async function updateViewerVersions(newViewer) {
    const prev = chipRects();
    state.viewer = newViewer;
    renderVerChips();
    flipChips(prev);
    CardManager.reloadAllBible();
    state.searchVersion = CardManager.primaryVersion();
    updateSearchVerLabel();
    if (hasBridge()) api().set_viewer_versions(newViewer);
  }

  // ---- chip drag-reorder with live gap ----

  const CHIP_GAP = 6; // matches .ver-chips CSS gap
  let chipDrag = null;

  function wireChipDrag() {
    const box = $("ver-chips");
    if (!box) return;

    box.addEventListener("dragstart", (e) => {
      const chip = e.target.closest(".pill.sel");
      if (!chip) return;
      const all = [...box.querySelectorAll(".pill.sel")];
      chipDrag = {
        name: chip.dataset.ver,
        el: chip,
        // untransformed snapshot — insertion math always uses these
        chips: all.map((el) => {
          const r = el.getBoundingClientRect();
          return { el, name: el.dataset.ver, left: r.left, width: r.width };
        }),
        lastIdx: null,
      };
      chip.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      try { e.dataTransfer.setData("text/plain", chip.dataset.ver); } catch (_) {}
    });

    box.addEventListener("dragover", (e) => {
      if (!chipDrag) return;
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      // insertion index among the *other* chips from the pointer X
      const others = chipDrag.chips.filter((c) => c.el !== chipDrag.el);
      let idx = others.length;
      for (let i = 0; i < others.length; i++) {
        if (e.clientX < others[i].left + others[i].width / 2) { idx = i; break; }
      }
      if (idx === chipDrag.lastIdx) return;
      chipDrag.lastIdx = idx;
      layoutChipGap(idx);
    });

    box.addEventListener("drop", (e) => {
      if (!chipDrag) return;
      e.preventDefault();
      commitChipDrag();
    });
    box.addEventListener("dragend", () => {
      if (chipDrag) commitChipDrag(); // dropped outside → settle (no change committed below)
    });
  }

  // Live preview: every chip (including the translucent drag source) slides to
  // where it WOULD sit if dropped at `insertIdx`.
  function layoutChipGap(insertIdx) {
    const dragChip = chipDrag.chips.find((c) => c.el === chipDrag.el);
    const others = chipDrag.chips.filter((c) => c.el !== chipDrag.el);
    const newOrder = [...others.slice(0, insertIdx), dragChip, ...others.slice(insertIdx)];
    let x = Math.min(...chipDrag.chips.map((c) => c.left));
    newOrder.forEach((c) => {
      const shift = x - c.left;
      c.el.style.transform = shift ? `translateX(${shift}px)` : "";
      x += c.width + CHIP_GAP;
    });
  }

  async function commitChipDrag() {
    const drag = chipDrag;
    chipDrag = null;
    drag.el.classList.remove("dragging");
    const others = drag.chips.filter((c) => c.el !== drag.el).map((c) => c.name);
    const order = drag.lastIdx == null
      ? state.viewer.slice()
      : [...others.slice(0, drag.lastIdx), drag.name, ...others.slice(drag.lastIdx)];
    // FLIP from the on-screen (transformed) positions to the re-rendered order —
    // chips land exactly where the live preview showed them, no jump.
    const prev = new Map();
    drag.chips.forEach((c) => prev.set(c.name, c.el.getBoundingClientRect().left));
    const changed = order.join(" ") !== state.viewer.join(" ");
    state.viewer = order;
    renderVerChips();
    flipChips(prev);
    if (changed) {
      if (hasBridge()) api().set_viewer_order(order);
      CardManager.reloadAllBible();
      state.searchVersion = CardManager.primaryVersion();
      updateSearchVerLabel();
    }
  }

  // ---- Clipboard monitoring ----

  function setStatus(active) {
    const badge = $("status-badge");
    const btn = $("monitor-btn");
    if (badge) {
      badge.textContent = active ? "모니터링 중" : "대기 중";
      badge.classList.toggle("on", active);
    }
    if (btn) btn.textContent = active ? "모니터링 중지" : "모니터링 시작";
  }

  const refLog = [];  // caught references, newest last (index === log row order)

  function vlist(verses) {
    if (!verses || !verses.length) return "전체";
    return verses.join(", ");
  }

  function renderLog() {
    const list = $("log-list");
    if (!list) return;
    if (!refLog.length) {
      list.innerHTML = `<div class="log-empty">모니터링 중 인식한 구절이 여기에 쌓입니다.</div>`;
      return;
    }
    list.innerHTML = refLog
      .map((e, i) => {
        if (e.kind === "keyword") {
          return `<div class="log-row keyword"><div class="log-ref"># ${esc(e.keyword)}</div><div class="log-meta">키워드 검색</div></div>`;
        }
        return `<div class="log-row" data-log="${i}"><div class="log-ref">${esc(e.short_name)} ${e.chapter}:${esc(vlist(e.verses))}</div><div class="log-meta"><span class="log-count">${e.n_parts}개 역본</span></div></div>`;
      })
      .reverse()
      .join("");
    list.querySelectorAll("[data-log]").forEach((row) => {
      row.addEventListener("click", async () => {
        const e = refLog[Number(row.dataset.log)];
        if (!e) return;
        CardManager.goToRef(e.book_num, e.chapter, e.verses);
        const r = await api().copy_reference(e.book_num, e.chapter, e.verses || []);
        if (r && r.ok) toast(`${e.short_name} ${e.chapter}:${vlist(e.verses)} 다시 복사됨`);
      });
    });
  }

  function wireMonitor() {
    const btn = $("monitor-btn");
    if (!btn) return;
    let busy = false;
    btn.addEventListener("click", async () => {
      if (busy) return;
      busy = true;
      try {
        if (!state.monitoring) {
          const res = await api().start_monitoring();
          if (res && res.ok) {
            state.monitoring = true;
            setStatus(true);
          } else {
            toast("클립보드 모니터링을 시작할 수 없습니다");
          }
        } else {
          await api().stop_monitoring();
          state.monitoring = false;
          setStatus(false);
        }
      } finally {
        busy = false;
      }
    });

    // Python → JS event channel (clipboard monitor runs on a worker thread).
    window.bibleclip = {
      onReference(r) {
        refLog.push({ kind: "reference", ...r });
        renderLog();
        flagUnread();
        toast(`${r.short_name} ${r.chapter}:${vlist(r.verses)} 변환·복사됨`);
        showView("viewer"); // a caught reference always returns to the bible view
        CardManager.goToRef(r.book_num, r.chapter, r.verses);
      },
      onKeyword(keyword) {
        refLog.push({ kind: "keyword", keyword });
        renderLog();
        flagUnread();
        toast(`키워드 "${keyword}" 검색`);
        showView("search");
        runSearch(keyword);
      },
      onUpdateProgress,
      onUpdateReady,
      onUpdateError,
    };
  }

  // ---- Output settings tab (출력 설정) ----

  const FORMAT_ROWS = [
    { key: "book_name", label: "책 이름",
      opts: [["long_ko", "한글 정식"], ["short_ko", "한글 약칭"], ["long_en", "영문 정식"], ["short_en", "영문 약칭"]] },
    { key: "chapter_verse_format", label: "장절 표기",
      opts: [["colon", "1:1"], ["korean", "1장 1절"]] },
    { key: "bracket_style", label: "괄호",
      opts: [["none", "없음"], ["[]", "[ ]"], ["()", "( )"]] },
    { key: "ref_position", label: "표기 위치",
      opts: [["before", "본문 앞"], ["after", "본문 뒤"]] },
    { key: "range_symbol", label: "범위 기호",
      opts: [["-", "-"], ["~", "~"]] },
    { key: "ref_body_separator", label: "구분 기호",
      opts: [[" - ", "하이픈"], [": ", "콜론"], [" ", "띄어쓰기"]] },
    { key: "output_mode", label: "출력 방식",
      opts: [["inline", "한 줄로"], ["newline", "줄마다"]] },
  ];
  const TOGGLE_ROWS = [
    { key: "newline_show_cv", label: "줄마다 장:절 표시" },
    { key: "show_version_header", label: "버전 헤더 출력" },
    { key: "hide_reference", label: "장절 표기 숨기기 (본문만)" },
  ];

  let settingsLoaded = false;
  let setState = null; // {format:{...}, output_order:[...], versions:[...]}

  function dispOf(name) {
    const v = (setState.versions || []).find((x) => x.name === name);
    return v ? v.display : "";
  }

  async function refreshPreview() {
    const pre = $("set-preview");
    if (pre) pre.textContent = await api().get_preview();
  }

  function renderFormat() {
    const host = $("set-format");
    host.innerHTML = "";
    FORMAT_ROWS.forEach((row) => {
      const r = document.createElement("div");
      r.className = "set-row";
      const lab = document.createElement("span");
      lab.className = "set-label";
      lab.textContent = row.label;
      const seg = document.createElement("div");
      seg.className = "seg";
      row.opts.forEach(([val, label]) => {
        const opt = document.createElement("div");
        opt.className = "opt" + (setState.format[row.key] === val ? " on" : "");
        opt.textContent = label;
        opt.addEventListener("click", async () => {
          seg.querySelectorAll(".opt").forEach((o) => o.classList.remove("on"));
          opt.classList.add("on");
          setState.format[row.key] = val;
          await api().set_setting(row.key, val);
          refreshPreview();
        });
        seg.appendChild(opt);
      });
      r.appendChild(lab);
      r.appendChild(seg);
      host.appendChild(r);
    });
    TOGGLE_ROWS.forEach((row) => {
      const t = document.createElement("div");
      t.className = "set-toggle";
      const lab = document.createElement("span");
      lab.className = "set-label";
      lab.textContent = row.label;
      const sw = document.createElement("span");
      sw.className = "switch" + (setState.format[row.key] ? " on" : "");
      sw.innerHTML = `<span class="knob"></span>`;
      t.appendChild(lab);
      t.appendChild(sw);
      t.addEventListener("click", async () => {
        const next = !setState.format[row.key];
        setState.format[row.key] = next;
        sw.classList.toggle("on", next);
        await api().set_setting(row.key, next);
        refreshPreview();
      });
      host.appendChild(t);
    });
  }

  function orderBtn(txt, disabled, fn) {
    const b = document.createElement("button");
    b.className = "order-btn";
    b.textContent = txt;
    b.title = txt;
    if (disabled) b.disabled = true;
    else b.addEventListener("click", fn);
    return b;
  }

  function rowTops() {
    const m = new Map();
    $("set-order").querySelectorAll(".order-row").forEach((el) => {
      m.set(el.dataset.ver, el.getBoundingClientRect().top);
    });
    return m;
  }

  function flipReorder(prev) {
    const rows = $("set-order").querySelectorAll(".order-row");
    rows.forEach((el) => {
      const before = prev.get(el.dataset.ver);
      if (before == null) return;
      const dy = before - el.getBoundingClientRect().top;
      if (!dy) return;
      el.style.transition = "none";
      el.style.transform = `translateY(${dy}px)`;
    });
    requestAnimationFrame(() => {
      rows.forEach((el) => {
        if (!el.style.transform) return;
        el.style.transition = "transform .22s cubic-bezier(.2,.8,.25,1)";
        el.style.transform = "";
      });
    });
  }

  function commitOrder(next) {
    const prev = rowTops();
    setState.output_order = next.slice();
    renderOrder();
    flipReorder(prev);
    refreshPreview();
    api().set_output_order(next).then((cleaned) => {
      if (cleaned && cleaned.join(" ") !== next.join(" ")) {
        setState.output_order = cleaned;
        renderOrder();
      }
    });
  }

  function renderOrder() {
    const host = $("set-order");
    host.innerHTML = "";
    const order = setState.output_order;
    if (!order.length) {
      const e = document.createElement("div");
      e.className = "order-empty";
      e.textContent = "복사 시 사용할 역본이 없습니다. 아래에서 추가하세요.";
      host.appendChild(e);
    } else {
      order.forEach((name, i) => {
        const row = document.createElement("div");
        row.className = "order-row";
        row.dataset.ver = name;
        row.innerHTML =
          `<span class="order-idx">${i + 1}</span>` +
          `<span class="order-name">${esc(name)}<span class="order-disp">${esc(dispOf(name))}</span></span>`;
        row.appendChild(orderBtn("↑", i === 0, () => moveOrder(i, -1)));
        row.appendChild(orderBtn("↓", i === order.length - 1, () => moveOrder(i, 1)));
        row.appendChild(orderBtn("✕", false, () => removeOrder(i)));
        host.appendChild(row);
      });
    }
    const avail = (setState.versions || []).filter((v) => !order.includes(v.name));
    if (avail.length) {
      const add = document.createElement("button");
      add.className = "set-add";
      add.textContent = "＋ 역본 추가";
      add.addEventListener("click", () => {
        openMenu(
          add,
          avail.map((v) => ({ label: v.display, value: v.name, on: false })),
          (name) => commitOrder([...setState.output_order, name])
        );
      });
      host.appendChild(add);
    }
  }

  function moveOrder(i, d) {
    const o = setState.output_order.slice();
    const j = i + d;
    if (j < 0 || j >= o.length) return;
    [o[i], o[j]] = [o[j], o[i]];
    commitOrder(o);
  }
  function removeOrder(i) {
    const o = setState.output_order.slice();
    o.splice(i, 1);
    commitOrder(o);
  }

  async function loadSettings() {
    setState = await api().get_settings();
    renderFormat();
    renderOrder();
    refreshPreview();
  }

  // ---- Keyword search ----

  let searchHits = [];

  // Unified search bar (통합 검색바, Phase 2): one input handles three intents.
  //   1) Strong's code (H7225 / G26) → reverse cross-query over 개역한글S tags
  //   2) a bible reference (창 1:1, 창세기 1장 1절) → jump straight to the viewer
  //   3) anything else → keyword search (the original behavior)
  const STRONG_RE = /^[HGhg]\s*\d+$/;

  async function runSearch(kw) {
    const input = $("search-input");
    if (typeof kw === "string") input.value = kw;
    const q = input.value.trim();
    if (!q) return;
    clearSuggest();

    // 1) Strong's code → original-language reverse search
    if (STRONG_RE.test(q)) {
      const code = q.replace(/\s+/g, "").toUpperCase();
      $("search-meta").textContent = "";
      $("search-results").innerHTML = `<div class="panel-loading">[${esc(code)}] 원어 역검색 중…</div>`;
      renderStrongSearch(await api().search_strong(code));
      return;
    }

    // 2) Bible reference → jump to the viewer (only when it parses)
    const ref = await api().resolve_reference(q);
    if (ref) {
      const vs = ref.verses && ref.verses.length ? ref.verses : null;
      showView("viewer");
      CardManager.goToRef(ref.book_num, ref.chapter, vs);
      toast(`${ref.short} ${ref.chapter}${vs ? ":" + vs[0] : "장"}으로 이동`);
      return;
    }

    // 3) Keyword search (default)
    $("search-meta").textContent = "";
    $("search-results").innerHTML = `<div class="panel-loading">검색 중…</div>`;
    renderSearch(await api().search(q, state.searchVersion || undefined));
  }

  // Click handler shared by keyword + strong-code results. Each hit carries
  // {book, chapter, verse, short}.
  function wireSearchHitClicks() {
    $("search-results").querySelectorAll(".sr").forEach((el) => {
      el.addEventListener("click", async () => {
        const h = searchHits[Number(el.dataset.i)];
        if (!h) return;
        const r = await api().copy_reference(h.book, h.chapter, [h.verse]);
        if (r && r.ok) {
          toast(`${h.short} ${h.chapter}:${h.verse} 복사됨`);
          el.classList.add("copied");
          setTimeout(() => el.classList.remove("copied"), 700);
        }
        if (state.searchClickNav) {
          showView("viewer");
          CardManager.goToRef(h.book, h.chapter, [h.verse]);
        }
      });
    });
  }

  function renderSearch(res) {
    const host = $("search-results");
    searchHits = (res.hits || []).map((h) => ({
      book: h.book, chapter: h.chapter, verse: h.verse, short: h.short,
    }));
    if (!searchHits.length) {
      $("search-meta").textContent = `"${res.keyword}" 검색 결과 없음`;
      host.innerHTML = `<div class="panel-loading">검색 결과가 없습니다.</div>`;
      return;
    }
    $("search-meta").textContent =
      `"${res.keyword}" 결과 ${searchHits.length}건 · ${res.display} — 구절 클릭 시 ` +
      (state.searchClickNav ? "복사 + 본문 이동" : "복사");
    host.innerHTML = (res.hits || [])
      .map(
        (h, i) =>
          `<div class="sr" data-i="${i}"><span class="sr-ref">${esc(h.short)} ${h.chapter}:${h.verse}</span><span class="sr-text">${esc(h.text)}</span></div>`
      )
      .join("");
    wireSearchHitClicks();
  }

  // Reverse Strong's search results (구절 목록 — 개역한글S 기준).
  function renderStrongSearch(res) {
    const host = $("search-results");
    const hits = (res && res.hits) || [];
    searchHits = hits.map((h) => ({
      book: h.book_num, chapter: h.chapter, verse: h.verse,
      short: (h.ref || "").split(" ")[0],
    }));
    if (!hits.length) {
      $("search-meta").textContent = `[${res ? res.code : ""}] 원어 역검색 결과 없음`;
      host.innerHTML = `<div class="panel-loading">이 스트롱 코드를 포함한 구절이 없습니다 (개역한글S 기준).</div>`;
      return;
    }
    $("search-meta").textContent =
      `원어 역검색 [${res.code}] · ${res.count}건 (개역한글S) — 구절 클릭 시 복사` +
      (state.searchClickNav ? " + 이동" : "");
    host.innerHTML = hits
      .map(
        (h, i) =>
          `<div class="sr" data-i="${i}"><span class="sr-ref">${esc(h.ref)}</span><span class="sr-text">${esc(h.text)}</span></div>`
      )
      .join("");
    wireSearchHitClicks();
  }

  // ---- search-bar autocomplete (book names + intent hints) ----
  function clearSuggest() { const h = $("search-suggest"); if (h) h.innerHTML = ""; }

  function renderSuggest(q) {
    const host = $("search-suggest");
    if (!host) return;
    const s = (q || "").trim();
    if (!s) { host.innerHTML = ""; return; }
    if (STRONG_RE.test(s)) {
      host.innerHTML = `<span class="sug-hint">↵ 원어 역검색 <b>${esc(s.replace(/\s+/g, "").toUpperCase())}</b></span>`;
      return;
    }
    // leading book token, only while the user hasn't started a chapter yet
    const m = s.match(/^([가-힣A-Za-z]{1,6})$/);
    if (!m) { host.innerHTML = ""; return; }
    const tok = m[1];
    const matches = (state.primaryBooks || [])
      .filter((b) => (b.short && b.short.startsWith(tok)) || (b.long && b.long.startsWith(tok)))
      .slice(0, 8);
    if (!matches.length) { host.innerHTML = ""; return; }
    host.innerHTML = matches
      .map((b) => `<span class="sug" data-b="${esc(b.long)}">${esc(b.long)}</span>`).join("");
    host.querySelectorAll(".sug").forEach((el) => {
      el.addEventListener("mousedown", (e) => {   // mousedown beats input blur
        e.preventDefault();
        const inp = $("search-input");
        inp.value = el.dataset.b + " ";
        inp.focus();
        clearSuggest();
      });
    });
  }

  function updateSearchVerLabel() {
    const sv = $("search-ver");
    if (sv) sv.textContent = state.searchVersion || CardManager.primaryVersion() || "—";
  }

  function wireSearch() {
    const go = $("search-go"), input = $("search-input");
    if (go) go.addEventListener("click", () => runSearch());
    if (input) {
      input.addEventListener("keydown", (e) => {
        if (e.key === "Enter") runSearch();
        else if (e.key === "Escape") clearSuggest();
      });
      input.addEventListener("input", () => renderSuggest(input.value));
      input.addEventListener("blur", () => setTimeout(clearSuggest, 150));
    }
    const sv = $("search-ver");
    if (sv) {
      sv.addEventListener("click", () => {
        openMenu(
          sv,
          state.versions.map((v) => ({
            label: v.display, value: v.name, on: v.name === state.searchVersion,
          })),
          (name) => {
            state.searchVersion = name;
            updateSearchVerLabel();
            if ($("search-input").value.trim()) runSearch();
          }
        );
      });
    }
    updateSearchVerLabel();
  }

  // ---- View switching (viewer / settings / search) ----

  async function showView(name) {
    $("viewer-view").hidden = name !== "viewer";
    $("settings-view").hidden = name !== "settings";
    $("search-view").hidden = name !== "search";
    $("viewer-controls").hidden = name !== "viewer";
    [["nav-viewer", "viewer"], ["nav-settings", "settings"], ["nav-search", "search"]]
      .forEach(([id, v]) => { const el = $(id); if (el) el.classList.toggle("on", name === v); });

    if (name === "settings") {
      if (!settingsLoaded) { settingsLoaded = true; await loadSettings(); }
      else refreshPreview();
    } else if (name === "search") {
      const input = $("search-input");
      if (input) input.focus();
    }
  }

  function wireTabs() {
    if ($("nav-viewer")) $("nav-viewer").addEventListener("click", () => showView("viewer"));
    if ($("nav-settings")) $("nav-settings").addEventListener("click", () => showView("settings"));
    if ($("nav-search")) $("nav-search").addEventListener("click", () => showView("search"));
    wireSearch();
  }

  // ---- Global workspace controls (card add/type, lang, font) ----

  function wireGlobalControls() {
    // ＋ 역본 추가·관리 button
    const verAdd = $("ver-add");
    if (verAdd) {
      verAdd.addEventListener("click", () => {
        const avail = state.versions.filter((v) => !state.viewer.includes(v.name));
        if (!avail.length) { toast("모든 역본이 이미 선택되어 있습니다"); return; }
        openMenu(
          verAdd,
          avail.map((v) => ({ label: v.display, value: v.name })),
          async (name) => { await updateViewerVersions([...state.viewer, name]); }
        );
      });
    }

    // Version chips: drag-reorder with live gap.
    wireChipDrag();

    // ＋ 본문 / ＋ 원어 / ＋ 사전 — new cards appear at the workspace center, on top.
    [["add-bible", "bible"], ["add-inter", "interlinear"], ["add-lex", "lexicon"]].forEach(([id, type]) => {
      const btn = $(id);
      if (btn) btn.addEventListener("click", () => CardManager.addCard(type));
    });

    // Dictionary language toggle (한글/영어) — also re-renders open lexicon cards.
    const langSeg = document.querySelector('.seg[data-seg="lang"]');
    if (langSeg) {
      langSeg.querySelectorAll(".opt").forEach((opt, i) => {
        opt.addEventListener("click", () => {
          lexLang = i === 0 ? "ko" : "en";
          if (lexCur) showStrong(lexCur.code, lexCur.verse, lexCur.book, lexCur.chapter);
        });
      });
    }

    // Font size A− / A+ (persisted as viewer_font_size).
    const changeFont = (d) => {
      const n = Math.max(8, Math.min(30, state.fontSize + d));
      if (n === state.fontSize) return;
      state.fontSize = n;
      applyFontScale();
      api().set_font_size(n);
    };
    if ($("font-dec")) $("font-dec").addEventListener("click", () => changeFont(-1));
    if ($("font-inc")) $("font-inc").addEventListener("click", () => changeFont(1));

    // DB rescan (settings tab). Refreshes available versions everywhere.
    if ($("db-refresh")) $("db-refresh").addEventListener("click", refreshDbs);

    // Keyboard: ←/→ steps the ACTIVE bible card (the focused/neon-stroked one;
    // falls back to the primary card) when the viewer is active.
    document.addEventListener("keydown", (e) => {
      if (e.target.closest("input, textarea")) return;
      if ($("viewer-view").hidden) return;
      if (!state.isPremium) return;  // free tier: chapter shortcut locked (Phase 1)
      if (!CardManager.primaryBible()) return;
      if (e.key === "ArrowLeft") { e.preventDefault(); CardManager.chapStepActive(-1); }
      else if (e.key === "ArrowRight") { e.preventDefault(); CardManager.chapStepActive(1); }
    });
  }

  async function refreshDbs() {
    const res = await api().refresh_databases();
    state.versions = res.versions;
    state.versionsNames = res.versions.map((v) => v.name);
    if (setState) { setState.versions = res.versions; renderOrder(); }
    toast(res.added && res.added.length ? `${res.added.length}개 역본 추가됨` : "새 역본 없음");
  }

  if (hasBridge()) {
    boot();
  } else {
    window.addEventListener("pywebviewready", boot);
  }
})();
