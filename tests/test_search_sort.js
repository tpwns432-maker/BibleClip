// 검색 결과 정렬 · 필터 테스트 (docs/SEARCH_SORT_PLAN.md).
//
//   node tests/test_search_sort.js
//
// web/js/search-sort.js 는 DOM 을 건드리지 않으므로 브라우저에서 도는 파일을 그대로 읽어 돌린다.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.window = {};
new Function(fs.readFileSync(path.join(__dirname, "..", "web", "js", "search-sort.js"), "utf8"))();
const S = window.SearchSort;

const refs = (items) => items.map((i) => `${i.book}:${i.chapter}:${i.verse}`);

// 정확도순으로 온 응답 — "이집트" 한 단어, 유의어 애굽.
const egypt = {
  matched_tokens: ["이집트"],
  expanded: { "이집트": ["애굽"] },
  hits: [
    { book: 20, chapter: 1, verse: 1, short: "출", text: "애굽에 내려간 이스라엘 아들들의 이름은 이러하니" },
    { book: 470, chapter: 2, verse: 13, short: "마", text: "애굽으로 피하여 내가 네게 이르기까지 거기 있으라 애굽에서" },
    { book: 10, chapter: 12, verse: 10, short: "창", text: "이집트 애굽 애굽" },
    { book: 300, chapter: 2, verse: 6, short: "렘", text: "이집트로" },
    { book: 730, chapter: 11, verse: 8, short: "계", text: "애굽이라고도 하는 큰 성 길에 있으리니 짧다" },
  ],
};
const items = S.analyze(egypt);

// 세는 법: 유의어까지 센다, 원래 단어는 따로.
assert.deepStrictEqual(items.map((i) => i.count), [1, 2, 3, 1, 1]);
assert.deepStrictEqual(items.map((i) => i.terms), [1, 1, 1, 1, 1]);
assert.deepStrictEqual(items.map((i) => i.orig), [0, 0, 1, 1, 0]);
assert.deepStrictEqual(items.map((i) => i.rank), [0, 1, 2, 3, 4]);

// 정렬 5종. 원본은 건드리지 않는다.
assert.deepStrictEqual(refs(S.sort(items, "rank")), refs(items));
assert.deepStrictEqual(refs(S.sort(items, "bible")),
  ["10:12:10", "20:1:1", "300:2:6", "470:2:13", "730:11:8"]);
assert.deepStrictEqual(refs(S.sort(items, "freq")),               // 3회 · 2회 · 1회(정확도순)
  ["10:12:10", "470:2:13", "20:1:1", "300:2:6", "730:11:8"]);
assert.deepStrictEqual(refs(S.sort(items, "short")).slice(0, 2), ["300:2:6", "10:12:10"]);
assert.deepStrictEqual(refs(S.sort(items, "orig")),               // 원래 단어 → 유의어만(각각 정확도순)
  ["10:12:10", "300:2:6", "20:1:1", "470:2:13", "730:11:8"]);
assert.deepStrictEqual(refs(S.sort(items, "nonsense")), refs(items));
assert.deepStrictEqual(refs(items), ["20:1:1", "470:2:13", "10:12:10", "300:2:6", "730:11:8"]);

// 여러 단어(OR): 포함한 검색어 수 먼저, 그다음 횟수.
const multi = S.analyze({
  matched_tokens: ["사랑", "믿음", "소망"], expanded: {},
  hits: [
    { book: 10, chapter: 1, verse: 1, short: "창", text: "사랑 사랑 사랑 사랑" },
    { book: 530, chapter: 13, verse: 13, short: "고전", text: "믿음 소망 사랑 이 세 가지는 항상 있을 것인데 그 중에 제일은 사랑이라" },
    { book: 520, chapter: 5, verse: 5, short: "롬", text: "소망이 부끄럽게 아니함은 사랑이" },
  ],
});
assert.deepStrictEqual(multi.map((i) => [i.terms, i.count]), [[1, 4], [3, 4], [2, 2]]);
assert.deepStrictEqual(refs(S.sort(multi, "freq")), ["530:13:13", "520:5:5", "10:1:1"]);

// 영어는 대소문자 무시.
const kjv = S.analyze({ matched_tokens: ["love"], expanded: {},
  hits: [{ book: 690, chapter: 4, verse: 8, short: "1Jo", text: "He that loveth not knoweth not God; for God is love." }] });
assert.strictEqual(kjv[0].count, 2);

// 강조할 단어가 없는 결과(붙여 친 구절의 글자 그대로 찾기) → 전부 0, 정확도 순서 유지.
const exact = S.analyze({ matched_tokens: ["태초에하나님이"], expanded: {},
  hits: [{ book: 10, chapter: 1, verse: 1, short: "창", text: "태초에 하나님이 천지를 창조하시니라" }] });
assert.deepStrictEqual([exact[0].count, exact[0].terms], [0, 0]);
assert.deepStrictEqual(S.analyze({ hits: [] }), []);
assert.deepStrictEqual(S.analyze(null), []);

// 필터 범위.
assert.deepStrictEqual(refs(S.filter(items, "ot")), ["20:1:1", "10:12:10", "300:2:6"]);
assert.deepStrictEqual(refs(S.filter(items, "nt")), ["470:2:13", "730:11:8"]);
assert.deepStrictEqual(refs(S.filter(items, "g:law")), ["20:1:1", "10:12:10"]);
assert.deepStrictEqual(refs(S.filter(items, "g:major")), ["300:2:6"]);
assert.deepStrictEqual(refs(S.filter(items, "b:730")), ["730:11:8"]);
assert.strictEqual(S.filter(items, "all").length, 5);
assert.strictEqual(S.filter(items, "???").length, 5);

// 묶음 경계: 히브리서(650)는 일반서신, 빌레몬서(640)는 바울서신, 외경은 그 밖.
assert.strictEqual(S.groupOf(640), "pauline");
assert.strictEqual(S.groupOf(650), "general");
assert.strictEqual(S.groupOf(190), "history");
assert.strictEqual(S.groupOf(170), "other");
assert.strictEqual(S.CANON.length, 66);
assert.strictEqual(S.CANON.filter((b) => !S.isNT(b)).length, 39);

// 건수.
const sum = S.summary(items);
assert.deepStrictEqual([sum.total, sum.ot, sum.nt], [5, 3, 2]);
assert.deepStrictEqual(sum.groups.map((g) => [g.key, g.count]),
  [["law", 2], ["major", 1], ["gospel", 1], ["prophecy", 1]]);
assert.deepStrictEqual(sum.groups[0].books, [
  { book: 10, short: "창", count: 1 }, { book: 20, short: "출", count: 1 }]);
assert.strictEqual(sum.byBook.get(730), 1);
const apo = S.summary(S.analyze({ matched_tokens: [], hits: [{ book: 170, chapter: 1, verse: 1, short: "토", text: "" }] }));
assert.deepStrictEqual(apo.groups.map((g) => g.key), ["other"]);

console.log("search-sort: analyze · sort 5종 · filter · summary OK");
