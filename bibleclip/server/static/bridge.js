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

  // ---- 홈으로 · 커뮤니티에서 온 구절 열기 ----

  // 주소 끝의 #go=<책>.<장>.<절,절…> (커뮤니티 글 속 구절 링크) → 그 구절로.
  // 첫 화면이 본문을 다 그린 뒤에 옮겨야 처음 불러오기가 덮어쓰지 않는다.
  function goFromHash() {
    const m = /^#go=(\d+)\.(\d+)(?:\.([\d,]+))?$/.exec(location.hash);
    if (!m) return;
    const book = +m[1], chapter = +m[2];
    const verses = m[3] ? m[3].split(",").map(Number).filter(Boolean) : null;
    let tries = 0;
    (function wait() {
      const BC = window.BC;
      const ready = BC && BC.CardManager && document.querySelector('.mcard[data-type="bible"] .v[data-v]');
      if (ready) {
        BC.CardManager.goToRef(book, chapter, verses);
        history.replaceState(null, "", location.pathname + location.search);
      } else if (tries++ < 75) {
        setTimeout(wait, 200);
      }
    })();
  }
  window.addEventListener("hashchange", goFromHash);

  // ---- 성경 ↔ 커뮤니티 (4단계) ----
  // web/ 의 코드는 건드리지 않고, 화면이 그려진 결과(DOM) 위에만 얹는다:
  //   ① 절 메뉴에 "함께 쓰기"  ② 글이 달린 절 표시(💬)  ③ 상대 형광펜 밑줄
  // ③은 CSS Custom Highlight(문서 구조를 바꾸지 않고 글자 구간에 모양만 입힘)라서
  //    내 형광펜(.vtx 안의 span)과 그 위치 계산을 전혀 건드리지 않는다.

  function capi(action, args) {
    return fetch("capi/" + action, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-BibleClip": "1" },
      body: JSON.stringify(args || {}),
    }).then(function (r) {
      if (r.status === 401) toLogin();
      return r.ok ? r.json().then(function (b) { return b.value; }) : null;
    });
  }

  function bibleCardOf(el) {
    const sec = el && el.closest('.mcard[data-type="bible"]');
    if (!sec || !window.BC || !BC.CardManager) return null;
    const card = BC.CardManager.bibleCards().find(function (c) { return String(c.id) === sec.dataset.id; });
    return card ? { card: card, sec: sec } : null;
  }

  // ① 절 메뉴 "함께 쓰기" — 우클릭(폰은 길게 누르기)한 절, 여러 절을 끌어 골랐으면 그 범위.
  let lastPick = null;
  document.addEventListener("contextmenu", function (e) {
    const v = e.target.closest && e.target.closest('.mcard[data-type="bible"] .v[data-v]');
    const hit = v && bibleCardOf(v);
    if (!hit) { lastPick = null; return; }
    let lo = +v.dataset.v, hi = lo;
    const sel = window.getSelection();
    if (sel && !sel.isCollapsed) {
      [sel.anchorNode, sel.focusNode].forEach(function (n) {
        const el = n && (n.nodeType === 1 ? n : n.parentElement);
        const sv = el && el.closest(".v[data-v]");
        if (sv && hit.sec.contains(sv)) { lo = Math.min(lo, +sv.dataset.v); hi = Math.max(hi, +sv.dataset.v); }
      });
    }
    lastPick = { book: hit.card.book, chapter: hit.card.chapter, verse: lo, verse_end: hi };
  }, true);

  function addShareItem(menu) {
    if (!lastPick || menu.querySelector('[data-a="share"]')) return;
    const p = lastPick;
    const it = document.createElement("div");
    it.className = "ctx-item";
    it.dataset.a = "share";
    it.textContent = "함께 쓰기(커뮤니티)" + (p.verse_end > p.verse ? " · " + p.verse + "-" + p.verse_end + "절" : "");
    it.addEventListener("mousedown", function () {
      location.href = "community#/new?verse=" + p.book + "." + p.chapter + "." + p.verse + "-" + p.verse_end;
    });
    menu.appendChild(it);
  }

  // ② 글이 달린 절 표시. 장마다 한 번 묻고 잠시 기억한다(다시 그려도 묻지 않게).
  const postCache = new Map();        // "책.장" → {at, posts}
  const POST_TTL = 30000;
  function chapterPosts(book, chapter) {
    const k = book + "." + chapter;
    const c = postCache.get(k);
    if (!c || Date.now() - c.at >= POST_TTL) {     // 처음이거나 오래됐으면 새로 묻는다(그동안은 옛 값)
      postCache.set(k, { at: Date.now(), posts: c ? c.posts : null });
      capi("verse_posts", { book: book, chapter: chapter }).then(function (r) {
        postCache.set(k, { at: Date.now(), posts: (r && r.posts) || [] });
        schedule();
      }).catch(function () {});
    }
    return c ? c.posts : null;
  }

  function hostOf(v) {                 // note-badge 와 같은 자리(병렬 독서는 첫 칸 안)
    return v.classList.contains("srow")
      ? (v.querySelector(".scell:not(.empty)") || v.querySelector(".scell") || v) : v;
  }

  function decorateShared(sec, card) {
    const posts = chapterPosts(card.book, card.chapter);
    const key = card.book + "." + card.chapter + ":" + (posts ? posts.map(function (p) { return p.id; }).join(",") : "-");
    const verses = sec.querySelectorAll(".v[data-v]");
    if (!verses.length) return;
    // 이미 이 장 · 이 글들로 표시했고 그대로 남아 있으면 건너뛴다(다시 그리면 표시가 사라진다).
    if (sec.dataset.wcKey === key && sec.querySelector(".v[data-v]").dataset.wcDone === key) return;
    sec.querySelectorAll(".wc-badge").forEach(function (b) { b.remove(); });
    verses.forEach(function (v) { v.classList.remove("wc-shared"); v.dataset.wcDone = key; });
    sec.dataset.wcKey = key;
    if (!posts || !posts.length) return;
    const first = new Map();           // 첫 절 → 그 절에서 시작하는 글들
    posts.forEach(function (p) {
      for (let n = p.verse.verse; n <= p.verse.verse_end; n++) {
        const v = sec.querySelector('.v[data-v="' + n + '"]');
        if (v) v.classList.add("wc-shared");
      }
      const list = first.get(p.verse.verse) || [];
      list.push(p);
      first.set(p.verse.verse, list);
    });
    first.forEach(function (list, n) {
      const v = sec.querySelector('.v[data-v="' + n + '"]');
      if (!v) return;
      const b = document.createElement("span");
      b.className = "wc-badge" + (list.some(function (p) { return p.is_new || p.new_comments; }) ? " new" : "");
      b.textContent = "💬" + (list.length > 1 ? list.length : "");
      b.title = list.map(function (p) { return p.verse.label + " · " + p.title + " — " + p.author.name; }).join("\n");
      b.addEventListener("click", function (e) {
        e.preventDefault();
        e.stopPropagation();
        openSharedPop(b, card, n, posts);
      });
      ["mousedown", "mouseup", "pointerdown"].forEach(function (t) {
        b.addEventListener(t, function (e) { e.stopPropagation(); });
      });
      hostOf(v).appendChild(b);
    });
  }

  let sharedPop = null;
  function closeSharedPop() { if (sharedPop) { sharedPop.remove(); sharedPop = null; } }
  function openSharedPop(anchor, card, n, posts) {
    closeSharedPop();
    const list = posts.filter(function (p) { return p.verse.verse <= n && n <= p.verse.verse_end; });
    const pop = document.createElement("div");
    pop.className = "wc-pop";
    const esc = function (s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; };
    pop.innerHTML = list.map(function (p) {
      return '<a class="wc-item" href="community#/p/' + p.id + '"><b>' + esc(p.title) + "</b>" +
        '<span>' + esc(p.verse.label) + " · " + esc(p.author.name) + " · 댓글 " + p.comments +
        (p.is_new || p.new_comments ? ' <i class="wc-new">새</i>' : "") + "</span></a>";
    }).join("") + '<a class="wc-write" href="community#/new?verse=' + card.book + "." + card.chapter + "." + n + "-" + n +
      '">＋ 이 절로 함께 쓰기</a>';
    (document.fullscreenElement || document.body).appendChild(pop);
    const r = anchor.getBoundingClientRect(), pr = pop.getBoundingClientRect();
    pop.style.left = Math.max(8, Math.min(r.left, window.innerWidth - pr.width - 8)) + "px";
    pop.style.top = (r.bottom + pr.height + 8 > window.innerHeight ? r.top - pr.height - 6 : r.bottom + 6) + "px";
    sharedPop = pop;
  }
  document.addEventListener("pointerdown", function (e) {
    if (sharedPop && !sharedPop.contains(e.target) && !e.target.closest(".wc-badge")) closeSharedPop();
  }, true);
  document.addEventListener("scroll", closeSharedPop, true);

  // ③ 상대 형광펜 — 밑줄. 설정에서 끌 수 있다(이 기기에만 기억).
  const HL_OK = !!(window.CSS && CSS.highlights && window.Highlight);
  const hlCache = new Map();           // "책.장|역본들" → {at, data}
  let partnerOn = true;
  try { partnerOn = localStorage.getItem("bc-partner-hl") !== "0"; } catch (_) {}

  function partnerData(book, chapter, versions) {
    const k = book + "." + chapter + "|" + versions.join(",");
    const c = hlCache.get(k);
    if (!c || Date.now() - c.at >= POST_TTL) {
      hlCache.set(k, { at: Date.now(), data: c ? c.data : null });
      capi("partner_highlights", { book: book, chapter: chapter, versions: versions }).then(function (r) {
        hlCache.set(k, { at: Date.now(), data: r || [] });
        schedule();
      }).catch(function () {});
    }
    return c ? c.data : null;
  }

  // .vtx 안 글자 위치 → (글자 마디, 그 안의 위치). 내 형광펜 span 이 끼어 있어도 글자만 센다.
  function rangeIn(vtx, s, e) {
    const w = document.createTreeWalker(vtx, NodeFilter.SHOW_TEXT);
    let pos = 0, n, start = null;
    const r = document.createRange();
    while ((n = w.nextNode())) {
      const len = n.nodeValue.length;
      if (!start && s <= pos + len) { r.setStart(n, s - pos); start = n; }
      if (start && e <= pos + len) { r.setEnd(n, e - pos); return r; }
      pos += len;
    }
    return null;
  }

  function paintPartner(cards) {
    if (!HL_OK) return;
    const byColor = { y: [], g: [], b: [], p: [] };
    if (partnerOn) {
      cards.forEach(function (x) {
        const vers = Array.from(new Set(Array.from(x.sec.querySelectorAll(".vtx[data-ver]"))
          .map(function (el) { return el.dataset.ver; }))).sort();
        if (!vers.length) return;
        const data = partnerData(x.card.book, x.card.chapter, vers);
        (data || []).forEach(function (u) {
          Object.keys(u.hl).forEach(function (ver) {
            const verses = u.hl[ver] || {};
            Object.keys(verses).forEach(function (vn) {
              const vtx = x.sec.querySelector('.v[data-v="' + vn + '"] .vtx[data-ver="' + CSS.escape(ver) + '"]');
              if (!vtx) return;
              const text = vtx.textContent;
              (verses[vn] || []).forEach(function (h) {
                let s = h.s, e = h.e;
                if (h.t && text.slice(s, e) !== h.t) {     // 본문이 밀렸으면 글자로 다시 찾기
                  const i = text.indexOf(h.t);
                  if (i < 0) return;
                  s = i; e = i + h.t.length;
                }
                const r = e > s ? rangeIn(vtx, s, e) : null;
                if (r) (byColor[h.c] || byColor.y).push(r);
              });
            });
          });
        });
      });
    }
    Object.keys(byColor).forEach(function (c) {
      if (byColor[c].length) CSS.highlights.set("bc-partner-" + c, new Highlight(...byColor[c]));
      else CSS.highlights.delete("bc-partner-" + c);
    });
  }

  // 설정 창에 "상대 형광펜 보기" 줄을 끼운다(정보 · 관리 묶음 앞).
  function addPartnerSetting() {
    const info = document.getElementById("set-version");
    const group = info && info.closest(".set-group");
    if (!group || document.getElementById("opt-partner-hl")) return;
    const g = document.createElement("div");
    g.className = "set-group";
    g.innerHTML = '<div class="set-group-h">함께</div>' +
      '<div class="set-toggle" id="opt-partner-hl"><span class="set-label">상대 형광펜 보기 (밑줄)</span>' +
      '<span class="switch' + (partnerOn ? " on" : "") + '"><span class="knob"></span></span></div>' +
      '<p class="set-note">상대가 칠한 형광펜을 본문에 밑줄로 보여 줍니다. 이 기기에만 기억합니다.' +
      (HL_OK ? "" : " (이 브라우저는 밑줄 표시를 지원하지 않습니다)") + "</p>";
    g.querySelector("#opt-partner-hl").addEventListener("click", function () {
      partnerOn = !partnerOn;
      this.querySelector(".switch").classList.toggle("on", partnerOn);
      try { localStorage.setItem("bc-partner-hl", partnerOn ? "1" : "0"); } catch (_) {}
      schedule();
    });
    group.parentNode.insertBefore(g, group);
  }

  // 화면이 바뀔 때마다(장 이동 · 다시 그리기 · 메뉴) 잠깐 기다렸다가 한 번에 얹는다.
  let timer = 0;
  function schedule() { clearTimeout(timer); timer = setTimeout(refresh, 120); }
  function refresh() {
    if (!window.BC || !BC.CardManager) return;
    const cards = [];
    document.querySelectorAll('.mcard[data-type="bible"]').forEach(function (sec) {
      const hit = bibleCardOf(sec);
      if (hit && hit.card.book && hit.card.chapter) cards.push(hit);
    });
    cards.forEach(function (x) { decorateShared(x.sec, x.card); });
    paintPartner(cards);
  }
  new MutationObserver(function (muts) {
    for (const m of muts) {
      for (const n of m.addedNodes) {
        if (n.nodeType === 1 && n.classList.contains("ctx-menu")) addShareItem(n);
      }
    }
    schedule();
  }).observe(document.documentElement, { childList: true, subtree: true });
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") { postCache.clear(); hlCache.clear(); schedule(); }
  });
  document.addEventListener("DOMContentLoaded", addPartnerSetting);

  document.addEventListener("DOMContentLoaded", function () {
    goFromHash();
    const logo = document.querySelector(".rail .logo-tile");
    if (logo) {
      logo.title = "홈으로";
      logo.style.cursor = "pointer";
      logo.addEventListener("click", function () { location.href = "./"; });
    }
    fetch("auth/me", { credentials: "same-origin" })
      .then(function (r) { if (r.status === 401) toLogin(); return r.ok ? r.json() : null; })
      .then(function (me) { if (me) addLogoutButton(me); })
      .catch(function () {});
  });
})();
