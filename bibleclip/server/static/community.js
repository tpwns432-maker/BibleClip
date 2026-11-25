// BibleClip 웹판 — 커뮤니티 화면(docs/WEB_PLAN.md "커뮤니티").
// 한 페이지 안에서 주소의 # 뒷부분으로 화면을 바꾼다:
//   #/            전체 글          #/t/<주제>          주제의 글
//   #/s/<종류>/<제목>  같은 설교 · 책 모아 보기
//   #/p/<글>       글 + 댓글        #/new[/<주제>]  글쓰기   #/edit/<글>  글 고치기
//   #/topic/new   주제 만들기      #/topic/<주제>  주제 고치기
// 글은 Site.renderRich 로만 그린다(HTML 해석 안 함 — 구절 · 웹 주소만 링크, 쓴 구절은 본문 카드).
(function () {
  "use strict";

  const { capi, esc, timeTag, renderRich } = Site;
  const $ = (id) => document.getElementById(id);
  const view = $("view");

  const SOURCE = {
    sermon: { ico: "🎤", label: "설교", fields: [
      ["title", "설교 제목", "text", "wide"], ["by", "설교자", "text"], ["date", "날짜", "date"],
      ["url", "링크(영상 등)", "url", "wide"]] },
    book: { ico: "📘", label: "책", fields: [
      ["title", "책 제목", "text", "wide"], ["by", "저자", "text"], ["part", "읽은 부분(예: 3장, 45~80쪽)", "text"]] },
  };
  const SORTS = [["activity", "최근 활동"], ["new", "새 글"], ["likes", "공감순"]];
  const ERR = {
    exists: "같은 이름의 주제가 이미 있습니다.",
    notempty: "글이 있는 주제는 지울 수 없습니다.",
    forbidden: "내가 쓴 것만 고치거나 지울 수 있습니다.",
    notfound: "찾을 수 없습니다. 지워졌을 수 있어요.",
    invalid: "입력한 내용을 확인해 주세요.",
  };

  let me = null;
  let topics = [];
  let sort = "activity";
  try { sort = localStorage.getItem("bc-community-sort") || sort; } catch (_) {}

  // ---- 작은 도움 ----

  let toastTimer = 0;
  function toast(msg) {
    let t = document.querySelector(".toast");
    if (!t) { t = document.createElement("div"); t.className = "toast"; document.body.appendChild(t); }
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => { t.hidden = true; }, 2600);
  }
  function fail(e) {
    if (e && e.message === "login") return;
    toast(ERR[e && e.code] || "잠시 뒤에 다시 해 주세요.");
  }
  const topicById = (id) => topics.find((t) => t.id === id);

  function sourceLine(s) {
    if (!s) return "";
    const k = SOURCE[s.kind];
    const sub = [s.by, s.kind === "sermon" ? s.date : s.part].filter(Boolean).join(" · ");
    return `${k.ico} ${esc(s.title)}${sub ? " — " + esc(sub) : ""}`;
  }
  function sourceHref(s) {
    return "#/s/" + s.kind + "/" + encodeURIComponent(s.title);
  }

  // 글에 단 구절(성경 화면에서 "함께 쓰기") — 링크와 본문 인용.
  function verseHref(v) {
    const vs = [];
    for (let n = v.verse; n <= v.verse_end; n++) vs.push(n);
    return Site.goHref({ book: v.book, chapter: v.chapter, verses: vs });
  }
  function quoteHtml(vt) {
    if (!vt || !vt.verses || !vt.verses.length) return "";
    return vt.verses.map((x) => `<sup>${x.n}</sup>${esc(x.text)}`).join(" ") +
      `<cite>${esc(vt.version)}</cite>`;
  }
  async function getJson(path) {
    const r = await fetch(path, { credentials: "same-origin" });
    if (r.status === 401) { Site.toLogin(); throw new Error("login"); }
    if (!r.ok) { const e = new Error("HTTP " + r.status); e.code = "notfound"; throw e; }
    return r.json();
  }
  // 성경읽기 체크 글의 칩: "✅ 1일째 · 창 1–3장" — 누르면 그 범위의 성경으로.
  function readingChip(rd) {
    return rd ? `<a class="src-chip reading" href="bible#go=${rd.book}.${rd.chapter}" title="성경에서 읽기">✅ 성경읽기 ${rd.day}일째 · ${esc(rd.label)}</a>` : "";
  }

  function parseVerseParam(q) {
    const m = /^(\d+)\.(\d+)\.(\d+)(?:-(\d+))?$/.exec(q || "");
    if (!m) return null;
    const v = { book: +m[1], chapter: +m[2], verse: +m[3], verse_end: +(m[4] || m[3]) };
    if (v.verse_end < v.verse) v.verse_end = v.verse;
    return v;
  }

  // ---- 주제 목록(왼쪽, 휴대폰에선 위쪽 칩) ----

  async function loadTopics() {
    topics = await capi("topics");
    renderTopics();
  }
  function renderTopics(activeId) {
    const total = topics.reduce((n, t) => n + t.unread, 0);
    const link = (href, name, n, on) =>
      `<a class="topic-link${on ? " on" : ""}" href="${href}">${esc(name)}` +
      `${n ? `<span class="n new">${n}</span>` : ""}</a>`;
    $("topics").innerHTML = "<h2>주제</h2>" +
      link("#/", "전체 글", total, activeId === "all") +
      topics.map((t) => link("#/t/" + t.id, t.name, t.unread, activeId === t.id)).join("") +
      `<a class="topic-add" href="#/topic/new">+ 주제 만들기</a>` +
      `<a class="topic-link${activeId === "reading" ? " on" : ""}" href="#/reading">📅 성경읽기 기록</a>`;
  }

  // ---- 글 목록 ----

  function postItem(p) {
    const title = p.deleted ? '<span class="deleted">지운 글입니다</span>' : esc(p.title);
    return `<article class="post-item" data-pid="${p.id}">
      <div class="like-col">
        <button class="heart${p.liked ? " on" : ""}" data-act="like-post" data-id="${p.id}"
          ${p.deleted ? "disabled" : ""} title="${esc(p.likers.join(", ") || "공감")}">♥</button>
        <span class="cnt">${p.likes || ""}</span>
      </div>
      <div class="pi-main">
        <div class="pi-meta"><a class="topic" href="#/t/${p.topic.id}">${esc(p.topic.name)}</a>
          · ${esc(p.author.name)} · ${timeTag(p.created_at)}${p.is_new ? ' <span class="new">새</span>' : ""}</div>
        <a class="pi-title" href="#/p/${p.id}">${title}</a>
        ${readingChip(p.reading)}
        ${p.verse ? `<a class="src-chip verse" href="${esc(verseHref(p.verse))}" title="성경에서 열기">📖 ${esc(p.verse.label)}</a>` : ""}
        ${p.source ? `<a class="src-chip" href="${sourceHref(p.source)}" title="같은 ${SOURCE[p.source.kind].label}의 글 모아 보기">${sourceLine(p.source)}</a>` : ""}
        ${p.snippet ? `<p class="pi-snippet">${esc(p.snippet)}</p>` : ""}
        <div class="pi-foot"><a href="#/p/${p.id}">💬 댓글 ${p.comments}</a>
          ${p.new_comments ? `<span class="new">새 댓글 ${p.new_comments}</span>` : ""}</div>
      </div>
    </article>`;
  }

  async function showList(filter) {
    // filter: {topic_id} | {source_kind, source_title} | {}
    const t = filter.topic_id ? topicById(filter.topic_id) : null;
    if (filter.topic_id && !t) { view.innerHTML = `<div class="empty">${ERR.notfound}</div>`; return; }
    renderTopics(t ? t.id : (filter.source_kind ? null : "all"));
    let head;
    if (t) {
      head = `<div><h1>${esc(t.name)}</h1>${t.description ? `<p class="muted">${esc(t.description)}</p>` : ""}</div>
        <div class="acts"><a class="btn" href="#/topic/${t.id}" title="주제 고치기">✎</a>
        <a class="btn primary" href="#/new/${t.id}">글쓰기</a></div>`;
    } else if (filter.source_kind) {
      const k = SOURCE[filter.source_kind];
      head = `<div><h1>${k.ico} ${esc(filter.source_title)}</h1>
        <p class="muted">같은 ${k.label}에 대한 글 모아 보기 · <a href="#/">전체 글로</a></p></div>`;
    } else {
      head = `<div><h1>전체 글</h1></div><div class="acts"><a class="btn primary" href="#/new">글쓰기</a></div>`;
    }
    view.innerHTML = `<div class="view-head">${head}</div>
      <div class="toolbar"><div class="seg" id="sort">${SORTS.map(([k, l]) =>
        `<button type="button" data-sort="${k}" class="${k === sort ? "on" : ""}">${l}</button>`).join("")}</div></div>
      <div class="post-list" id="list"><div class="empty">불러오는 중…</div></div>`;
    $("sort").addEventListener("click", (e) => {
      const b = e.target.closest("[data-sort]");
      if (!b) return;
      sort = b.dataset.sort;
      try { localStorage.setItem("bc-community-sort", sort); } catch (_) {}
      showList(filter);
    });
    await loadPage(filter, 0);
  }

  async function loadPage(filter, offset) {
    let r;
    try { r = await capi("posts", Object.assign({ sort, offset, limit: 30 }, filter)); }
    catch (e) { fail(e); return; }
    const list = $("list");
    if (!list) return;
    if (offset === 0) list.innerHTML = "";
    const old = list.querySelector(".more");
    if (old) old.remove();
    if (!r.posts.length && offset === 0) {
      list.innerHTML = `<div class="empty">아직 글이 없습니다.${filter.source_kind ? "" : " 첫 글을 남겨 보세요."}</div>`;
      return;
    }
    list.insertAdjacentHTML("beforeend", r.posts.map(postItem).join(""));
    if (r.more) {
      const b = document.createElement("button");
      b.className = "btn more";
      b.textContent = "더 보기";
      b.onclick = () => loadPage(filter, offset + r.posts.length);
      list.appendChild(b);
    }
  }

  // ---- 글 보기 + 댓글 ----

  function commentTree(list) {
    const kids = new Map();
    for (const c of list) {
      const k = c.parent_id || 0;
      if (!kids.has(k)) kids.set(k, []);
      kids.get(k).push(c);
    }
    const node = (c, depth) => {
      const children = kids.get(c.id) || [];
      return `<div class="c" id="c${c.id}" data-cid="${c.id}">
        <div class="c-meta"><b>${esc(c.author.name)}</b> · ${timeTag(c.created_at)}
          ${c.edited_at && !c.deleted ? " · 고침" : ""}${c.is_new ? ' <span class="new">새</span>' : ""}</div>
        <div class="c-body">${c.deleted ? '<span class="deleted">지운 댓글입니다</span>' : renderRich(c.body, c.refs)}</div>
        ${c.deleted ? "" : `<div class="c-acts">
          <button class="heart${c.liked ? " on" : ""}" data-act="like-comment" data-id="${c.id}"
            title="${esc(c.likers.join(", ") || "공감")}">♥</button><span class="cnt">${c.likes || ""}</span>
          <button class="link-btn" data-act="reply" data-id="${c.id}">답글</button>
          ${c.mine ? `<button class="link-btn" data-act="edit-comment" data-id="${c.id}">고치기</button>
          <button class="link-btn" data-act="del-comment" data-id="${c.id}">지우기</button>` : ""}
        </div>`}
        <div class="c-slot"></div>
        ${children.length ? `<div class="c-children${depth >= 4 ? " flat" : ""}">${
          children.map((x) => node(x, depth + 1)).join("")}</div>` : ""}
      </div>`;
    };
    return (kids.get(0) || []).map((c) => node(c, 1)).join("");
  }

  let current = null;   // 지금 보는 글(댓글 고치기 등에 씀)

  async function showPost(id, focusComment) {
    let p;
    try { p = await capi("post", { id }); }
    catch (e) { view.innerHTML = `<div class="empty">${ERR[e.code] || "불러오지 못했습니다."}</div>`; return; }
    current = p;
    renderTopics(p.topic.id);
    const src = p.source ? `<a class="src-card" href="${sourceHref(p.source)}" title="같은 ${SOURCE[p.source.kind].label}의 글 모아 보기">
        <span class="ico">${SOURCE[p.source.kind].ico}</span>
        <span><span class="t">${esc(p.source.title)}</span><br><span class="sub">${esc([p.source.by,
          p.source.kind === "sermon" ? p.source.date : p.source.part].filter(Boolean).join(" · "))}</span></span></a>` : "";
    const link = p.source && p.source.url ? `<p><a href="${esc(p.source.url)}" target="_blank" rel="noopener noreferrer">🔗 ${esc(p.source.url)}</a></p>` : "";
    view.innerHTML = `<a class="back" href="#/t/${p.topic.id}">← ${esc(p.topic.name)}</a>
      <article class="post-full">
        <div class="pi-meta"><span class="topic">${esc(p.topic.name)}</span> · ${esc(p.author.name)} ·
          ${timeTag(p.created_at)}${p.edited_at ? " · 고침" : ""}</div>
        ${p.deleted ? '<h1 class="deleted">지운 글입니다</h1>' : `<h1>${esc(p.title)}</h1>${p.reading ? `<p>${readingChip(p.reading)}</p>` : ""}${p.verse ? `
        <div class="verse-quote"><a class="vq-label" href="${esc(verseHref(p.verse))}" title="성경에서 열기">📖 ${esc(p.verse.label)}</a>
          ${p.verse_text ? `<blockquote>${quoteHtml(p.verse_text)}</blockquote>` : ""}</div>` : ""}${src}${link}
        <div class="body">${renderRich(p.body, p.refs)}</div>
        <div class="post-acts">
          <button class="like-btn${p.liked ? " on" : ""}" data-act="like-post" data-id="${p.id}">♥ 공감 <span class="cnt">${p.likes || ""}</span></button>
          <span class="likers">${esc(p.likers.join(", "))}</span>
          <span class="spacer"></span>
          ${p.mine ? `<a class="btn" href="#/edit/${p.id}">고치기</a>
          <button class="btn danger" data-act="del-post" data-id="${p.id}">지우기</button>` : ""}
        </div>`}
      </article>
      <section class="comments">
        <h2>댓글 ${p.comment_list.filter((c) => !c.deleted).length}</h2>
        ${p.deleted ? "" : `<form class="c-form" id="c-new">
          <textarea name="body" maxlength="5000" placeholder="댓글을 남겨 주세요" required></textarea>
          <div class="row"><button class="btn primary" type="submit">댓글 달기</button></div></form>`}
        <div class="c-tree">${commentTree(p.comment_list) || ""}</div>
      </section>`;
    const f = $("c-new");
    if (f) f.addEventListener("submit", (e) => {
      e.preventDefault();
      submitComment({ post_id: p.id }, f.body.value);
    });
    if (focusComment) {
      const el = $("c" + focusComment);
      if (el) { el.scrollIntoView({ block: "center" }); el.classList.add("flash"); }
    }
    loadTopics().then(() => renderTopics(p.topic.id)).catch(() => {});   // 읽음 → 새 글 수 갱신
  }

  async function submitComment(args, body) {
    if (!body.trim()) return;
    let r;
    try { r = await capi("comment_save", Object.assign({ body }, args)); }
    catch (e) { fail(e); return; }
    await showPost(current.id, r.id);
  }

  function commentForm(slot, value, onSubmit, label) {
    slot.innerHTML = `<form class="c-form"><textarea name="body" maxlength="5000" required></textarea>
      <div class="row"><button class="btn" type="button" data-act="cancel-form">취소</button>
      <button class="btn primary" type="submit">${label}</button></div></form>`;
    const f = slot.querySelector("form");
    f.body.value = value || "";
    f.body.focus();
    f.addEventListener("submit", (e) => { e.preventDefault(); onSubmit(f.body.value); });
  }

  // ---- 글쓰기 · 고치기 ----

  const DRAFT = "bc-community-draft";
  function readDraft() { try { return JSON.parse(localStorage.getItem(DRAFT) || "null"); } catch (_) { return null; } }
  function writeDraft(d) { try { d ? localStorage.setItem(DRAFT, JSON.stringify(d)) : localStorage.removeItem(DRAFT); } catch (_) {} }

  async function showCompose(topicId, editId, verseParam, readingParam) {
    let post = null;
    if (editId) {
      try { post = await capi("post", { id: editId }); } catch (e) { fail(e); return; }
      if (!post.mine || post.deleted) { view.innerHTML = `<div class="empty">${ERR.forbidden}</div>`; return; }
    }
    // 성경읽기 체크(홈 · 텔레그램 · 기록 화면에서 "✍️ 성경읽기 체크"): 그날 범위가 달린 글쓰기.
    let reading = null;
    if (!editId && /^\d{4}-\d{2}-\d{2}$/.test(readingParam || "")) {
      try { reading = await getJson("rc/day?date=" + readingParam); } catch (_) { reading = null; }
      if (!reading) { toast("그날은 성경읽기 계획에 없어요."); }
      else if (!topicId) { try { topicId = (await capi("reading_topic")).id; } catch (_) {} }
    }
    const shownReading = reading || (post && post.reading) || null;
    const fromBible = parseVerseParam(verseParam);       // 성경 화면에서 "함께 쓰기"로 왔다
    const draft = editId || fromBible || reading ? null : readDraft();
    const v = post || draft || {};
    let verse = post ? post.verse : (fromBible || (draft && draft.verse) || null);
    if (fromBible && !topicId) {
      try { topicId = (await capi("default_topic")).id; } catch (_) {}
    }
    const tid = (post && post.topic.id) || topicId || (draft && draft.topic_id) || (topics[0] && topics[0].id);
    renderTopics(tid);
    const src = v.source || null;
    let kind = src ? src.kind : ((topicById(tid) || {}).source_kind || "");
    let kindTouched = !!src;
    view.innerHTML = `<div class="view-head"><div><h1>${editId ? "글 고치기" : "글쓰기"}</h1></div></div>
      <form class="form" id="compose">
        <label>주제<select name="topic">${topics.map((t) =>
          `<option value="${t.id}"${t.id === tid ? " selected" : ""}>${esc(t.name)}</option>`).join("")}</select></label>
        ${shownReading ? `<div class="reading-box">${readingChip(shownReading)}
          <p class="hint">읽고 든 생각을 짧게 남기면 그날 성경읽기 체크가 됩니다.</p></div>` : ""}
        <div class="verse-box" id="vbox" hidden></div>
        <div class="vb-attach" id="vattach" hidden>
          <input type="text" id="va-text" maxlength="60" enterkeyhint="done" autocomplete="off"
            placeholder="📖 구절 달기 — 예: 창 1:28, 요 3:16-18">
          <button type="button" class="btn" id="va-go">달기</button></div>
        <label>제목<input type="text" name="title" maxlength="200" required></label>
        <fieldset><legend>무엇에 대한 감상인가요? (선택)</legend>
          <div class="seg" id="kind">${[["", "없음"], ["sermon", "🎤 설교"], ["book", "📘 책"]].map(([k, l]) =>
            `<button type="button" data-kind="${k}">${l}</button>`).join("")}</div>
          ${Object.entries(SOURCE).map(([k, d]) => `<div class="src-fields" data-for="${k}">${d.fields.map(([f, l, type, wide]) =>
            `<label class="${wide || ""}">${l}<input type="${type}" name="${k}-${f}"></label>`).join("")}</div>`).join("")}
        </fieldset>
        <label>내용<textarea name="body" rows="12" maxlength="20000" required></textarea></label>
        <p class="hint" id="ref-hint"></p>
        <div class="form-acts"><a class="btn" href="${editId ? "#/p/" + editId : "#/" + (tid ? "t/" + tid : "")}">취소</a>
          <button class="btn primary" type="submit">${editId ? "저장" : "올리기"}</button></div>
      </form>`;
    const f = $("compose");
    f.title.value = v.title || (reading ? `${reading.day}일째 · ${reading.label}` : "");
    f.body.value = v.body || "";
    if (shownReading) f.body.placeholder = "오늘 읽은 부분에서 마음에 남은 것을 짧게 적어 주세요.";
    if (src) for (const [fld] of SOURCE[src.kind].fields) f[src.kind + "-" + fld].value = src[fld] || "";
    const showKind = () => {
      f.querySelectorAll("#kind button").forEach((b) => b.classList.toggle("on", b.dataset.kind === kind));
      f.querySelectorAll(".src-fields").forEach((d) => { d.hidden = d.dataset.for !== kind; });
    };
    showKind();
    $("kind").addEventListener("click", (e) => {
      const b = e.target.closest("[data-kind]");
      if (!b) return;
      kind = b.dataset.kind;
      kindTouched = true;
      showKind();
    });
    f.topic.addEventListener("change", () => {
      if (!kindTouched) { kind = (topicById(+f.topic.value) || {}).source_kind || ""; showKind(); }
    });
    const collect = () => {
      const s = kind ? Object.fromEntries(SOURCE[kind].fields.map(([fld]) => [fld, f[kind + "-" + fld].value.trim()])) : null;
      return { topic_id: +f.topic.value, title: f.title.value, body: f.body.value,
               source: s && s.title ? Object.assign({ kind }, s) : null,
               verse: verse ? { book: verse.book, chapter: verse.chapter, verse: verse.verse, verse_end: verse.verse_end } : null,
               ...(reading ? { reading_day: reading.date } : {}) };
    };
    // 구절 상자: 절 범위를 고치면 이름표와 본문을 다시 받아 보여 준다.
    let previewTimer = 0;
    async function previewVerse() {
      const lab = $("vb-label"), txt = $("vb-text");
      if (!verse || !lab) return;
      try {
        const r = await capi("verse_preview", { verse: collect().verse });
        lab.textContent = "📖 " + r.verse.label;
        txt.innerHTML = quoteHtml(r.verse_text) || '<span class="muted">본문을 찾지 못했습니다.</span>';
      } catch (_) {
        lab.textContent = "📖 구절 범위를 확인해 주세요";
        txt.innerHTML = "";
      }
    }
    function renderVerseBox() {
      const box = $("vbox");
      $("vattach").hidden = !!verse;
      if (!verse) { box.hidden = true; box.innerHTML = ""; return; }
      box.hidden = false;
      box.innerHTML = `<div class="vb-head"><b id="vb-label">📖 ${esc(verse.label || "")}</b>
        <span class="vb-range">절 <input type="number" min="1" max="176" id="vb-s" value="${verse.verse}">
        ~ <input type="number" min="1" max="176" id="vb-e" value="${verse.verse_end}"></span>
        <button type="button" class="link-btn" id="vb-del">구절 떼기</button></div>
        <blockquote class="vb-text" id="vb-text"></blockquote>`;
      const onRange = () => {
        const a = +$("vb-s").value, b = +$("vb-e").value;
        if (!a || !b) return;
        verse = Object.assign({}, verse, { verse: Math.min(a, b), verse_end: Math.max(a, b) });
        clearTimeout(previewTimer);
        previewTimer = setTimeout(previewVerse, 250);
        if (!editId) writeDraft(collect());
      };
      $("vb-s").addEventListener("input", onRange);
      $("vb-e").addEventListener("input", onRange);
      $("vb-del").addEventListener("click", () => {
        verse = null;
        renderVerseBox();
        if (!editId) writeDraft(collect());
      });
      previewVerse();
    }
    renderVerseBox();

    // 구절 달기(성경 화면을 거치지 않고 — 휴대폰에서도): "창 1:28" 을 적으면 위 구절 상자로.
    async function attachVerse() {
      const inp = $("va-text");
      const t = inp.value.trim();
      if (!t) { inp.focus(); return; }
      let r;
      try { r = (await capi("refs_preview", { text: t })).refs[0]; } catch (e) { fail(e); return; }
      if (!r) { toast("구절을 알아보지 못했어요. 예: 창 1:28, 요 3:16-18"); return; }
      verse = { book: r.book, chapter: r.chapter, verse: r.verses[0], verse_end: r.verses[r.verses.length - 1], label: r.label };
      inp.value = "";
      renderVerseBox();
      if (!editId) writeDraft(collect());
    }
    $("va-go").addEventListener("click", attachVerse);
    $("va-text").addEventListener("keydown", (e) => {
      if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); attachVerse(); }
    });

    // 내용에 쓴 구절 알려 주기 — 올리면 그 줄 아래에 본문이 함께 보인다.
    const HINT = '"창 1:28", "요한복음 3장 16절"처럼 구절을 쓰면 그 줄 아래에 본문이 함께 보이고, 누르면 성경으로 갑니다.';
    let hintTimer = 0, hintFor = null;
    async function refHint() {
      const t = f.body.value;
      if (t === hintFor) return;
      hintFor = t;
      let refs = [];
      if (t.trim()) { try { refs = (await capi("refs_preview", { text: t })).refs; } catch (_) { refs = []; } }
      if (t !== f.body.value) return;              // 그새 더 썼다
      const labels = [...new Set(refs.map((r) => r.label))];
      $("ref-hint").textContent = labels.length
        ? "📖 " + labels.join(" · ") + " — 올리면 본문이 함께 보여요." : HINT;
    }
    $("ref-hint").textContent = HINT;
    f.body.addEventListener("input", () => { clearTimeout(hintTimer); hintTimer = setTimeout(refHint, 500); });
    if (f.body.value) refHint();

    if (!editId) f.addEventListener("input", () => writeDraft(collect()));
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      const d = collect();
      if (kind && !(d.source && d.source.title)) { toast(SOURCE[kind].label + " 제목을 적거나 '없음'을 골라 주세요."); return; }
      const btn = f.querySelector("button[type=submit]");
      btn.disabled = true;
      try {
        const r = await capi("post_save", editId ? Object.assign({ id: editId }, d) : d);
        if (!editId) writeDraft(null);
        location.hash = "#/p/" + r.id;
      } catch (err) {
        btn.disabled = false;
        fail(err);
      }
    });
  }

  // ---- 주제 만들기 · 고치기 ----

  function showTopicForm(id) {
    const t = id ? topicById(id) : null;
    if (id && !t) { view.innerHTML = `<div class="empty">${ERR.notfound}</div>`; return; }
    renderTopics(t ? t.id : null);
    view.innerHTML = `<div class="view-head"><div><h1>${t ? "주제 고치기" : "주제 만들기"}</h1></div></div>
      <form class="form" id="tform">
        <label>이름<input type="text" name="name" maxlength="30" required></label>
        <label>설명(선택)<input type="text" name="description" maxlength="200"></label>
        <label>이 주제의 글은 보통 무엇에 대한 감상인가요?<select name="kind">
          <option value="">정하지 않음</option><option value="sermon">🎤 설교</option><option value="book">📘 책</option></select></label>
        <div class="form-acts">
          ${t ? `<button class="btn danger left" type="button" id="tdel" ${t.posts ? 'disabled title="글이 있는 주제는 지울 수 없습니다"' : ""}>주제 지우기</button>` : ""}
          <a class="btn" href="${t ? "#/t/" + t.id : "#/"}">취소</a>
          <button class="btn primary" type="submit">저장</button></div>
      </form>`;
    const f = $("tform");
    if (t) { f.name.value = t.name; f.description.value = t.description; f.kind.value = t.source_kind; }
    f.addEventListener("submit", async (e) => {
      e.preventDefault();
      try {
        const r = await capi("topic_save", Object.assign(t ? { id: t.id } : {},
          { name: f.name.value, description: f.description.value, source_kind: f.kind.value }));
        await loadTopics();
        location.hash = "#/t/" + r.id;
      } catch (err) { fail(err); }
    });
    const del = $("tdel");
    if (del) del.addEventListener("click", async () => {
      if (!confirm(`'${t.name}' 주제를 지울까요?`)) return;
      try { await capi("topic_delete", { id: t.id }); await loadTopics(); location.hash = "#/"; }
      catch (err) { fail(err); }
    });
  }

  // ---- 누르기(공감 · 답글 · 고치기 · 지우기) ----

  view.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-act]");
    if (!b) return;
    const id = +b.dataset.id;
    const act = b.dataset.act;
    if (act === "like-post" || act === "like-comment") {
      try {
        const r = await capi("like", { kind: act === "like-post" ? "post" : "comment", id });
        b.classList.toggle("on", r.liked);
        b.title = r.likers.join(", ") || "공감";
        const cnt = b.querySelector(".cnt") || b.nextElementSibling;
        if (cnt && cnt.classList.contains("cnt")) cnt.textContent = r.likes || "";
        const who = b.parentElement.querySelector(".likers");
        if (who) who.textContent = r.likers.join(", ");
      } catch (err) { fail(err); }
    } else if (act === "reply") {
      const slot = b.closest(".c").querySelector(".c-slot");
      commentForm(slot, "", (body) => submitComment({ post_id: current.id, parent_id: id }, body), "답글 달기");
    } else if (act === "edit-comment") {
      const c = current.comment_list.find((x) => x.id === id);
      const slot = b.closest(".c").querySelector(".c-slot");
      commentForm(slot, c ? c.body : "", (body) => submitComment({ id }, body), "저장");
    } else if (act === "cancel-form") {
      b.closest(".c-slot").innerHTML = "";
    } else if (act === "del-comment") {
      if (!confirm("이 댓글을 지울까요?")) return;
      try { await capi("comment_delete", { id }); await showPost(current.id); } catch (err) { fail(err); }
    } else if (act === "del-post") {
      if (!confirm("이 글을 지울까요? 댓글이 있으면 댓글은 남습니다.")) return;
      try {
        await capi("post_delete", { id });
        await loadTopics();
        location.hash = "#/t/" + current.topic.id;
      } catch (err) { fail(err); }
    }
  });

  // ---- 성경읽기 기록: 날짜별로 두 분의 체크 ----

  async function showReadingLog() {
    renderTopics("reading");
    let st;
    try { st = await getJson("rc/status"); } catch (e) { fail(e); return; }
    if (!st.started) {
      view.innerHTML = `<div class="view-head"><div><h1>📅 성경읽기 기록</h1></div></div>
        <div class="empty">성경읽기는 ${esc(st.start)}에 시작해요.</div>`;
      return;
    }
    const users = st.users;
    const WD = "일월화수목금토";
    const dayCell = (iso) => { const d = new Date(iso + "T00:00:00"); return `${d.getMonth() + 1}/${d.getDate()} (${WD[d.getDay()]})`; };
    const cell = (h, u) => {
      const pid = h.done[u.id];
      if (pid) return `<a class="rc-ok" href="#/p/${pid}" title="글 보기">✅</a>`;
      return u.me ? `<a class="rc-write" href="#/new?reading=${h.date}">✍️ 체크</a>` : `<span class="rc-miss">—</span>`;
    };
    view.innerHTML = `<div class="view-head"><div><h1>📅 성경읽기 기록</h1>
        <p class="muted">1년 1독 · ${esc(st.start)} 시작 · 오늘 ${st.today.day}일째. 그날 범위에 대한 짧은 생각을 쓰면 체크예요(지난 날도 나중에 쓸 수 있어요).</p></div>
        <div class="acts">${st.today.done[users[0].id] ? "" : `<a class="btn primary" href="#/new?reading=${st.today.date}">✍️ 오늘 성경읽기 체크</a>`}</div></div>
      <div class="rc-users">${users.map((u) => `<div class="rc-user"><b>${esc(u.name)}${u.me ? " (나)" : ""}</b>
        <span>${u.today ? "✅ 오늘 체크" : "오늘 아직"}</span><span>연속 ${u.streak}일 · ${u.done}/${u.elapsed}일</span></div>`).join("")}</div>
      <table class="rc-table"><thead><tr><th>날짜</th><th>범위</th>${users.map((u) => `<th>${esc(u.name)}</th>`).join("")}</tr></thead>
        <tbody>${st.history.map((h) => `<tr><td>${dayCell(h.date)}<br><small class="muted">${h.day}일째</small></td>
          <td><a href="bible#go=${h.book}.${h.chapter}">${esc(h.label)}</a></td>${users.map((u) => `<td>${cell(h, u)}</td>`).join("")}</tr>`).join("")}</tbody></table>`;
  }

  // ---- 주소(#) → 화면 ----

  async function route() {
    const h = location.hash.replace(/^#\/?/, "");
    const [path, query] = h.split("?");
    const parts = path.split("/").filter(Boolean);
    const q = new URLSearchParams(query || "");
    window.scrollTo(0, 0);
    if (parts[0] === "t" && parts[1]) return showList({ topic_id: +parts[1] });
    if (parts[0] === "s" && SOURCE[parts[1]] && parts[2])
      return showList({ source_kind: parts[1], source_title: decodeURIComponent(parts.slice(2).join("/")) });
    if (parts[0] === "p" && parts[1]) return showPost(+parts[1]);
    if (parts[0] === "new") return showCompose(parts[1] ? +parts[1] : null, null, q.get("verse"), q.get("reading"));
    if (parts[0] === "reading") return showReadingLog();
    if (parts[0] === "edit" && parts[1]) return showCompose(null, +parts[1]);
    if (parts[0] === "topic") return showTopicForm(parts[1] === "new" ? null : +parts[1]);
    return showList({});
  }

  $("logout").addEventListener("click", Site.logout);
  window.addEventListener("hashchange", route);
  (async () => {
    try {
      me = await Site.me();
      $("who").textContent = me.name;
      Site.themeMenu($("theme-btn"), me);
      await loadTopics();
    } catch (e) { fail(e); return; }
    route();
  })();
})();
