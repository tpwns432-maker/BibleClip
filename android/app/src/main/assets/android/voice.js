// BibleClip Android — 말로 구절 찾기.
// 마이크 버튼 → 안드로이드 음성 입력(Bridge.kt voice_input) → 들린 문장 후보들을
// 참조 파서가 읽는 꼴("요한복음 3:16-18")로 다듬어, 구절이면 그리로 가고 아니면
// 키워드 검색. MainActivity 가 mobile.js 다음에 넣는다.
(function () {
  "use strict";

  // ---- 들린 말 → 참조 문자열 ----
  // 음성 인식은 "요한복음 3장 16절"처럼 숫자로 주는 게 보통이지만 가끔 "삼 장 십육 절",
  // "요한 복음", "요한일서", "1절에서 3절까지"처럼 준다. 파서는 "장 절" 꼴의 범위를
  // 못 읽고(첫 절만), 띄어 쓴 책 이름·한글 숫자도 못 읽는다 — 여기서 메운다.
  const KO_DIGIT = { 영: 0, 공: 0, 일: 1, 이: 2, 삼: 3, 사: 4, 오: 5, 육: 6, 륙: 6, 칠: 7, 팔: 8, 구: 9 };

  function koNumber(s) {
    let total = 0, cur = 0;
    for (const ch of s) {
      if (ch === "백") { total += (cur || 1) * 100; cur = 0; }
      else if (ch === "십") { total += (cur || 1) * 10; cur = 0; }
      else if (ch in KO_DIGIT) cur = KO_DIGIT[ch];
      else return null;
    }
    return total + cur;
  }

  const EN_ORDINAL = { first: 1, second: 2, third: 3, i: 1, ii: 2, iii: 3 };
  const UNIT = "(?:장|편|절)";

  function spokenRef(text) {
    let s = String(text || "").trim()
      .replace(/[.,!?。]+$/g, "")
      // 끝에 붙는 부탁 말: "…으로 가 줘", "… 찾아 줘", "… 펴 줘", "… 보여 줘"
      .replace(/\s*(?:(?:으로|로)\s*)?(?:가\s*줘|가자|이동(?:해\s*줘)?|찾아\s*줘|찾기|펴\s*줘|펼쳐\s*줘|열어\s*줘|보여\s*줘|읽어\s*줘)\s*$/, "")
      .replace(/\s*(?:말씀|본문)\s*$/, "");
    // 한글 숫자 + 장/편/절 → 아라비아 숫자 ("삼 장 십육 절" → "3장 16절")
    s = s.replace(new RegExp("([영공일이삼사오육륙칠팔구십백]+)\\s*(?=" + UNIT + ")", "g"),
      (m, n) => { const v = koNumber(n); return v ? String(v) : m; });
    // 요한일서 → 요한1서 (베드로·디모데 등은 전후서라 해당 없음)
    s = s.replace(/요한\s*(일|이|삼)\s*서/, (m, n) => "요한" + KO_DIGIT[n] + "서");
    // English: "first John" → "1 John", "chapter 3 verse 16" → "3:16"
    s = s.replace(/^(first|second|third|i{1,3})\s+(?=[a-z])/i, (m, n) => EN_ORDINAL[n.toLowerCase()] + " ");
    s = s.replace(/\bchapter\s+(\d+)/i, "$1").replace(/(\d+)\s*(?:,\s*)?verses?\s+(\d+)/i, "$1:$2")
      .replace(/(\d+)\s+(?:to|through|thru)\s+(\d+)\s*$/i, "$1-$2");

    // 책 이름 + 숫자들. 책 이름 안의 띄어쓰기는 붙인다("요한 복음" → "요한복음").
    // 장 뒤 절: "3장 16절" · "3장16절" · "3:16" · "3 16"(영어 인식이 콜론을 빼먹을 때)
    const m = /^(\d?\s*[^\d:]+?(?:[1-3]서)?)\s*(\d+)\s*(?:(?:장|편)\s*(?:(\d+)\s*절?)?|[:\s]\s*(\d+)\s*절?)?\s*(?:(?:에서부터|에서|부터|~|-|–)\s*(\d+)\s*절?)?\s*(?:까지)?\s*$/.exec(s);
    if (!m) return s;
    let book = m[1].trim();
    if (/[가-힣]/.test(book)) book = book.replace(/\s+/g, "");
    const ch = m[2], v1 = m[3] || m[4], v2 = m[5];
    let out = book + " " + ch;
    if (v1) out += ":" + v1 + (v2 && +v2 > +v1 ? "-" + v2 : "");
    return out;
  }

  window.BibleClipVoice = { spokenRef, koNumber };
  if (typeof document === "undefined" || !window.BibleClipNative) return;   // node 시험

  // ---- 버튼과 흐름 ----
  const MIC = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5 11a7 7 0 0 0 14 0"/><path d="M12 18v3"/></svg>';
  const t = (k, fb) => { try { const v = I18N.t(k); return v && v !== k ? v : fb; } catch (_) { return fb; } };
  let busy = false;

  async function listen() {
    if (busy) return;
    const BC = window.BC || {};
    if (!BC.api || !BC.runSearch) return;
    busy = true;
    try {
      const lang = (I18N.getLang && I18N.getLang()) === "en" ? "en-US" : "ko-KR";
      const heard = await BC.api().voice_input(lang, t("voice.prompt", "구절을 말씀하세요 — 예: 요한복음 3장 16절"));
      if (heard && heard.error) { toastMsg(t("voice.unavailable", "이 휴대폰에서는 음성 입력을 쓸 수 없습니다")); return; }
      const list = (Array.isArray(heard) ? heard : []).filter((x) => typeof x === "string" && x.trim());
      if (!list.length) return;   // 취소했거나 못 알아들음 — 음성 창이 이미 알렸다
      // 후보마다 다듬은 꼴 → 그대로의 꼴 순으로 참조인지 본다. 첫 참조로 간다.
      for (const raw of list) {
        for (const q of [spokenRef(raw), raw.trim()]) {
          let ref = null;
          try { ref = await BC.api().resolve_reference(q); } catch (_) {}
          if (ref) { BC.runSearch(q); return; }   // runSearch 가 본문으로 가고 알림까지 띄운다
        }
      }
      // 구절이 아니면 첫 후보로 키워드 검색
      const kw = spokenRef(list[0]);
      if (BC.showView) await BC.showView("search");
      BC.runSearch(kw);
    } finally {
      busy = false;
    }
  }

  function toastMsg(msg) {
    const wrap = document.getElementById("toast-wrap");
    if (!wrap) return;
    const el = document.createElement("div");
    el.className = "toast";
    el.textContent = msg;
    wrap.appendChild(el);
    setTimeout(() => { el.classList.add("fade"); setTimeout(() => el.remove(), 320); }, 2400);
  }

  function makeButton(id, cls) {
    const b = document.createElement("span");
    b.id = id;
    b.className = cls;
    b.setAttribute("role", "button");
    b.setAttribute("data-i18n-title", "voice.title");
    b.title = t("voice.title", "말로 구절 찾기");
    b.innerHTML = MIC;
    b.addEventListener("click", listen);
    return b;
  }

  function start() {
    // 본문 화면: 맨 윗줄 맨 앞(역본 칩 앞). 검색 화면: 입력칸 바로 뒤.
    const row = document.getElementById("viewer-controls");
    if (row && !document.getElementById("voice-viewer")) row.insertBefore(makeButton("voice-viewer", "pill voice-mic"), row.firstChild);
    const input = document.getElementById("search-input");
    if (input && !document.getElementById("voice-search")) input.insertAdjacentElement("afterend", makeButton("voice-search", "pill voice-mic"));
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", start);
  else start();
})();
