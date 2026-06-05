// BibleClip web frontend — search-notes (묵상노트·툴팁·업데이트/패치 모달·설정 UI·
// 역본칩·모니터·통합검색·뷰 전환). Shares global scope; runs boot() last.

"use strict";

  // ---- 묵상 노트 + verse context menu (Phase 3) ----
  const noteCache = {};   // cardId -> { "<verse>": text } (string keys from JSON)
  let verseMenuEl = null;

  function hideVerseMenu() { if (verseMenuEl) { verseMenuEl.remove(); verseMenuEl = null; } }

  function refLabel(card, verse) {
    const b = (state.primaryBooks || []).find((x) => x.num === card.book);
    return `${b ? b.long : card.book} ${card.chapter}:${verse}`;
  }

  function showVerseMenu(card, verse, x, y) {
    hideVerseMenu();
    const has = !!(noteCache[card.id] && noteCache[card.id][verse]);
    const m = document.createElement("div");
    m.className = "ctx-menu";
    m.innerHTML =
      `<div class="ctx-item" data-a="copy">${I18N.t("ctx.copyVerse")}</div>` +
      `<div class="ctx-item" data-a="note">${has ? I18N.t("ctx.noteEdit") : I18N.t("ctx.noteNew")}</div>` +
      `<div class="ctx-item" data-a="cart">${I18N.t("cart.add")}</div>` +
      `<div class="ctx-item" data-a="orig">${I18N.t("ctx.lookupOriginal")}</div>`;
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(x, window.innerWidth - r.width - 8) + "px";
    m.style.top = Math.min(y, window.innerHeight - r.height - 8) + "px";
    m.addEventListener("mousedown", (e) => {
      const it = e.target.closest(".ctx-item");
      if (!it) return;
      e.preventDefault();
      const a = it.dataset.a;
      hideVerseMenu();
      if (a === "copy") copyVersesFromCard(card, [verse]);
      else if (a === "note") openNoteEditor(card, verse);
      else if (a === "cart") addVerseToCart(card, verse);
      else if (a === "orig") openOriginalFor(card, verse);
    });
    verseMenuEl = m;
  }
  document.addEventListener("mousedown", (e) => {
    if (verseMenuEl && !e.target.closest(".ctx-menu")) hideVerseMenu();
  }, true);
  document.addEventListener("scroll", hideVerseMenu, true);
  window.addEventListener("resize", hideVerseMenu);

  // Open (or focus) a linked 원어 card for the verse's chapter.
  function openOriginalFor(card, verse) {
    CardManager.ensureInterlinearFor(card.id);
  }

  // 우클릭 → 설교 장바구니에 담기. 책이름은 표시 중 viewer 역본 기준(카드 복사와 동일).
  function addVerseToCart(card, verse) {
    const ver = state.viewer[0] || state.primary;
    addToCart({ book_num: card.book, chapter: card.chapter, verses: [verse],
      short_name: bookShortFor(ver, card.book) });
  }

  async function openNoteEditor(card, verse) {
    hideVerseMenu();
    let existing = null;
    try { existing = await api().get_note(card.book, card.chapter, verse); } catch (e) {}
    const back = document.createElement("div");
    back.className = "note-modal-back";
    back.innerHTML =
      `<div class="note-modal" role="dialog" aria-modal="true">` +
        `<div class="note-modal-h"><span>📄 ${I18N.t("note.title")}</span>` +
          `<span class="note-modal-ref">${esc(refLabel(card, verse))}</span></div>` +
        `<textarea class="note-ta" placeholder="${esc(I18N.t("note.placeholder"))}"></textarea>` +
        `<div class="note-modal-foot">` +
          `<button class="btn note-del" ${existing ? "" : "hidden"}>${I18N.t("common.delete")}</button>` +
          `<span class="note-modal-spacer"></span>` +
          `<button class="btn note-cancel">${I18N.t("common.cancel")}</button>` +
          `<button class="btn primary note-save">${I18N.t("common.save")}</button>` +
        `</div>` +
      `</div>`;
    document.body.appendChild(back);
    const ta = back.querySelector(".note-ta");
    ta.value = (existing && existing.text) || "";
    setTimeout(() => ta.focus(), 0);

    const close = () => back.remove();
    const refresh = async () => {
      // re-decorate the card so the badge appears/disappears immediately
      await CardManager.decorateNotesFor(card);
    };
    back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
    back.querySelector(".note-cancel").addEventListener("click", close);
    back.querySelector(".note-save").addEventListener("click", async () => {
      await api().set_note(card.book, card.chapter, verse, ta.value);
      await refresh();
      toast(I18N.t("note.saved"));
      close();
    });
    const del = back.querySelector(".note-del");
    if (del) del.addEventListener("click", async () => {
      await api().delete_note(card.book, card.chapter, verse);
      await refresh();
      toast(I18N.t("note.deleted"));
      close();
    });
    back.addEventListener("keydown", (e) => {
      if (e.key === "Escape") close();
      else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) back.querySelector(".note-save").click();
    });
  }

  // Clicking a 📄 badge opens its note editor.
  document.addEventListener("click", (e) => {
    const b = e.target.closest(".note-badge");
    if (!b) return;
    const sec = b.closest('.mcard[data-type="bible"]');
    if (!sec) return;
    const card = CardManager.bibleCards().find((c) => c.id === sec.dataset.id);
    if (card) { e.stopPropagation(); openNoteEditor(card, +b.dataset.v); }
  }, true);

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

  // Translate a bridge error: prefer the stable error_code via t(); fall back to
  // the Korean 'error' the backend still ships, then a keyed default. (Backend
  // 1-B: user-facing messages are returned as error_code, translated here.)
  function bridgeErr(r, fallbackKey) {
    if (r && r.error_code && window.I18N) return I18N.t(r.error_code, r.error || "");
    if (r && r.error) return r.error;
    return window.I18N ? I18N.t(fallbackKey) : "";
  }

  async function checkUpdate(silent) {
    if (!silent) toast(I18N.t("update.checking"));
    let r = null;
    try { r = await api().check_update(); } catch (e) { r = null; }
    if (!r || !r.ok) { if (!silent) toast(I18N.t("update.checkFailed")); return; }
    if (r.has_update && r.mandatory) {
      // Soft forced update (Phase 4): non-dismissible modal, but app still runs.
      updateInfo = r;
      showForcedUpdate(r);
    } else if (r.has_update && !(silent && r.skipped)) {
      updateInfo = r;
      $("ub-text").textContent = I18N.t("update.available", { latest: r.latest, current: r.current });
      $("update-banner").hidden = false;
    } else if (!silent) {
      toast(I18N.t("update.upToDate", { current: r.current }));
    }
  }

  // Non-dismissible "update required" modal (Phase 4). Driven by the kill-switch
  // manifest's recommend_version (soft threshold) — distinct from the hard
  // min_version block at startup.
  function showForcedUpdate(r) {
    if (document.querySelector(".forced-back")) return;
    const back = document.createElement("div");
    back.className = "note-modal-back forced-back";
    back.innerHTML =
      `<div class="note-modal forced-modal" role="dialog" aria-modal="true">` +
        `<div class="patch-h forced-h">⚠ ${I18N.t("update.requiredTitle")}</div>` +
        `<p class="forced-text">${I18N.t("update.requiredBody", { current: esc(r.current), latest: esc(r.latest) })}</p>` +
        `<div class="note-modal-foot"><span class="note-modal-spacer"></span>` +
          `<button class="btn forced-page">${I18N.t("ub.releases")}</button>` +
          `<button class="btn primary forced-install">${I18N.t("ub.install")}</button></div>` +
      `</div>`;
    document.body.appendChild(back);
    back.querySelector(".forced-page").addEventListener("click", () => api().open_releases_page());
    back.querySelector(".forced-install").addEventListener("click", async () => {
      const x = await api().install_update();
      if (!x || !x.ok) toast(bridgeErr(x, "toast.installUseReleases"));
    });
    // intentionally non-dismissible: no backdrop / Escape close.
  }

  // First-run-after-update patch notes (Phase 4).
  async function maybePatchModal() {
    let p = null;
    try { p = await api().get_patch_notes(); } catch (e) { p = null; }
    if (!p || !p.show || !(p.notes || []).length) return;
    const back = document.createElement("div");
    back.className = "note-modal-back";
    back.innerHTML =
      `<div class="note-modal patch-modal" role="dialog" aria-modal="true">` +
        `<div class="patch-h"><span class="patch-badge">NEW</span> ${I18N.t("update.notesTitle", { version: esc(p.version) })}</div>` +
        `<ul class="patch-list">${p.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` +
        `<label class="patch-dismiss"><input type="checkbox" class="patch-cb"> ${I18N.t("update.dontShowAgain")}</label>` +
        `<div class="note-modal-foot"><span class="note-modal-spacer"></span>` +
          `<button class="btn primary patch-ok">${I18N.t("common.confirm")}</button></div>` +
      `</div>`;
    document.body.appendChild(back);
    const close = () => {
      try { api().dismiss_patch(!!back.querySelector(".patch-cb").checked); } catch (e) {}
      back.remove();
    };
    back.querySelector(".patch-ok").addEventListener("click", close);
    back.addEventListener("mousedown", (e) => { if (e.target === back) close(); });
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
      if (!r || !r.ok) { toast(bridgeErr(r, "toast.installCannotStart")); return; }
      $("ub-text").textContent = I18N.t("update.preparing");
      $("ub-install").disabled = true;
    });
  }

  function onUpdateProgress(pct, kb, total) {
    const t = $("ub-text");
    if (t) t.textContent = total ? `${I18N.t("update.downloading")} ${pct}% (${kb.toLocaleString()} / ${total.toLocaleString()} KB)`
                                 : `${I18N.t("update.downloading")} ${kb.toLocaleString()} KB`;
  }
  function onUpdateReady() {
    const t = $("ub-text");
    if (t) t.textContent = I18N.t("update.applying");
  }
  function onUpdateError(msg) {
    toast(I18N.t("update.failedPrefix") + msg);
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

  // UI 언어가 토글로 바뀌었는지 표시. 백엔드 동기화(디스크 쓰기)는 토글마다 하지 않고
  // 모달을 닫을 때 1회만 — 빠른 연속 토글이 pywebview 브릿지/OneDrive 파일잠금과 겹쳐
  // UI가 멈추던 문제 방지. 화면 전환 자체는 순수 프론트(localStorage+DOM)라 영향 없음.
  let _uiLangDirty = false;

  function closeAppSettings() {
    const m = $("settings-modal");
    if (m) m.hidden = true;
    if (_uiLangDirty && window.I18N) {
      _uiLangDirty = false;
      try { api().set_app_setting("ui_lang", I18N.getLang()); } catch (_) {}
    }
  }

  async function openAppSettings() {
    const m = $("settings-modal");
    if (!m) return;
    const s = await api().get_app_settings();
    const ver = $("set-version");
    if (ver) ver.textContent = "v" + s.version;

    // UI 표시 언어 (i18n) — 재시작 없이 즉시 전환. 화면 전환은 순수 프론트(localStorage+DOM).
    // 백엔드 ui_lang 기록(Python-렌더 표면용)은 토글마다가 아니라 모달 닫을 때 1회만 한다.
    if (window.I18N) {
      setSeg($("opt-ui-lang"), I18N.getLang(), (val) => {
        if (val === I18N.getLang()) return;   // 무변경 클릭 무시(불필요 디스크 쓰기 방지)
        I18N.setLang(val);
        _uiLangDirty = true;
      });
    }
    const fontPill = $("opt-reading-font");
    if (fontPill) fontPill.textContent = state.readingFont || I18N.t("font.default");

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
    setSwitch($("opt-auto-copy"), s.auto_copy_top_result, (on) => {
      state.autoCopyTop = on;
      api().set_app_setting("auto_copy_top_result", on);
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
      if (!r || !r.ok) toast(I18N.t("toast.folderOpenFail"));
    };
    const gh = $("act-github");
    if (gh) gh.onclick = () => api().open_github();
    const rs = $("act-reset");
    if (rs) {
      rs.textContent = I18N.t("modal.actReset");
      let armed = false;
      rs.onclick = async () => {
        if (!armed) { armed = true; rs.textContent = I18N.t("settings.resetArm"); return; }
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
        if (state.viewer.length <= 1) { toast(I18N.t("toast.keepOneVersion")); return; }
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
      badge.textContent = active ? I18N.t("monitor.active") : I18N.t("topbar.statusIdle");
      badge.classList.toggle("on", active);
    }
    if (btn) btn.textContent = active ? I18N.t("monitor.stop") : I18N.t("topbar.monitorStart");
  }

  const refLog = [];  // caught references, newest last (index === log row order)

  function vlist(verses) {
    if (!verses || !verses.length) return I18N.t("ref.whole");
    return verses.join(", ");
  }

  // Append an internally-copied reference to the activity log (좌측 클립보드
  // 드로어). The clipboard monitor's onReference uses this same refLog/renderLog
  // path; in-app 클릭·드래그·검색 결과 복사도 여기로 통합 기록한다.
  function logReference(entry) {
    refLog.push({ kind: "reference", ...entry });
    renderLog();
    flagUnread();
  }

  function renderLog() {
    const list = $("log-list");
    if (!list) return;
    if (!refLog.length) {
      list.innerHTML = `<div class="log-empty">${I18N.t("drawer.logEmpty")}</div>`;
      return;
    }
    list.innerHTML = refLog
      .map((e, i) => {
        if (e.kind === "keyword") {
          return `<div class="log-row keyword"><div class="log-ref"># ${esc(e.keyword)}</div><div class="log-meta">${I18N.t("log.keywordSearch")}</div></div>`;
        }
        return `<div class="log-row" data-log="${i}"><div class="log-ref">${esc(e.short_name)} ${e.chapter}:${esc(vlist(e.verses))}</div><div class="log-meta"><span class="log-count">${I18N.t("log.nVersions", { n: e.n_parts })}</span></div><span class="cart-add-btn" data-cart-add-log="${i}" title="${esc(I18N.t("cart.add"))}">＋</span></div>`;
      })
      .reverse()
      .join("");
    list.querySelectorAll("[data-log]").forEach((row) => {
      row.addEventListener("click", async (ev) => {
        if (ev.target.closest("[data-cart-add-log]")) return;  // ＋ 는 장바구니 담기 전용
        const e = refLog[Number(row.dataset.log)];
        if (!e) return;
        CardManager.goToRef(e.book_num, e.chapter, e.verses);
        const r = await api().copy_reference(e.book_num, e.chapter, e.verses || []);
        if (r && r.ok) toast(I18N.t("toast.recopiedRef", { ref: `${e.short_name} ${e.chapter}:${vlist(e.verses)}` }));
      });
    });
    list.querySelectorAll("[data-cart-add-log]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const e = refLog[Number(btn.dataset.cartAddLog)];
        if (e) addToCart({ book_num: e.book_num, chapter: e.chapter, verses: e.verses, short_name: e.short_name });
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
            toast(I18N.t("toast.monitorStartFail"));
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
        toast(I18N.t("toast.convertedCopied", { ref: `${r.short_name} ${r.chapter}:${vlist(r.verses)}` }));
        showView("viewer"); // a caught reference always returns to the bible view
        CardManager.goToRef(r.book_num, r.chapter, r.verses);
      },
      onKeyword(keyword) {
        refLog.push({ kind: "keyword", keyword });
        renderLog();
        flagUnread();
        toast(I18N.t("toast.keywordSearch", { keyword }));
        showView("search");
        runSearch(keyword);
      },
      onUpdateProgress,
      onUpdateReady,
      onUpdateError,
    };
  }

  // ---- Sermon cart / cue sheet (오늘의 설교 성구, 2순위) ----
  // Items persist in localStorage; clicking one re-copies it (same path as a log
  // row). Added via the hover ＋ on search results / activity-log rows. The cart
  // drawer is mutually exclusive with the activity-log drawer.
  const CART_KEY = "bibleclip_cart";
  let cart = [];
  try { cart = JSON.parse(localStorage.getItem(CART_KEY) || "[]"); if (!Array.isArray(cart)) cart = []; } catch (_) { cart = []; }

  function saveCart() { try { localStorage.setItem(CART_KEY, JSON.stringify(cart)); } catch (_) {} }
  function cartKey(it) { return `${it.book_num}|${it.chapter}|${(it.verses || []).join(",")}`; }

  function addToCart(item) {
    const it = {
      book_num: item.book_num, chapter: item.chapter,
      verses: (item.verses || []).slice(), short_name: item.short_name || "",
    };
    if (!it.book_num) return;
    if (cart.some((c) => cartKey(c) === cartKey(it))) { toast(I18N.t("cart.dup")); return; }
    cart.push(it);
    saveCart();
    renderCart();
    if ($("cart-drawer") && $("cart-drawer").hidden) {
      const dot = $("cart-dot"); if (dot) dot.hidden = false;  // unread badge
    }
    toast(I18N.t("cart.added"));
  }
  function removeFromCart(i) { cart.splice(i, 1); saveCart(); renderCart(); }
  function clearCart() { cart = []; saveCart(); renderCart(); }

  function renderCart() {
    const list = $("cart-list");
    if (!list) return;
    if (!cart.length) {
      list.innerHTML = `<div class="log-empty" data-i18n="cart.empty">${I18N.t("cart.empty")}</div>`;
      return;
    }
    list.innerHTML = cart.map((e, i) =>
      `<div class="log-row cart-item" data-cart="${i}" data-tip="${esc(I18N.t("cart.itemTip"))}">` +
        `<div class="log-ref">${esc(e.short_name)} ${e.chapter}:${esc(vlist(e.verses))}</div>` +
        `<span class="cart-del-btn" data-del="${i}" title="${esc(I18N.t("cart.remove"))}">✕</span>` +
      `</div>`
    ).join("");
    list.querySelectorAll("[data-cart]").forEach((row) => {
      row.addEventListener("click", async (ev) => {
        if (ev.target.closest("[data-del]")) return;
        const e = cart[Number(row.dataset.cart)];
        if (!e) return;
        const r = await api().copy_reference(e.book_num, e.chapter, e.verses || []);
        if (r && r.ok) {
          row.classList.add("copied");
          setTimeout(() => row.classList.remove("copied"), 600);
          toast(I18N.t("toast.recopiedRef", { ref: `${e.short_name} ${e.chapter}:${vlist(e.verses)}` }));
        }
        if (state.searchClickNav) {   // 찾기 옵션처럼: 클릭 시 본문(viewer)으로 이동
          showView("viewer");
          CardManager.goToRef(e.book_num, e.chapter, e.verses);
        }
      });
    });
    list.querySelectorAll("[data-del]").forEach((x) => {
      x.addEventListener("click", (ev) => { ev.stopPropagation(); removeFromCart(Number(x.dataset.del)); });
    });
  }

  function openCart() {
    const cd = $("cart-drawer");
    if (!cd) return;
    if (typeof closeDrawer === "function") closeDrawer();   // 상호배타: 로그 드로어 닫기
    cd.hidden = false;
    $("cart-toggle").classList.add("on");
    const dot = $("cart-dot"); if (dot) dot.hidden = true;
    renderCart();
  }
  function closeCart() {
    const cd = $("cart-drawer");
    if (cd) cd.hidden = true;
    const t = $("cart-toggle"); if (t) t.classList.remove("on");
  }
  function wireCart() {
    const tog = $("cart-toggle");
    if (tog) tog.addEventListener("click", () => $("cart-drawer").hidden ? openCart() : closeCart());
    const cl = $("cart-close"); if (cl) cl.addEventListener("click", closeCart);
    const clr = $("cart-clear"); if (clr) clr.addEventListener("click", clearCart);
    renderCart();
  }

  // ---- F2 quick search (presentation jump, 3순위) ----
  // Type a reference (창 1:1 / Gen 1:1 / 1Ths 1:1) or keyword → jump the active /
  // fullscreen bible card to it. Appended INSIDE the fullscreen card when
  // presenting (else covers the window), so it shows over a fullscreen slide.
  function closeQuickSearch() {
    document.querySelectorAll(".qs-overlay").forEach((o) => o.remove());
  }
  function openQuickSearch() {
    closeQuickSearch();
    const host = document.fullscreenElement || document.body;
    const box = document.createElement("div");
    box.className = "qs-overlay";
    box.innerHTML = `<input type="text" class="qs-input" autocomplete="off" placeholder="${esc(I18N.t("present.qsPlaceholder"))}">`;
    host.appendChild(box);
    const input = box.querySelector(".qs-input");
    setTimeout(() => input.focus(), 0);
    box.addEventListener("mousedown", (e) => { if (e.target === box) closeQuickSearch(); });
    input.addEventListener("keydown", async (e) => {
      e.stopPropagation();
      if (e.key === "Escape") { closeQuickSearch(); }
      else if (e.key === "Enter") {
        const q = input.value.trim();
        closeQuickSearch();
        if (q) await quickJump(q);
      }
    });
  }
  async function quickJump(q) {
    // Reference first; fall back to a keyword search and jump to the top hit.
    let ref = null;
    try { ref = await api().resolve_reference(q); } catch (_) {}
    if (ref) {
      const vs = ref.verses && ref.verses.length ? ref.verses : null;
      CardManager.goToRef(ref.book_num, ref.chapter, vs);
      return;
    }
    try {
      const res = await api().search(q, state.searchVersion || undefined, 1, searchMode());
      const h = (res.hits || [])[0];
      if (h) CardManager.goToRef(h.book, h.chapter, [h.verse]);
    } catch (_) {}
  }

  // F11 = present the active card fullscreen; F2 = quick jump.
  document.addEventListener("keydown", (e) => {
    if (e.key === "F11") { e.preventDefault(); CardManager.presentToggle(); }
    else if (e.key === "F2") { e.preventDefault(); openQuickSearch(); }
  });

  // ---- Custom reading fonts (fonts/ 폴더 → 동적 @font-face, 4순위) ----
  // The backend lists/serves user .ttf/.otf placed in the data 'fonts' folder;
  // we inject an @font-face from base64 and drive the scripture via --reading-font.
  let fontsList = [];                 // [{family, file}]
  const injectedFonts = new Set();
  // family 는 파일명에서 오므로, 따옴표/구두점이 CSS 를 깨뜨리지 않게 안전화.
  const cssFontName = (s) => String(s).replace(/["\\;{}<>\r\n]/g, "").trim();
  async function loadFontsList() {
    try { fontsList = await api().list_fonts(); } catch (_) { fontsList = []; }
    if (!Array.isArray(fontsList)) fontsList = [];
    return fontsList;
  }
  async function injectFont(family, file) {
    if (injectedFonts.has(family)) return true;
    let info = null;
    try { info = await api().get_font(file); } catch (_) {}
    if (!info || !info.b64) return false;
    const st = document.createElement("style");
    st.textContent = `@font-face{font-family:"${cssFontName(family)}";font-display:swap;` +
      `src:url(data:${info.mime};base64,${info.b64});}`;
    document.head.appendChild(st);
    injectedFonts.add(family);
    return true;
  }
  function applyReadingFont(family) {
    if (family) root.style.setProperty("--reading-font", `"${cssFontName(family)}", var(--font-ui)`);
    else root.style.removeProperty("--reading-font");
    state.readingFont = family || "";
  }
  async function selectReadingFont(family, file) {
    if (family && file && !(await injectFont(family, file))) { toast(I18N.t("font.loadFail")); return; }
    applyReadingFont(family);
    if (hasBridge()) api().set_app_setting("reading_font", family || "");
  }
  async function bootReadingFont(family) {        // boot: inject+apply saved font (no re-save)
    if (!family) return;
    await loadFontsList();
    const f = fontsList.find((x) => x.family === family);
    if (f && await injectFont(family, f.file)) applyReadingFont(family);
  }
  function wireReadingFontMenu() {
    const pill = $("opt-reading-font");
    if (!pill) return;
    pill.addEventListener("click", async () => {
      await loadFontsList();
      const items = [{ label: I18N.t("font.default"), value: "", on: !state.readingFont }]
        .concat(fontsList.map((f) => ({ label: f.family, value: f.family, on: state.readingFont === f.family })));
      openMenu(pill, items, async (family) => {
        const f = fontsList.find((x) => x.family === family);
        await selectReadingFont(family, f ? f.file : null);
        pill.textContent = family || I18N.t("font.default");
      });
    });
  }

  // ---- Output settings tab (출력 설정) ----

  // label / opt label 은 i18n 키. 렌더 시 I18N.t 로 번역 → 언어 전환 시 재렌더로 갱신.
  // 포맷 샘플(1:1 · [ ] · - 등)은 ko/en 동일 값으로 로케일에 둔다(uniform 렌더).
  const FORMAT_ROWS = [
    { key: "book_name", label: "fmt.bookName",
      opts: [["long_ko", "fmt.bookLong"], ["short_ko", "fmt.bookShort"]] },
    { key: "chapter_verse_format", label: "fmt.cvFormat",
      opts: [["colon", "fmt.cvColon"], ["korean", "fmt.cvKorean"]] },
    { key: "bracket_style", label: "fmt.bracket",
      opts: [["none", "fmt.bracketNone"], ["[]", "fmt.bracketSquare"], ["()", "fmt.bracketParen"]] },
    { key: "ref_position", label: "fmt.position",
      opts: [["before", "fmt.posBefore"], ["after", "fmt.posAfter"]] },
    { key: "range_symbol", label: "fmt.rangeSymbol",
      opts: [["-", "fmt.rangeHyphen"], ["~", "fmt.rangeTilde"]] },
    { key: "ref_body_separator", label: "fmt.separator",
      opts: [[" - ", "fmt.sepHyphen"], [": ", "fmt.sepColon"], [" ", "fmt.sepSpace"]] },
    { key: "output_mode", label: "fmt.outputMode",
      opts: [["inline", "fmt.inline"], ["newline", "fmt.newline"]] },
  ];
  const TOGGLE_ROWS = [
    { key: "newline_show_cv", label: "fmt.newlineShowCv" },
    { key: "show_version_header", label: "fmt.showVersionHeader" },
    { key: "hide_reference", label: "fmt.hideReference" },
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
      lab.textContent = I18N.t(row.label);
      const seg = document.createElement("div");
      seg.className = "seg";
      row.opts.forEach(([val, label]) => {
        const opt = document.createElement("div");
        opt.className = "opt" + (setState.format[row.key] === val ? " on" : "");
        opt.textContent = I18N.t(label);
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
      lab.textContent = I18N.t(row.label);
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
      e.textContent = I18N.t("order.empty");
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
      add.textContent = I18N.t("order.addVersion");
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
      $("search-results").innerHTML = `<div class="panel-loading">${I18N.t("search.strongSearching", { code: esc(code) })}</div>`;
      renderStrongSearch(await api().search_strong(code));
      return;
    }

    // 2) Bible reference → jump to the viewer (only when it parses)
    const ref = await api().resolve_reference(q);
    if (ref) {
      const vs = ref.verses && ref.verses.length ? ref.verses : null;
      showView("viewer");
      CardManager.goToRef(ref.book_num, ref.chapter, vs);
      const jref = `${ref.short} ${ref.chapter}${vs ? ":" + vs[0] : I18N.t("ref.chapterMark")}`;
      toast(I18N.t("toast.jumpedTo", { ref: jref }));
      return;
    }

    // 3) Keyword search (default). v1.0.5: 띄어쓰기 다중 키워드면 AND/OR 모드 적용.
    $("search-meta").textContent = "";
    $("search-results").innerHTML = `<div class="panel-loading">${I18N.t("search.searching")}</div>`;
    renderSearch(await api().search(q, state.searchVersion || undefined, 200, searchMode()));
  }

  // 검색바의 AND/OR 세그먼트 현재 값 ('and'|'or'). 기본 'and'.
  function searchMode() {
    const on = document.querySelector('#search-mode .opt.on');
    return (on && on.dataset.mode === "or") ? "or" : "and";
  }

  // 검색 히트 1건을 클립보드에 복사하고 활동 로그에 기록(클립보드 모니터와 동일 경로
  // → 로그 행 클릭 시 재복사도 자동 지원). {book, chapter, verse, short} 사용.
  async function copyHit(h) {
    const r = await api().copy_reference(h.book, h.chapter, [h.verse]);
    if (r && r.ok) {
      toast(I18N.t("toast.copiedRef", { ref: `${h.short} ${h.chapter}:${h.verse}` }));
      logReference({ book_num: h.book, chapter: h.chapter, verses: [h.verse],
        short_name: h.short, n_parts: r.n_parts || 1, text: r.text });
    }
    return r;
  }

  // Click handler shared by keyword + strong-code results.
  function wireSearchHitClicks() {
    const host = $("search-results");
    host.querySelectorAll(".sr").forEach((el) => {
      el.addEventListener("click", async (ev) => {
        if (ev.target.closest("[data-cart-add]")) return;  // ＋ 는 장바구니 담기 전용
        const h = searchHits[Number(el.dataset.i)];
        if (!h) return;
        const r = await copyHit(h);
        if (r && r.ok) {
          el.classList.add("copied");
          setTimeout(() => el.classList.remove("copied"), 700);
        }
        if (state.searchClickNav) {
          showView("viewer");
          CardManager.goToRef(h.book, h.chapter, [h.verse]);
        }
      });
    });
    host.querySelectorAll("[data-cart-add]").forEach((btn) => {
      btn.addEventListener("click", (ev) => {
        ev.stopPropagation();
        const h = searchHits[Number(btn.dataset.cartAdd)];
        if (h) addToCart({ book_num: h.book, chapter: h.chapter, verses: [h.verse], short_name: h.short });
      });
    });
  }

  function renderSearch(res) {
    const host = $("search-results");
    searchHits = (res.hits || []).map((h) => ({
      book: h.book, chapter: h.chapter, verse: h.verse, short: h.short,
    }));
    if (!searchHits.length) {
      $("search-meta").textContent = I18N.t("search.noResultMeta", { keyword: res.keyword });
      host.innerHTML = `<div class="panel-loading">${I18N.t("search.noResults")}</div>`;
      return;
    }
    // 띄어쓰기 다중 키워드일 때만 AND/OR 모드 표기(단일어는 모드 무관 폴백).
    const multi = res.keyword.trim().includes(" ");
    const modeTag = multi && res.mode ? ` · ${res.mode.toUpperCase()}` : "";
    $("search-meta").textContent =
      I18N.t("search.resultMeta", { keyword: res.keyword, count: searchHits.length, display: res.display, mode: modeTag }) +
      (state.searchClickNav ? I18N.t("search.actionCopyNav") : I18N.t("search.actionCopy"));
    const toks = res.matched_tokens || [];
    host.innerHTML = (res.hits || [])
      .map(
        (h, i) =>
          `<div class="sr" data-i="${i}"><span class="sr-ref">${esc(h.short)} ${h.chapter}:${h.verse}</span><span class="sr-text">${highlightHtml(esc(h.text), toks)}</span><span class="cart-add-btn" data-cart-add="${i}" title="${esc(I18N.t("cart.add"))}">＋</span></div>`
      )
      .join("");
    wireSearchHitClicks();
    // 옵션: 최고 점수 결과(1위) 자동 복사 + 활동 로그 기록. 결과는 점수 내림차순이라
    // searchHits[0] 이 최고점. 로그 행 클릭 시 재복사는 기존 동작이 처리.
    if (state.autoCopyTop && searchHits.length) {
      copyHit(searchHits[0]);
      const top = host.querySelector('.sr[data-i="0"]');
      if (top) { top.classList.add("copied"); setTimeout(() => top.classList.remove("copied"), 900); }
    }
  }

  // 검색 결과 하이라이트. 이미 esc()된 본문에서 매칭 토큰을 <span class="search-highlight">
  // 로 래핑한다. 토큰은 백엔드 matched_tokens(korean.tokenize — 조사 제거된 어근)이며,
  // 부분일치로 적용되어 '창조'가 '창조하시니라' 안에서도 강조된다. 대소문자 무시.
  // esc 이후에 동작하므로 안전(한국어/일반 단어엔 HTML 특수문자 없음).
  function reEscapeRx(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&"); }
  function highlightHtml(escapedText, tokens) {
    if (!escapedText || !tokens || !tokens.length) return escapedText;
    const parts = tokens.filter(Boolean).map(reEscapeRx);
    if (!parts.length) return escapedText;
    // 긴 토큰 우선(겹칠 때 더 긴 매칭) — 정규식 교대는 좌측 우선이므로 길이 내림차순.
    parts.sort((a, b) => b.length - a.length);
    const re = new RegExp("(" + parts.join("|") + ")", "gi");
    return escapedText.replace(re, '<span class="search-highlight">$1</span>');
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
      $("search-meta").textContent = I18N.t("search.strongNoResultMeta", { code: res ? res.code : "" });
      host.innerHTML = `<div class="panel-loading">${I18N.t("search.strongNoResults")}</div>`;
      return;
    }
    $("search-meta").textContent =
      I18N.t("search.strongResultMeta", { code: res.code, count: res.count }) +
      (state.searchClickNav ? I18N.t("search.strongNavSuffix") : "");
    host.innerHTML = hits
      .map(
        (h, i) =>
          `<div class="sr" data-i="${i}"><span class="sr-ref">${esc(h.ref)}</span><span class="sr-text">${esc(h.text)}</span><span class="cart-add-btn" data-cart-add="${i}" title="${esc(I18N.t("cart.add"))}">＋</span></div>`
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
      host.innerHTML = `<span class="sug-hint">${I18N.t("search.strongSuggest", { code: esc(s.replace(/\s+/g, "").toUpperCase()) })}</span>`;
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
    // v1.0.5: AND/OR 모드 토글 시(시각 전환은 공용 .seg 핸들러가 처리) 현재 검색어가
    // 있으면 즉시 재검색.
    const sm = $("search-mode");
    if (sm) {
      sm.addEventListener("click", (e) => {
        if (e.target.closest(".opt") && $("search-input").value.trim()) runSearch();
      });
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
        if (!avail.length) { toast(I18N.t("toast.allVersionsSelected")); return; }
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
      // 비례 스텝: 큰 글자일수록 큰 폭으로(대형 스크린 극대화). Max 제한 사실상 해제(400).
      const step = Math.max(1, Math.round(state.fontSize * 0.12));
      const n = Math.max(8, Math.min(400, state.fontSize + d * step));
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
    toast(res.added && res.added.length ? I18N.t("toast.versionsAdded", { n: res.added.length }) : I18N.t("toast.noNewVersions"));
  }

  // 라이브 UI 언어 전환 시 지속 렌더 영역을 현재 언어로 다시 그린다. 전부 메모리/DOM
  // 기반(브릿지 호출 없음)이라 빠른 토글에도 안전. (검색 결과 메타는 다음 검색 때 갱신.)
  function relabelDynamic() {
    try { setStatus(state.monitoring); } catch (_) {}
    try { renderLog(); } catch (_) {}
    try { renderCart(); } catch (_) {}
    if (settingsLoaded && setState) {
      try { renderFormat(); } catch (_) {}
      try { renderOrder(); } catch (_) {}
    }
  }
  window.addEventListener("i18n:changed", relabelDynamic);

  // Shared namespace (classic scripts, file:// safe). The three app scripts
  // share global scope; BC surfaces the principal handles for debugging.
  window.BC = Object.assign(window.BC || {}, { state, api, CardManager, boot });

  if (hasBridge()) {
    boot();
  } else {
    window.addEventListener("pywebviewready", boot);
  }
