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
      `<div class="ctx-item" data-a="copy">구절 복사</div>` +
      `<div class="ctx-item" data-a="note">${has ? "묵상 노트 수정" : "묵상 노트 쓰기"}</div>` +
      `<div class="ctx-item" data-a="orig">원어 코드 조회</div>`;
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

  async function openNoteEditor(card, verse) {
    hideVerseMenu();
    let existing = null;
    try { existing = await api().get_note(card.book, card.chapter, verse); } catch (e) {}
    const back = document.createElement("div");
    back.className = "note-modal-back";
    back.innerHTML =
      `<div class="note-modal" role="dialog" aria-modal="true">` +
        `<div class="note-modal-h"><span>📄 묵상 노트</span>` +
          `<span class="note-modal-ref">${esc(refLabel(card, verse))}</span></div>` +
        `<textarea class="note-ta" placeholder="이 구절에 대한 묵상을 적어 보세요…"></textarea>` +
        `<div class="note-modal-foot">` +
          `<button class="btn note-del" ${existing ? "" : "hidden"}>삭제</button>` +
          `<span class="note-modal-spacer"></span>` +
          `<button class="btn note-cancel">취소</button>` +
          `<button class="btn primary note-save">저장</button>` +
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
      toast("묵상 노트 저장됨");
      close();
    });
    const del = back.querySelector(".note-del");
    if (del) del.addEventListener("click", async () => {
      await api().delete_note(card.book, card.chapter, verse);
      await refresh();
      toast("묵상 노트 삭제됨");
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

  async function checkUpdate(silent) {
    if (!silent) toast("업데이트 확인 중…");
    let r = null;
    try { r = await api().check_update(); } catch (e) { r = null; }
    if (!r || !r.ok) { if (!silent) toast("업데이트 확인 실패"); return; }
    if (r.has_update && r.mandatory) {
      // Soft forced update (Phase 4): non-dismissible modal, but app still runs.
      updateInfo = r;
      showForcedUpdate(r);
    } else if (r.has_update && !(silent && r.skipped)) {
      updateInfo = r;
      $("ub-text").textContent = `새 버전 v${r.latest} 사용 가능 — 현재 v${r.current}`;
      $("update-banner").hidden = false;
    } else if (!silent) {
      toast(`최신 버전입니다 (v${r.current})`);
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
        `<div class="patch-h forced-h">⚠ 업데이트가 필요합니다</div>` +
        `<p class="forced-text">현재 <b>v${esc(r.current)}</b> — 새 버전 <b>v${esc(r.latest)}</b>로 업데이트해야 계속 사용할 수 있습니다.</p>` +
        `<div class="note-modal-foot"><span class="note-modal-spacer"></span>` +
          `<button class="btn forced-page">릴리스 페이지</button>` +
          `<button class="btn primary forced-install">지금 업데이트</button></div>` +
      `</div>`;
    document.body.appendChild(back);
    back.querySelector(".forced-page").addEventListener("click", () => api().open_releases_page());
    back.querySelector(".forced-install").addEventListener("click", async () => {
      const x = await api().install_update();
      if (!x || !x.ok) toast(x && x.error ? x.error : "릴리스 페이지에서 받아 주세요");
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
        `<div class="patch-h"><span class="patch-badge">NEW</span> v${esc(p.version)} 업데이트 내역</div>` +
        `<ul class="patch-list">${p.notes.map((n) => `<li>${esc(n)}</li>`).join("")}</ul>` +
        `<label class="patch-dismiss"><input type="checkbox" class="patch-cb"> 다시 보지 않기</label>` +
        `<div class="note-modal-foot"><span class="note-modal-spacer"></span>` +
          `<button class="btn primary patch-ok">확인</button></div>` +
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

    // 3) Keyword search (default). v1.0.5: 띄어쓰기 다중 키워드면 AND/OR 모드 적용.
    $("search-meta").textContent = "";
    $("search-results").innerHTML = `<div class="panel-loading">검색 중…</div>`;
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
      toast(`${h.short} ${h.chapter}:${h.verse} 복사됨`);
      logReference({ book_num: h.book, chapter: h.chapter, verses: [h.verse],
        short_name: h.short, n_parts: r.n_parts || 1, text: r.text });
    }
    return r;
  }

  // Click handler shared by keyword + strong-code results.
  function wireSearchHitClicks() {
    $("search-results").querySelectorAll(".sr").forEach((el) => {
      el.addEventListener("click", async () => {
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
    // 띄어쓰기 다중 키워드일 때만 AND/OR 모드 표기(단일어는 모드 무관 폴백).
    const multi = res.keyword.trim().includes(" ");
    const modeTag = multi && res.mode ? ` · ${res.mode.toUpperCase()}` : "";
    $("search-meta").textContent =
      `"${res.keyword}" 결과 ${searchHits.length}건 · ${res.display}${modeTag} — 구절 클릭 시 ` +
      (state.searchClickNav ? "복사 + 본문 이동" : "복사");
    const toks = res.matched_tokens || [];
    host.innerHTML = (res.hits || [])
      .map(
        (h, i) =>
          `<div class="sr" data-i="${i}"><span class="sr-ref">${esc(h.short)} ${h.chapter}:${h.verse}</span><span class="sr-text">${highlightHtml(esc(h.text), toks)}</span></div>`
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

  // Shared namespace (classic scripts, file:// safe). The three app scripts
  // share global scope; BC surfaces the principal handles for debugging.
  window.BC = Object.assign(window.BC || {}, { state, api, CardManager, boot });

  if (hasBridge()) {
    boot();
  } else {
    window.addEventListener("pywebviewready", boot);
  }
