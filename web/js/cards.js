// BibleClip web frontend — cards (CardManager·렌더·스크롤 싱크·원어/사전·복사).
// Shares global scope with core.js / search-notes.js (loaded in order).

"use strict";

  const CardManager = (() => {
    let cards = [];          // card descriptors (each carries free-form geometry)
    let saveTimer = null;
    let interacting = false; // true while a move/resize gesture is in flight
    let zTop = 1;            // highest z-index in use (click-to-front counter)
    let cascadeN = 0;        // cascade offset counter for newly added cards
    let activeId = null;     // id of the focused card (neon stroke + keyboard target)
    let fsCardId = null;     // id of the card currently presented fullscreen (F11)

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
          if (c.parallel && c.parallelVersion) {   // FEAT-04 대조 쌍 영속화
            o.parallel = true; o.parallelVersion = c.parallelVersion;
          }
        } else {
          o.link = c.link || null;
          if (c.type === "interlinear" && typeof c.source === "string") o.source = c.source;
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
            parallel: !!raw.parallel,             // FEAT-04 대조 쌍 복원
            parallelVersion: typeof raw.parallelVersion === "string" ? raw.parallelVersion : null,
            x: raw.x, y: raw.y, w: raw.w, h: raw.h, z: raw.z,
          });
          bibleN++;
        } else if (raw.type === "interlinear" || raw.type === "lexicon") {
          out.push({
            rawId: raw.id, id: "", type: raw.type,
            link: typeof raw.link === "string" ? raw.link : null,
            // 원전 분해 소스 역본(KJV+ 등). 미저장(undefined)이면 로드 시 UI 언어
            // 기준 기본값으로 해석한다. ''(빈문자)=개역한글S 라는 명시적 선택값.
            source: (raw.type === "interlinear" && typeof raw.source === "string")
              ? raw.source : undefined,
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
          tip = I18N.t("card.lock.needTwo");
        } else if (!card.locked && lockedN >= N - 1) {
          // The last receiving card can't be locked (N-1 rule).
          disabled = true;
          tip = I18N.t("card.lock.needReceiver");
        } else if (card.locked) {
          tip = I18N.t("card.lock.unlockHint");
        } else {
          tip = I18N.t("card.lock.lockHint");
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
          toast(I18N.t("card.lock.needReceiver"));
          return;
        }
        card.locked = true;
      }
      refreshLockStates();
      saveLayout();
    }

    // ---- DOM building ----

    // ---- 원전 분해 소스(Strong's source 역본) 선택 ----
    // 소스는 viewer 역본과 분리된 카드 자체 설정이다(역본을 바꿔도 분해는 흔들리지
    // 않는다). 기본값은 UI 언어를 따른다 — 영어 UI면 영어 Strong's 역본(KJV+),
    // 한국어면 개역한글S('')를. 사용자는 헤더 pill 로 자유롭게 바꾼다.
    function lexSourceLabel(name) {
      const list = state.lexSources || [];
      const s = list.find((x) => x.name === (name || ""));
      if (s) return s.display;
      return name || (list[0] && list[0].display) || "개역한글S";
    }
    function defaultLexSource() {
      const list = state.lexSources || [];
      if (!list.length) return "";
      const lang = window.I18N ? I18N.getLang() : "ko";
      const match = list.find((s) => s.lang === lang);
      return match ? match.name : (list[0].name || "");
    }

    function headerHTML(card) {
      const grip = `<span class="card-grip" data-tip="드래그하여 이동" data-i18n-tip="card.tip.move">⠿</span>`;
      if (card.type === "bible") {
        // FEAT-04: 다국어 대조(parallel) 토글 pill. 켜지면 대조 역본명을, 꺼지면 "대조".
        const parOn = !!(card.parallel && card.parallelVersion);
        const parLabel = parOn ? esc(card.parallelVersion) : I18N.t("card.parallelOff");
        return `<div class="card-hd">${grip}<span class="card-title" data-i18n="card.type.bible">${typeLabel("bible")}</span>` +
          `<span class="hd-mini hd-nav disabled" data-act="back" data-tip="이전 구절로" data-i18n-tip="card.tip.prevVerse">◀</span>` +
          `<span class="hd-mini hd-nav disabled" data-act="forward" data-tip="다음 구절로" data-i18n-tip="card.tip.nextVerse">▶</span>` +
          `<span class="card-hd-ctrls">` +
            `<span class="hd-pill dropdown" data-act="book">…</span>` +
            `<span class="hd-pill dropdown" data-act="chapter">${I18N.t("card.chapterLabel", { n: card.chapter || 1 })}</span>` +
            `<span class="hd-mini" data-act="prev" data-tip="이전 장" data-i18n-tip="card.tip.prevChapter">‹</span>` +
            `<span class="hd-mini" data-act="next" data-tip="다음 장" data-i18n-tip="card.tip.nextChapter">›</span>` +
            `<span class="hd-pill dropdown${parOn ? " on" : ""}" data-act="parallel" data-tip="다국어 대조 보기 (역본 쌍)" data-i18n-tip="card.tip.parallel">${parLabel}</span>` +
          `</span>` +
          `<span class="card-hd-spacer"></span>` +
          `<span class="card-lock" data-act="lock">${LOCK_OPEN}</span>` +
          `<span class="card-x" data-act="close" data-tip="카드 닫기" data-i18n-tip="card.tip.close">✕</span>` +
        `</div>`;
      }
      // 원전 분해 카드만: 분석 소스 역본 선택 pill (개역한글S / KJV+ …).
      const sourcePill = card.type === "interlinear"
        ? `<span class="hd-pill dropdown" data-act="source" data-tip="원전 분해 소스 역본 선택" data-i18n-tip="card.tip.sourceSelect">${esc(lexSourceLabel(card.source))}</span>`
        : "";
      return `<div class="card-hd">${grip}<span class="card-title" data-i18n="card.type.${card.type}">${typeLabel(card.type)}</span>` +
        `<span class="card-hd-ctrls">` +
          `<span class="hd-pill dropdown" data-act="link" data-tip="연결할 성경 카드 선택" data-i18n-tip="card.tip.linkSelect">${esc(card.link || I18N.t("card.linkNone"))}</span>` +
          sourcePill +
        `</span>` +
        `<span class="card-hd-spacer"></span>` +
        `<span class="card-x" data-act="close" data-tip="카드 닫기" data-i18n-tip="card.tip.close">✕</span>` +
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
        `<div class="card-body ${BODY_CLASS[card.type]}"><div class="panel-loading">${I18N.t("card.loading")}</div></div>` +
        handles +
      `</section>`;
    }

    function renderAll() {
      const c = container();
      if (!c) return;
      if (!cards.length) {
        c.innerHTML = `<div class="panels-empty" data-i18n-html="card.empty">카드가 없습니다.<br>우측 상단의 <b>＋ 본문 · ＋ 원어 · ＋ 사전</b> 버튼으로 카드를 추가하세요.</div>`;
        if (window.I18N) I18N.apply(c);
        return;
      }
      c.innerHTML = cards.map(skeleton).join("");
      if (window.I18N) I18N.apply(c);   // 갓 렌더된 카드 헤더 번역(data-i18n / -tip)
      normalizeLocks();
      refreshLockStates();
      // Re-apply the active highlight (innerHTML rebuild dropped the class).
      if (activeId && cardById(activeId)) setActive(cardById(activeId));
      cards.forEach((card) => loadCard(card));
    }

    // ---- BUG-03: incremental mount/unmount (기존 카드 데이터 보존) ----
    // renderAll() rebuilds the ENTIRE container (innerHTML) and reloads EVERY
    // card — fine for the one-shot initial render, but using it on add/remove
    // wiped every other card's DOM + content and re-fetched them (본문2·원어2 가
    // 빈 채로 증발). Add/remove now touch ONLY the affected card: a new card is
    // appended and loaded in isolation; a removed card's node is detached. All
    // other cards keep their live DOM, scroll position, and loaded text intact.
    // (Container-level event delegation in wireContainer keeps working because
    // the container element itself is never replaced.)
    function mountCard(card) {
      const c = container();
      if (!c) return;
      const empty = c.querySelector(".panels-empty");
      if (empty) empty.remove();                 // first card replaces the placeholder
      c.insertAdjacentHTML("beforeend", skeleton(card));
      const sec = sectionEl(card.id);
      if (sec && window.I18N) I18N.apply(sec);    // translate just this card's header
      normalizeLocks();
      refreshLockStates();                        // lock availability depends on bible count
      setActive(card);                            // the new card is on top → focus it
      loadCard(card);                             // load ONLY this card
    }

    function unmountCard(id) {
      const sec = sectionEl(id);
      if (sec) sec.remove();
      if (activeId === id) activeId = null;
      if (!cards.length) { renderAll(); return; } // restore the empty placeholder
      normalizeLocks();
      refreshLockStates();                        // count dropped → refresh lock icons
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
      body.innerHTML = `<div class="panel-loading">${I18N.t("card.loading")}</div>`;
      const navVer = state.viewer[0] || state.primary;
      await booksFor(navVer);
      const chs = await chaptersFor(navVer, card.book);
      if (!chs.includes(card.chapter)) card.chapter = chs[0] || 1;
      // Versions to show: the card's 대조(parallel) pair when on, else the global
      // viewer selection (cardVersions decides — render + copy agree).
      const viewerVers = cardVersions(card);
      const chapDataArr = await Promise.all(
        viewerVers.map((v) => api().get_chapter(v, card.book, card.chapter))
      );
      const b2 = bodyEl(card.id);
      if (b2) renderMultiVersesInto(b2, viewerVers, chapDataArr, highlight);
      updateBibleHeader(card);
      updateNavButtons(card);
      decorateNotes(card);   // 묵상 노트 배지 (Phase 3, async)
    }

    // Fetch this chapter's notes and stamp a 📄 badge on each noted verse.
    async function decorateNotes(card) {
      if (!card || card.type !== "bible") return;
      let notes = {};
      try { notes = (await api().get_chapter_notes(card.book, card.chapter)) || {}; }
      catch (e) { notes = {}; }
      noteCache[card.id] = notes;
      const body = bodyEl(card.id);
      if (!body) return;
      body.querySelectorAll(".v[data-v]").forEach((el) => {
        const old = el.querySelector(".note-badge");
        if (old) old.remove();
        const txt = notes[el.dataset.v];
        if (txt) {
          const b = document.createElement("span");
          b.className = "note-badge";
          b.textContent = "📄";
          b.title = txt.length > 80 ? txt.slice(0, 80) + "…" : txt;  // hover preview
          b.dataset.v = el.dataset.v;
          const vnum = el.querySelector(".vnum");
          if (vnum) vnum.after(b); else el.prepend(b);
        }
      });
    }

    // Ensure an interlinear (원어) card linked to a bible card, then surface it.
    function ensureInterlinearFor(bibleId) {
      const ex = cards.find(
        (c) => c.type === "interlinear" && (linkedBible(c) || {}).id === bibleId);
      if (ex) { bringToFront(ex); return ex; }
      return addCardWithLink("interlinear", bibleId);
    }

    async function loadInterlinearCard(card) {
      const body = bodyEl(card.id);
      if (!body) return;
      const src = linkedBible(card);
      updateLinkHeader(card);
      if (!src) {
        body.innerHTML = `<div class="panel-loading">${I18N.t("card.noLinkedBible")}</div>`;
        return;
      }
      body.innerHTML = `<div class="panel-loading">${I18N.t("card.loading")}</div>`;
      // 분석 소스는 카드 자체 설정(card.source) — viewer 역본과 무관하다. 미설정이면
      // UI 언어 기준 기본값(영어→KJV+, 한국어→개역한글S)으로 처음 한 번 정한다.
      if (card.source == null) card.source = defaultLexSource();
      const data = await api().get_interlinear(src.book, src.chapter, card.source);
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
        body.innerHTML = `<div class="panel-loading">${I18N.t("card.loadingCode", { code: esc(cur.code) })}</div>`;
        api().lookup_strong(cur.code, lexLang, cur.book, cur.chapter, cur.verse || null)
          .then((res) => { const b = bodyEl(card.id); if (b) renderLexEntryInto(b, cur.code, res); });
      } else {
        // data-i18n 부착: 사전 카드를 띄운 채 언어를 바꿔도 I18N.apply 전역 스윕이
        // 이 안내 문구를 즉시 재번역한다(BUG-i18n: 영어 전환 후에도 한국어로 고정되던
        // 현상). 키는 이미 ko/en 양쪽에 존재하는 card.clickStrong 을 재사용한다.
        body.innerHTML = `<div class="panel-loading" data-i18n="card.clickStrong">${I18N.t("card.clickStrong")}</div>`;
      }
    }

    function updateBibleHeader(card) {
      const s = sectionEl(card.id);
      if (!s) return;
      const navVer = state.viewer[0] || state.primary;
      const bp = s.querySelector('[data-act="book"]'); if (bp) bp.textContent = bookShortFor(navVer, card.book) || "…";
      const cp = s.querySelector('[data-act="chapter"]'); if (cp) cp.textContent = I18N.t("card.chapterLabel", { n: card.chapter });
      const pp = s.querySelector('[data-act="parallel"]');
      if (pp) {                                  // FEAT-04 대조 pill 라벨/활성 갱신
        const on = !!(card.parallel && card.parallelVersion);
        pp.textContent = on ? card.parallelVersion : I18N.t("card.parallelOff");
        pp.classList.toggle("on", on);
      }
    }
    function updateLinkHeader(card) {
      const s = sectionEl(card.id);
      if (!s) return;
      const lp = s.querySelector('[data-act="link"]');
      const src = linkedBible(card);
      if (lp) lp.textContent = src ? src.id : I18N.t("card.linkNone");
      if (card.type === "interlinear") {
        const sp = s.querySelector('[data-act="source"]');
        if (sp) sp.textContent = lexSourceLabel(card.source);
      }
    }

    // Reload interlinear cards that follow the given bible card (its book/chapter
    // changed). Lexicon cards are driven by clicks, so they aren't reloaded here.
    // Returns a promise that resolves once every linked 원어 card has re-rendered,
    // so callers can align them to the new position afterwards (BUG-01).
    function reloadDependents(card) {
      return Promise.all(
        cards.filter((c) => c.type === "interlinear" && linkedBible(c) === card)
          .map(loadInterlinearCard)
      );
    }

    // ---- mutations (add / remove) ----
    // New cards appear at the CENTER of the workspace, on top of everything,
    // with a small cascade offset so consecutive adds don't perfectly overlap.
    // Existing cards keep their positions (the user rearranges manually).

    function addCard(type) {
      // Free tier (Phase 1): a single card only. Premium unlocks the workspace.
      if (!state.isPremium && cards.length >= 1) {
        toast(I18N.t("card.toast.freeOnePlace"));
        return;
      }
      if (type === "bible" && bibleCards().length >= MAX_BIBLE) {
        toast(I18N.t("card.toast.maxBible", { max: MAX_BIBLE }));
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
      mountCard(card);   // BUG-03: append only this card (others untouched)
      saveLayout();
    }

    function removeCard(id) {
      const i = cards.findIndex((c) => c.id === id);
      if (i < 0) return;
      const wasBible = cards[i].type === "bible";
      cards.splice(i, 1);
      unmountCard(id);   // BUG-03: detach only this card (others untouched)
      // Dependents linked to a removed bible card fall back to the first bible —
      // re-point + reload just those (not a global re-render).
      if (wasBible) {
        const fb = (firstBible() && firstBible().id) || null;
        cards.forEach((c) => {
          if (c.type !== "bible" && c.link === id) { c.link = fb; loadCard(c); }
        });
      }
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
      if (!el) return;
      // Body-scoped scroll (NOT el.scrollIntoView, which also nudges the
      // workspace and drags every other card — see FIX-01 / centerHighlightVerse).
      const br = body.getBoundingClientRect();
      body.scrollTop += el.getBoundingClientRect().top - br.top;
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
      await reloadDependents(card);
      scrollVerseToTop(card, ref.verse);   // restore scroll position (작업 5)
      const hbody = bodyEl(card.id);       // keep linked 원어 aligned (BUG-01)
      if (hbody) requestAnimationFrame(() => syncInterlinFrom(card, hbody));
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
      // Priority 0: the fullscreen-presented card (F2 jump during a presentation)
      // — it always navigates in place, even if locked, so the slide follows.
      const fsCard = (fsCardId && document.fullscreenElement)
        ? bibles.find((c) => c.id === fsCardId) : null;
      // Priority 1: locked card that already shows this book+chapter.
      const matchedLocked = bibles.find(
        (c) => c.locked && c.book === book && c.chapter === chapter
      );
      // Priority 2: first unlocked card.
      const firstUnlocked = bibles.find((c) => !c.locked);
      const target = fsCard || matchedLocked || firstUnlocked;
      if (!target) return;

      if (target === fsCard || !target.locked) {
        // Navigate to the incoming position.
        target.book = book;
        const chs = await chaptersFor(state.viewer[0] || state.primary, book);
        target.chapter = chs.includes(chapter) ? chapter : (chs[0] || chapter);
      }
      // Render (highlight the specific verses).
      await loadBibleCard(target, verses && verses.length ? verses : null);
      // BUG-01: the linked 원어(interlinear) card re-renders from the chapter top
      // and would stay pinned at 1절. Wait for its reload, then snap it to the
      // SAME verse the 본문 just jumped to (matching height), exactly as the
      // real-time scroll sync would — instead of leaving it at the chapter head.
      await reloadDependents(target);
      const tbody = bodyEl(target.id);
      if (tbody) requestAnimationFrame(() => syncInterlinFrom(target, tbody));
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
        case "parallel": {
          // FEAT-04: 대조 역본 선택(끄기 + navVer 제외한 역본들). 켜면 기준+대조 쌍 렌더.
          const base = state.viewer[0] || state.primary;
          const items = [{ label: I18N.t("card.parallelOff"), value: "", on: !card.parallel }];
          state.versions.filter((v) => v.name !== base).forEach((v) =>
            items.push({ label: v.display, value: v.name,
                         on: !!(card.parallel && card.parallelVersion === v.name) }));
          openMenu(actEl, items, async (name) => {
            if (!name) { card.parallel = false; }
            else { card.parallel = true; card.parallelVersion = name; }
            await loadBibleCard(card);
            reloadDependents(card);
            updateBibleHeader(card);
            saveLayout();
          });
          break;
        }
        case "back": cardHistoryNav(card, -1); break;
        case "forward": cardHistoryNav(card, 1); break;
        case "lock": toggleLock(card); break;
        case "close": removeCard(card.id); break;
        case "link":
          openMenu(actEl,
            bibleCards().map((b) => ({ label: b.id, value: b.id, on: b.id === card.link })),
            (id) => { card.link = id; loadCard(card); saveLayout(); });
          break;
        case "source": {
          // 원전 분해 소스 역본 전환 — 즉시 재로드(역본/언어 무관, 카드 자체 설정).
          const list = state.lexSources || [];
          if (!list.length) break;
          const cur = card.source == null ? defaultLexSource() : card.source;
          openMenu(actEl,
            list.map((s) => ({ label: s.display, value: s.name, on: s.name === cur })),
            (name) => { card.source = name; loadInterlinearCard(card); saveLayout(); });
          break;
        }
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

    // ---- F11 presentation: fullscreen the active bible card (성구만 가득) ----
    function presentToggle() {
      if (document.fullscreenElement) { document.exitFullscreen().catch(() => {}); return; }
      const card = activeBibleCard();
      if (!card) return;
      const el = sectionEl(card.id);
      if (!el || !el.requestFullscreen) return;
      fsCardId = card.id;
      el.requestFullscreen().then(() => {
        const hint = document.createElement("div");
        hint.className = "present-hint";
        hint.textContent = window.I18N ? I18N.t("present.hint") : "F2 검색 · ESC 나가기";
        el.appendChild(hint);
      }).catch(() => { fsCardId = null; });
    }
    // Exiting fullscreen (ESC / F11): drop the hint + tracking.
    document.addEventListener("fullscreenchange", () => {
      if (!document.fullscreenElement) {
        document.querySelectorAll(".present-hint").forEach((h) => h.remove());
        fsCardId = null;
      }
    });

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
    const progScroll = new Set();  // card ids being programmatically scrolled (sync guard)

    // The topmost fully-visible verse number in a scripture body (or null).
    // 시선 중심선: 스크롤 바디의 위에서 40% 지점. 이 밴드를 품은 절이 앵커.
    const SIGHT_BAND = 0.4;

    // The anchor verse drives interlinear + split-compare sync. We anchor on the
    // verse occupying the reader's sight line (a band ~40% down the viewport)
    // instead of the topmost uncut verse — the latter flipped the instant the
    // next verse merely peeked in at the bottom (튕김/강제 전환). The verse
    // straddling the sight line wins; if none does (gaps / short bodies) we fall
    // back to the verse with the largest visible slice inside the body. Center
    // anchoring resists jitter: a new verse only takes over once it genuinely
    // rises into the gaze band.
    function anchorVerseOf(body) {
      const br = body.getBoundingClientRect();
      const sightY = br.top + br.height * SIGHT_BAND;
      let best = null, bestVis = 0;
      for (const v of body.querySelectorAll(".v[data-v]")) {
        const r = v.getBoundingClientRect();
        if (r.top <= sightY && r.bottom >= sightY) return +v.dataset.v;  // straddles the line
        const vis = Math.min(r.bottom, br.bottom) - Math.max(r.top, br.top);
        if (vis > bestVis) { bestVis = vis; best = +v.dataset.v; }
      }
      return best;
    }

    // Align another scroll body so verse `n` sits at fraction `align` down its
    // viewport (0 = top). `markId` (when the target is a bible card) is flagged
    // in progScroll so the resulting scroll event is ignored — preventing an
    // A→B→A sync feedback loop.
    function scrollBodyToVerse(targetBody, n, markId, align = 0) {
      const target = targetBody.querySelector(`.v[data-v="${n}"]`);
      if (!target) return;
      if (markId) progScroll.add(markId);
      const br = targetBody.getBoundingClientRect();
      targetBody.scrollTop += target.getBoundingClientRect().top - br.top - br.height * align;
      if (markId) setTimeout(() => progScroll.delete(markId), 150);
    }

    // Real-time (every frame): keep ONLY this card's linked 원어(interlinear)
    // cards aligned to its anchor verse, placed at the SAME viewport fraction the
    // anchor occupies in the bible card. Aligning the 원어 verse to its own TOP
    // (the old behavior) shoved the bible's leading verses above the fold — the
    // "1절 스킵". Matching the fraction makes the two read in lockstep, and being
    // verse-DOM + fraction based it's immune to font family/size differences
    // between the cards. Does NOT touch history (debounced, 7차-2).
    //
    // BUG-02 (v1.0.7 격리): a bible card NEVER drives another bible card. Two
    // cards on the same book/chapter scroll/navigate independently — the old
    // same-chapter cross-sync made them move together like magnets. Each card
    // owns only its own scroll + the interlinear cards explicitly linked to it.
    function syncInterlinFrom(card, body) {
      const n = anchorVerseOf(body);
      if (!n) return;
      const frac = verseTopFraction(body, n);
      cards.forEach((c) => {
        if (c === card) return;
        if (c.type === "interlinear" && linkedBible(c) === card) {
          const ib = bodyEl(c.id);
          if (ib) scrollBodyToVerse(ib, n, null, frac);  // 동일 절을 동일 높이로 정렬
        }
      });
    }

    // The viewport fraction (0 = top) at which verse n's top currently sits in a
    // body — lets another card place the same verse at the same height.
    function verseTopFraction(body, n) {
      const el = body.querySelector(`.v[data-v="${n}"]`);
      if (!el) return 0;
      const br = body.getBoundingClientRect();
      const f = (el.getBoundingClientRect().top - br.top) / (br.height || 1);
      return Math.max(0, Math.min(0.9, f));
    }

    // ---- BUG-01: hold the reading position across font family/size changes ----
    // A font swap or A−/A+ reflows the scripture (word-wrap + line height), so a
    // px-preserved scrollTop lands on a different verse — and the linked 원어 card
    // drifts with it ("겉도는"/1절 스킵). We snapshot each bible card's anchor
    // verse AND the exact fraction it sits at BEFORE the reflow, then restore that
    // verse to the same fraction AFTER it and re-align the linked 원어. Purely
    // verse-DOM based (the 절 ID 앵커), immune to the font in play. The size reflow
    // is synchronous and a family swap is already loaded (injectFont awaits the
    // face), so one rAF after the change is enough.
    function snapshotAnchors() {
      const m = new Map();
      bibleCards().forEach((c) => {
        const b = bodyEl(c.id);
        if (!b) return;
        const n = anchorVerseOf(b);
        if (n) m.set(c.id, { n, frac: verseTopFraction(b, n) });
      });
      return m;
    }
    function realignAnchors(anchors) {
      requestAnimationFrame(() => {
        bibleCards().forEach((c) => {
          const b = bodyEl(c.id);
          if (!b) return;
          const a = anchors && anchors.get(c.id);
          if (a) scrollBodyToVerse(b, a.n, c.id, a.frac);  // restore bible position
          syncInterlinFrom(c, b);                          // realign linked 원어
        });
      });
    }

    // Debounced (500ms after scrolling stops): lock the settled top verse into
    // the card's current history entry so ◀ ▶ restore the scroll position. While
    // the wheel is moving, history writes are held off entirely (7차-2).
    function lockHistoryVerse(card, body) {
      const n = anchorVerseOf(body);
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
        if (t) {
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
          return;
        }
        // Right-click a bible verse → context menu (복사 / 묵상 노트 / 원어, Phase 3)
        const vEl = e.target.closest('.mcard[data-type="bible"] .v[data-v]');
        if (vEl) {
          const card = cardById(vEl.closest(".mcard").dataset.id);
          if (card) { e.preventDefault(); showVerseMenu(card, +vEl.dataset.v, e.clientX, e.clientY); }
        }
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
        if (progScroll.has(card.id)) return;  // this scroll was programmatic (sibling sync)
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
        toast(I18N.t("card.toast.freeOne"));
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
      mountCard(card);   // BUG-03: append only this card (others untouched)
      saveLayout();
      return card;
    }

    // Re-label the JS-rendered header bits (chapter/link pills) + lock tooltips
    // in the current UI language. Called on i18n:changed. Pure DOM / cache reads —
    // NO backend round-trip, so a rapid language toggle can't flood the bridge.
    // (Tooltips/titles via data-i18n* are handled by the global I18N.apply.)
    function relabel() {
      refreshLockStates();
      cards.forEach((card) => {
        if (card.type === "bible") updateBibleHeader(card);
        else updateLinkHeader(card);
      });
    }

    return { init, addCard, addCardWithLink, goToRef, primaryVersion,
             primaryBible, bibleCards, lexiconCards, bodyEl, linkedBibleFor,
             chapStepPrimary, chapStepActive, reloadAllBible, relabel,
             presentToggle, ensureInterlinearFor, decorateNotesFor: decorateNotes,
             snapshotAnchors, realignAnchors };
  })();

  // ---- Scripture / interlinear / lexicon rendering (into a card body) ----

  // Scroll a card body so its first highlighted verse sits centered, WITHOUT
  // Element.scrollIntoView — that walks every scrollable ancestor and nudges the
  // workspace (overflow:hidden but still programmatically scrollable), dragging
  // every other card's apparent position with it. That entanglement is FIX-01:
  // F2 점프로 잠금 카드를 띄울 때 메인 카드 스크롤과 엉켜 엉뚱한 절이 보이던 현상.
  // FEAT-04: the version list a bible card displays. When 대조(parallel) mode is
  // on, it's a fixed pair [기준 역본(viewer[0]), 대조 역본] independent of the
  // global viewer selection; otherwise the global viewer set. Shared by render
  // AND copy so both stay in lockstep (copy keeps the per-version block format).
  function cardVersions(card) {
    const navVer = state.viewer[0] || state.primary;
    if (card && card.parallel && card.parallelVersion
        && state.versionsNames.includes(card.parallelVersion)
        && card.parallelVersion !== navVer) {
      return [navVer, card.parallelVersion].filter(Boolean);
    }
    return state.viewer.length ? state.viewer.slice() : [navVer].filter(Boolean);
  }

  function centerHighlightVerse(body) {
    const first = body.querySelector(".v.hl");
    if (!first) return;
    const br = body.getBoundingClientRect();
    const fr = first.getBoundingClientRect();
    body.scrollTop += (fr.top - br.top) - (br.height - fr.height) / 2;
  }

  function renderVersesInto(body, verses, highlight) {
    if (!verses || !verses.length) {
      body.innerHTML = `<div class="panel-loading">${I18N.t("card.noText")}</div>`;
      return;
    }
    const hl = new Set(highlight || []);
    body.innerHTML = verses
      .map((v) => `<div class="v${hl.has(v.n) ? " hl" : ""}" data-v="${v.n}"><span class="vnum">${v.n}</span>${esc(v.text)}</div>`)
      .join("");
    if (hl.size) centerHighlightVerse(body);
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
    if (!verseMap.size) { body.innerHTML = `<div class="panel-loading">${I18N.t("card.noText")}</div>`; return; }
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
    if (hl.size) centerHighlightVerse(body);
  }

  function renderInterlinearInto(body, data) {
    if (!data || !data.length) {
      body.innerHTML = `<div class="panel-loading">${I18N.t("card.noOriginalData")}</div>`;
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
    return `<div class="morph"><div class="morph-h">${I18N.t("dict.morphHeading")}</div>${rows}</div>`;
  }

  function renderLexEntryInto(body, code, res) {
    if (!res) {
      // No entry. Distinguish "no dictionary module installed" (guide the user
      // to add one — copyright-clean default ships without lexicons) from "this
      // code simply isn't in the installed dictionary".
      const noModule = state.lexAvail && !state.lexAvail.ko && !state.lexAvail.en;
      const msg = noModule
        ? I18N.t("card.noLexModule")
        : I18N.t("dict.noEntry");
      body.innerHTML = `<span class="chip">${esc(code)}</span><div class="lex-body">${msg}</div>`;
      return;
    }
    const head = res.headword
      ? `<div class="lex-head"><span class="heb">${esc(res.headword)}</span>` +
        `<span class="rom">${esc(res.reading)}</span></div>`
      : "";
    body.innerHTML =
      `<span class="chip">${esc(res.code)}</span>${head}${renderMorph(res.morph)}` +
      `<div class="lex-body">${res.html || I18N.t("dict.noEntry")}</div>`;
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
      if (b) b.innerHTML = `<div class="panel-loading">${I18N.t("card.loadingCode", { code: esc(code) })}</div>`;
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
    // Copy the versions the card is actually SHOWING — its 대조 쌍 when parallel
    // mode is on, else the global viewer (cardVersions). Block format unchanged
    // (format_reference joins per-version blocks). A stale per-card card.version
    // would copy the wrong text AND miss the book-name cache → "?".
    const versions = cardVersions(card);
    const r = await api().copy_reference(card.book, card.chapter, verses, versions);
    if (!r || !r.ok) return;
    const nameVer = versions[0] || card.version;
    // 책이름은 백엔드가 정식/약칭 설정 + 복사된 역본 기준으로 돌려준 short_name 을 쓴다
    // (모니터 토스트와 동일 출처 _display_book_name). 폴백으로만 프론트 약칭 조회.
    const short = r.short_name || (await booksFor(nameVer), bookShortFor(nameVer, card.book));
    toast(I18N.t("toast.copiedRef", { ref: `${short} ${card.chapter}:${verses.join(",")}` }));
    logReference({ book_num: card.book, chapter: card.chapter, verses,
      short_name: short, n_parts: r.n_parts || 1, text: r.text });
    const body = CardManager.bodyEl(card.id);
    if (!body) return;
    verses.forEach((n) => {
      const el = body.querySelector(`.v[data-v="${n}"]`);
      if (el) { el.classList.add("copied"); setTimeout(() => el.classList.remove("copied"), 700); }
    });
  }

