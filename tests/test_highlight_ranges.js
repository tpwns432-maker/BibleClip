// 형광펜 구간 대수 + 오프셋→HTML 복원 테스트 (v1.1.12).
//
//   node tests/test_highlight_ranges.js
//
// cards.js 의 해당 함수들은 CardManager IIFE 안에 있어 import 할 수 없다. 그래서
// 소스에서 함수 정의만 이름으로 잘라내 여기서 eval 한다 — 브라우저에서 실제로 도는
// 코드 그대로를 검증하므로 로직 복사본이 따로 생겨 갈라질 일이 없다. 이 테스트가
// "함수를 못 찾았다"고 실패하면 cards.js 에서 이름이 바뀐 것이니 아래 목록을 고칠 것.
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "web", "js", "cards.js"), "utf8");

// 함수 정의 하나를 여는 중괄호부터 짝이 맞는 닫는 중괄호까지 잘라낸다.
function extract(name) {
  const sig = new RegExp("function\\s+" + name + "\\s*\\(", "g");
  const m = sig.exec(SRC);
  if (!m) throw new Error(`cards.js 에서 function ${name} 을 찾지 못했습니다`);
  const open = SRC.indexOf("{", m.index);
  let depth = 0, i = open;
  for (; i < SRC.length; i++) {
    const ch = SRC[i];
    if (ch === "{") depth++;
    else if (ch === "}") { depth--; if (depth === 0) break; }
  }
  if (depth !== 0) throw new Error(`${name} 의 중괄호 짝이 맞지 않습니다`);
  return SRC.slice(m.index, i + 1);
}

// 순수 함수들이 기대하는 최소 환경(core.js 의 esc 와 동일 구현).
const esc = (s) =>
  String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
const HL_COLORS = ["y", "g", "b", "p"];

const NAMES = ["hlColor", "hlMark", "hlTextHTML", "normRanges", "mergeRange",
               "subtractRange"];
const scope = eval(
  "(function(){" + NAMES.map(extract).join("\n") + "\nreturn {" +
  NAMES.join(",") + "};})()");
const { hlTextHTML, normRanges, mergeRange, subtractRange } = scope;

let failures = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { console.log("  ok  " + label); return; }
  failures++;
  console.log("  FAIL " + label + "\n       got  " + g + "\n       want " + w);
}
// 구간 목록을 읽기 쉬운 "s-e:c" 형태로.
const brief = (list) => list.map((r) => `${r.s}-${r.e}:${r.c}`);

const RAW = "태초에 하나님이 천지를 창조하시니라";
// 태0 초1 에2 ␣3 하4 나5 님6 이7 ␣8 천9 지10 를11 ␣12 창13 조14 하15 시16 니17 라18
//   → '천지를' = 9..12, '창조' = 13..15

console.log("\n[normRanges] 정렬 · 같은색 병합 · 겹침 제거 · t 재계산");
check("정렬", brief(normRanges(
  [{ s: 10, e: 13, c: "g" }, { s: 0, e: 3, c: "y" }], RAW)),
  ["0-3:y", "10-13:g"]);
check("같은 색 겹침 → 하나로", brief(normRanges(
  [{ s: 0, e: 6, c: "y" }, { s: 4, e: 9, c: "y" }], RAW)), ["0-9:y"]);
check("같은 색 인접 → 하나로", brief(normRanges(
  [{ s: 0, e: 4, c: "y" }, { s: 4, e: 8, c: "y" }], RAW)), ["0-8:y"]);
check("다른 색 인접 → 유지", brief(normRanges(
  [{ s: 0, e: 4, c: "y" }, { s: 4, e: 8, c: "g" }], RAW)), ["0-4:y", "4-8:g"]);
check("다른 색 겹침 → 뒤를 잘라냄", brief(normRanges(
  [{ s: 0, e: 6, c: "y" }, { s: 3, e: 9, c: "g" }], RAW)), ["0-6:y", "6-9:g"]);
check("빈 구간 제거", brief(normRanges(
  [{ s: 5, e: 5, c: "y" }, { s: 0, e: 3, c: "y" }], RAW)), ["0-3:y"]);
check("알 수 없는 색 → 기본색", brief(normRanges(
  [{ s: 0, e: 3, c: "rainbow" }], RAW)), ["0-3:y"]);
// t 는 경계가 바뀌어도 항상 실제 본문에서 다시 떠야 한다. 안 그러면 다음 렌더의
// 검증에 걸려 하이라이트가 사라진다.
check("t 재계산", normRanges([{ s: 9, e: 12, c: "y", t: "낡은값" }], RAW)[0].t,
  "천지를");

console.log("\n[mergeRange] 형광펜 덧칠 — 새 색이 이기고 남는 쪽은 보존");
check("빈 목록에 추가", brief(mergeRange([], { s: 10, e: 13, c: "y" }, RAW)),
  ["10-13:y"]);
check("무관한 구간은 그대로", brief(mergeRange(
  [{ s: 0, e: 3, c: "g" }], { s: 10, e: 13, c: "y" }, RAW)),
  ["0-3:g", "10-13:y"]);
check("같은 색 겹쳐 칠하기 → 병합", brief(mergeRange(
  [{ s: 0, e: 6, c: "y" }], { s: 4, e: 10, c: "y" }, RAW)), ["0-10:y"]);
// 노랑 구간의 가운데를 초록으로 덮으면 노랑이 좌우로 쪼개진다.
check("다른 색이 가운데를 덮음 → 3조각", brief(mergeRange(
  [{ s: 0, e: 12, c: "y" }], { s: 4, e: 8, c: "g" }, RAW)),
  ["0-4:y", "4-8:g", "8-12:y"]);
check("다른 색이 왼쪽을 덮음", brief(mergeRange(
  [{ s: 4, e: 12, c: "y" }], { s: 0, e: 8, c: "g" }, RAW)),
  ["0-8:g", "8-12:y"]);
check("다른 색이 완전히 덮음 → 새 색만", brief(mergeRange(
  [{ s: 4, e: 8, c: "y" }], { s: 0, e: 12, c: "g" }, RAW)), ["0-12:g"]);
check("여러 구간을 한 번에 덮음", brief(mergeRange(
  [{ s: 0, e: 3, c: "y" }, { s: 6, e: 9, c: "b" }, { s: 14, e: 17, c: "p" }],
  { s: 2, e: 15, c: "g" }, RAW)), ["0-2:y", "2-15:g", "15-17:p"]);

console.log("\n[subtractRange] ✕ 지우기");
check("가운데 지우기 → 2조각", brief(subtractRange(
  [{ s: 0, e: 12, c: "y" }], { s: 4, e: 8 }, RAW)), ["0-4:y", "8-12:y"]);
check("전체 지우기 → 빈 목록", brief(subtractRange(
  [{ s: 4, e: 8, c: "y" }], { s: 0, e: 12 }, RAW)), []);
check("왼쪽 걸쳐 지우기", brief(subtractRange(
  [{ s: 4, e: 12, c: "y" }], { s: 0, e: 8 }, RAW)), ["8-12:y"]);
check("무관한 범위 지우기 → 변화 없음", brief(subtractRange(
  [{ s: 0, e: 3, c: "y" }], { s: 10, e: 13 }, RAW)), ["0-3:y"]);
check("여러 구간 걸쳐 지우기", brief(subtractRange(
  [{ s: 0, e: 4, c: "y" }, { s: 8, e: 14, c: "g" }], { s: 2, e: 10 }, RAW)),
  ["0-2:y", "10-14:g"]);

console.log("\n[hlTextHTML] 오프셋 → HTML (esc 이후가 아니라 원문 기준)");
check("구간 없음 → 그냥 이스케이프", hlTextHTML("a<b&c", []), "a&lt;b&amp;c");
check("한 구간",
  hlTextHTML("abcdef", [{ s: 2, e: 4, c: "y", t: "cd" }]),
  'ab<span class="hl-mark" data-c="y" data-s="2" data-e="4">cd</span>ef');
// ★ 오프셋은 esc 이전 원문 기준이어야 한다. '&' 가 '&amp;' 로 5자가 되므로 만약
// 이스케이프된 문자열에 오프셋을 적용하면 하이라이트가 밀린다.
check("& 를 넘는 오프셋이 밀리지 않음",
  hlTextHTML("a&b cd", [{ s: 4, e: 6, c: "g", t: "cd" }]),
  'a&amp;b <span class="hl-mark" data-c="g" data-s="4" data-e="6">cd</span>');
check("하이라이트 안의 특수문자도 이스케이프",
  hlTextHTML("x <y> z", [{ s: 2, e: 5, c: "y", t: "<y>" }]),
  'x <span class="hl-mark" data-c="y" data-s="2" data-e="5">&lt;y&gt;</span> z');
check("여러 구간",
  hlTextHTML("abcdefgh", [{ s: 0, e: 2, c: "y", t: "ab" },
                          { s: 5, e: 7, c: "b", t: "fg" }]),
  '<span class="hl-mark" data-c="y" data-s="0" data-e="2">ab</span>cde' +
  '<span class="hl-mark" data-c="b" data-s="5" data-e="7">fg</span>h');

console.log("\n[hlTextHTML] 본문이 바뀐 뒤 — 검증(t)과 재탐색");
// 성경 DB 갱신·역본 재동봉으로 본문이 앞에서 밀린 경우: 저장된 오프셋 자리에는
// 다른 글자가 있으므로 그 자리를 칠하지 않고 같은 조각을 다시 찾아 칠한다.
check("본문이 밀리면 조각을 재탐색",
  hlTextHTML("XXabcdef", [{ s: 2, e: 4, c: "y", t: "cd" }]),
  'XXab<span class="hl-mark" data-c="y" data-s="4" data-e="6">cd</span>ef');
// 조각이 아예 사라졌으면 엉뚱한 곳을 칠하는 대신 조용히 버린다.
check("조각이 사라지면 폐기",
  hlTextHTML("완전히 다른 본문", [{ s: 2, e: 4, c: "y", t: "cd" }]),
  "완전히 다른 본문");
check("t 가 없으면 오프셋을 그대로 신뢰",
  hlTextHTML("abcdef", [{ s: 2, e: 4, c: "y" }]),
  'ab<span class="hl-mark" data-c="y" data-s="2" data-e="4">cd</span>ef');
check("본문이 짧아져 범위를 벗어나면 폐기",
  hlTextHTML("ab", [{ s: 5, e: 9, c: "y", t: "zzzz" }]), "ab");

console.log("\n[통합] 실제 절 텍스트로 칠하기");
const painted = hlTextHTML(RAW, normRanges(
  mergeRange([], { s: 9, e: 12, c: "y" }, RAW), RAW));
check("'천지를' 만 칠해짐", painted,
  '태초에 하나님이 <span class="hl-mark" data-c="y" data-s="9" data-e="12">' +
  '천지를</span> 창조하시니라');
// 칠한 결과의 textContent(= 태그를 뺀 글자)는 원문과 같아야 한다. 이게 성립해야
// paintHighlights 가 DOM 을 원문 캐시 없이 몇 번이고 다시 칠할 수 있다.
check("태그를 뺀 글자는 원문과 동일",
  painted.replace(/<[^>]*>/g, "").replace(/&amp;/g, "&")
         .replace(/&lt;/g, "<").replace(/&gt;/g, ">"), RAW);

if (failures) {
  console.log(`\n${failures}개 실패`);
  process.exit(1);
}
console.log("\nALL HIGHLIGHT RANGE TESTS PASSED");
