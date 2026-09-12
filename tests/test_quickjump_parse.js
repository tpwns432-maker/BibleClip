// F2 단축 입력 파서 테스트 (v1.1.14).
//
//   node tests/test_quickjump_parse.js
//
// search-notes.js 에서 relativeRef/vRange 정의만 이름으로 잘라 eval 한다
// (test_highlight_ranges.js 와 같은 방식 — 로직 복사본이 갈라지지 않는다).
const fs = require("fs");
const path = require("path");

const SRC = fs.readFileSync(
  path.join(__dirname, "..", "web", "js", "search-notes.js"), "utf8");

function extract(name, kind) {
  const re = kind === "const"
    ? new RegExp("const\\s+" + name + "\\s*=")
    : new RegExp("function\\s+" + name + "\\s*\\(");
  const m = re.exec(SRC);
  if (!m) throw new Error(`search-notes.js 에서 ${name} 을 찾지 못했습니다`);
  const open = SRC.indexOf("{", m.index);
  let depth = 0, i = open;
  for (; i < SRC.length; i++) {
    if (SRC[i] === "{") depth++;
    else if (SRC[i] === "}") { depth--; if (depth === 0) break; }
  }
  // const 화살표 함수는 닫는 중괄호 뒤의 ';' 까지 포함해야 문장이 완성된다.
  return SRC.slice(m.index, i + 1) + (kind === "const" ? ";" : "");
}

const scope = eval("(function(){" + extract("vRange", "const") + "\n" +
  extract("relativeRef") + "\nreturn {vRange, relativeRef};})()");
const { relativeRef } = scope;

let failures = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { console.log("  ok  " + label); return; }
  failures++;
  console.log("  FAIL " + label + "\n       got  " + g + "\n       want " + w);
}
// 이사야(290) 44장을 보고 있는 상태
const CTX = { book: 290, chapter: 44 };
const brief = (r) => r && [r.book, r.chapter, r.verses, !!r.sameChapter];

console.log("\n[현재 장 안의 절] 숫자만 = 절");
check("22", brief(relativeRef("22", CTX)), [290, 44, [22], true]);
check("1", brief(relativeRef("1", CTX)), [290, 44, [1], true]);
check("22절", brief(relativeRef("22절", CTX)), [290, 44, [22], true]);
check("공백 무시 ' 22 '", brief(relativeRef(" 22 ", CTX)), [290, 44, [22], true]);

console.log("\n[절 범위]");
check("22-24", brief(relativeRef("22-24", CTX)), [290, 44, [22, 23, 24], true]);
check("22~24", brief(relativeRef("22~24", CTX)), [290, 44, [22, 23, 24], true]);
check("전각 22－24", brief(relativeRef("22－24", CTX)), [290, 44, [22, 23, 24], true]);
// 거꾸로 써도 오름차순으로 편다 — 사용자가 뒤집어 쳐도 의도는 명확하다.
check("역순 24-22", brief(relativeRef("24-22", CTX)), [290, 44, [22, 23, 24], true]);

console.log("\n[현재 책의 장:절] 장이 바뀌므로 sameChapter=false");
check("44:22", brief(relativeRef("44:22", CTX)), [290, 44, [22], false]);
check("1:1 (같은 책 1장)", brief(relativeRef("1:1", CTX)), [290, 1, [1], false]);
check("53:5", brief(relativeRef("53:5", CTX)), [290, 53, [5], false]);
check("53:5-7", brief(relativeRef("53:5-7", CTX)), [290, 53, [5, 6, 7], false]);
check("전각 콜론 53：5", brief(relativeRef("53：5", CTX)), [290, 53, [5], false]);

console.log("\n[현재 책의 장만]");
check("53장", brief(relativeRef("53장", CTX)), [290, 53, null, false]);
check("1장", brief(relativeRef("1장", CTX)), [290, 1, null, false]);

console.log("\n[파서가 손대면 안 되는 입력] — 백엔드 참조 파서/키워드 검색으로 넘겨야 함");
for (const q of ["사 44:22", "창 1:1", "이사야 44장", "사44", "사랑", "hello",
                 "", "  ", "44:", ":22", "22:", "abc22", "22abc", "1:2:3"]) {
  check(`${JSON.stringify(q)} → null`, relativeRef(q, CTX), null);
}

console.log("\n[문맥이 없으면 아무것도 하지 않는다]");
check("ctx=null", relativeRef("22", null), null);
check("ctx.book 없음", relativeRef("22", { chapter: 44 }), null);

if (failures) {
  console.log(`\n${failures}개 실패`);
  process.exit(1);
}
console.log("\nALL QUICKJUMP PARSE TESTS PASSED");
