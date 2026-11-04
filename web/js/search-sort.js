// BibleClip — 검색 결과 정렬 · 필터 (docs/SEARCH_SORT_PLAN.md).
//
// 검색은 걸린 절 전부를 정확도(BM25)순으로 받아 오고, 정렬·필터는 여기서 화면 없이
// 계산한다 — 다시 검색하지 않으니 누르는 즉시 바뀌고, 상위 200개 안에서만의 "성경순"
// "신약만"이 되는 일이 없다. DOM 을 건드리지 않아 node 에서 그대로 시험된다
// (tests/test_search_sort.js).
//
// 책 번호는 MyBible 번호: 창 10 … 말 460, 마 470 … 계 730. 외경(170 토빗 등)은 "그 밖".
"use strict";

window.SearchSort = (() => {

  const SORTS = ["rank", "bible", "freq", "short", "orig"];

  // 묶음 — 화면 순서대로. books = 그 묶음에 드는 번호.
  const range = (a, b) => { const out = []; for (let n = a; n <= b; n += 10) out.push(n); return out; };
  const GROUPS = [
    { key: "law",      books: range(10, 50) },
    { key: "history",  books: [...range(60, 160), 190] },
    { key: "poetry",   books: range(220, 260) },
    { key: "major",    books: [290, 300, 310, 330, 340] },
    { key: "minor",    books: range(350, 460) },
    { key: "gospel",   books: range(470, 500) },
    { key: "acts",     books: [510] },
    { key: "pauline",  books: range(520, 640) },
    { key: "general",  books: range(650, 720) },
    { key: "prophecy", books: [730] },
  ];
  const GROUP_OF = new Map();
  GROUPS.forEach((g) => g.books.forEach((b) => GROUP_OF.set(b, g.key)));
  // 개신교 66권 — 분포 막대의 칸.
  const CANON = GROUPS.flatMap((g) => g.books);

  const isNT = (book) => book >= 470;
  const groupOf = (book) => GROUP_OF.get(book) || "other";

  const escRx = (s) => String(s).replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  // 화면의 노란 강조(search-notes.js highlightHtml)와 같은 규칙: 대소문자 무시, 긴 단어 우선,
  // 겹치지 않게. 그래서 "몇 번 나왔나"가 눈에 보이는 강조 개수와 같다.
  function counter(terms) {
    const parts = [...new Set(terms.filter(Boolean))].sort((a, b) => b.length - a.length).map(escRx);
    if (!parts.length) return () => 0;
    const re = new RegExp(parts.join("|"), "gi");
    return (text) => { const m = text.match(re); return m ? m.length : 0; };
  }

  /**
   * 검색 응답 → 정렬·필터용 항목(정확도순). 검색어 하나 = 그 단어 + 유의어 묶음.
   *   rank   엔진 순서(0 = 정확도 1위)
   *   terms  검색어 중 그 절에 나온 개수        count  검색어(유의어 포함)가 나온 횟수
   *   orig   유의어가 아니라 원래 단어로 나온 검색어 개수        len  글자 수
   */
  function analyze(res) {
    const tokens = (res && res.matched_tokens) || [];
    const exp = (res && res.expanded) || {};
    const groups = tokens.map((t) => ({ all: counter([t, ...(exp[t] || [])]), own: counter([t]) }));
    return ((res && res.hits) || []).map((h, rank) => {
      const text = h.text || "";
      let terms = 0, count = 0, orig = 0;
      for (const g of groups) {
        const n = g.all(text);
        if (n) { terms++; count += n; if (g.own(text)) orig++; }
      }
      return { rank, book: h.book, chapter: h.chapter, verse: h.verse, short: h.short,
               text, len: text.length, terms, count, orig };
    });
  }

  const byRank = (a, b) => a.rank - b.rank;
  const byBible = (a, b) => (a.book - b.book) || (a.chapter - b.chapter) || (a.verse - b.verse);
  const COMPARE = {
    rank: byRank,
    bible: byBible,
    freq: (a, b) => (b.terms - a.terms) || (b.count - a.count) || byRank(a, b),
    short: (a, b) => (a.len - b.len) || byRank(a, b),
    orig: (a, b) => (b.orig - a.orig) || byRank(a, b),
  };

  /** 새 배열(원본은 정확도순 그대로). 모르는 값 = 정확도순. */
  function sort(items, key) {
    return items.slice().sort(COMPARE[key] || byRank);
  }

  /** 범위: "all" · "ot" · "nt" · "g:<묶음>" · "b:<책 번호>". 모르는 값 = 전체. */
  function inScope(item, scope) {
    if (!scope || scope === "all") return true;
    if (scope === "ot") return !isNT(item.book);
    if (scope === "nt") return isNT(item.book);
    if (scope.startsWith("g:")) return groupOf(item.book) === scope.slice(2);
    if (scope.startsWith("b:")) return item.book === Number(scope.slice(2));
    return true;
  }
  function filter(items, scope) {
    return items.filter((it) => inScope(it, scope));
  }

  /**
   * 메뉴·버튼·막대용 건수. groups 는 결과가 있는 것만 화면 순서로, books 는 그 안에서
   * 성경 순서로({book, short, count}). byBook = Map(책 → 건수).
   */
  function summary(items) {
    const byBook = new Map(), shortOf = new Map();
    let ot = 0, nt = 0;
    for (const it of items) {
      byBook.set(it.book, (byBook.get(it.book) || 0) + 1);
      if (!shortOf.has(it.book)) shortOf.set(it.book, it.short);
      if (isNT(it.book)) nt++; else ot++;
    }
    const keys = [...GROUPS.map((g) => g.key), "other"];
    const groups = keys.map((key) => {
      const books = [...byBook.keys()].filter((b) => groupOf(b) === key).sort((a, b) => a - b)
        .map((b) => ({ book: b, short: shortOf.get(b), count: byBook.get(b) }));
      return { key, books, count: books.reduce((s, b) => s + b.count, 0) };
    }).filter((g) => g.count);
    return { total: items.length, ot, nt, groups, byBook };
  }

  return { SORTS, GROUPS, CANON, isNT, groupOf, analyze, sort, filter, inScope, summary };
})();
