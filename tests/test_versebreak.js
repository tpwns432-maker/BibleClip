// 성경 구절 자동 줄바꿈 엔진 테스트 (v1.2.0).
//
//   node tests/test_versebreak.js
//
// measure 를 주입받는 설계라 브라우저 없이 검증된다. 한글은 폭이 글자수에
// 거의 비례하므로 테스트에서는 measure = 글자수, maxWidth = 한 줄 글자수로 둔다
// (실제 화면에서는 Canvas measureText 가 들어간다).
const fs = require("fs");
const path = require("path");

global.window = {};
new Function(fs.readFileSync(
  path.join(__dirname, "..", "web", "js", "versebreak.js"), "utf8")).call(global);
const VB = global.window.VerseBreak;

let failures = 0;
function check(label, got, want) {
  const g = JSON.stringify(got), w = JSON.stringify(want);
  if (g === w) { console.log("  ok  " + label); return; }
  failures++;
  console.log("  FAIL " + label + "\n       got  " + g + "\n       want " + w);
}
function ok(label, cond, detail) {
  if (cond) { console.log("  ok  " + label); return; }
  failures++;
  console.log("  FAIL " + label + (detail ? "\n       " + detail : ""));
}
const chars = (t) => t.length;
const planBy = (verses, width, maxLines) =>
  VB.plan(verses, { measure: chars, maxWidth: width, maxLines: maxLines || 99 });

console.log("\n[① 후보 등급] 어미가 자리를 알려준다");
check("종결 -노니(연결)", VB.wordTier("이르노니"), VB.TIER.CONN);
check("종결 -리라", VB.wordTier("하시리라"), VB.TIER.CLAUSE);
check("종결 -느니라", VB.wordTier("있느니라"), VB.TIER.CLAUSE);
check("연결 -면", VB.wordTier("구하면"), VB.TIER.CONN);
check("연결 -여", VB.wordTier("합심하여"), VB.TIER.CONN);
check("나열 -과", VB.wordTier("자들과"), VB.TIER.LIST);
check("보통 어절", VB.wordTier("아버지께서"), VB.TIER.WORD);
check("보통 어절2", VB.wordTier("사람이"), VB.TIER.WORD);
// 뒤 문장부호가 붙어도 어미를 알아봐야 한다.
check("마침표 붙은 종결", VB.wordTier("하시리라."), VB.TIER.CLAUSE);
check("닫는따옴표 붙은 종결", VB.wordTier("있느니라”"), VB.TIER.CLAUSE);
check("쉼표는 호흡 자리", VB.wordTier("야곱,"), VB.TIER.LIST);

console.log("\n[② 절 경계는 최상급] 19절↔20절 사이에서 끊겨야 한다");
{
  const t = VB.tokenize([{ text: "가 나 다" }, { text: "라 마" }]);
  check("어절 5개", t.words, ["가", "나", "다", "라", "마"]);
  check("3번째(절 끝)가 CLAUSE", t.tiers[2], VB.TIER.CLAUSE);
  // 마지막 절의 끝은 '내부 후보'가 아니다 — 어미로만 판정.
  check("마지막 절 끝은 어미 판정", t.tiers[4], VB.wordTier("마"));
}

console.log("\n[③ 기준 사례] 마태복음 18:19-20 (개역한글) → 샘플 슬라이드 재현");
const MT = [
  { n: 19, text: "진실로 다시 너희에게 이르노니 너희 중에 두 사람이 땅에서 합심하여 " +
                 "무엇이든지 구하면 하늘에 계신 내 아버지께서 저희를 위하여 이루게 하시리라" },
  { n: 20, text: "두 세 사람이 내 이름으로 모인 곳에는 나도 그들 중에 있느니라" },
];
{
  // 폭 36자 — 20절 전체가 35자다. 이보다 좁게 주면 20절이 한 줄에 안 들어가서
  // 엔진이 절 경계를 넘을 수밖에 없다(그 경우 폭을 지키는 쪽이 옳다: 투사 화면에서
  // 글자가 잘리는 것이 최악). 여기서는 '자리를 제대로 고르는가'만 본다.
  const r = planBy(MT, 36);
  console.log("      실제 출력:");
  r.lines.forEach((l) => console.log(`        [${l.length}자] ${l}`));
  // 사람이 만든 슬라이드와 같은 자리에서 끊기는가
  ok("4줄로 나뉨", r.lines.length === 4, `줄 수=${r.lines.length}`);
  ok("1줄이 '이르노니'로 끝남", /이르노니$/.test(r.lines[0]), r.lines[0]);
  ok("2줄이 '구하면'으로 끝남", /구하면$/.test(r.lines[1]), r.lines[1]);
  ok("3줄이 '하시리라'로 끝남", /하시리라$/.test(r.lines[2]), r.lines[2]);
  ok("4줄이 20절 전체", /^두 세 사람이/.test(r.lines[3]), r.lines[3]);
  ok("모든 줄이 폭 안에 들어감", r.lines.every((l) => l.length <= 36),
     r.lines.map((l) => l.length).join(","));
}

console.log("\n[④ 나열문 구제] 계 21:8 — 어미 후보가 0개인 89자 덩어리");
const REV = [{ text: "그러나 두려워하는 자들과 믿지 아니하는 자들과 흉악한 자들과 " +
  "살인자들과 행음자들과 술객들과 우상 숭배자들과 모든 거짓말 하는 자들은 불과 " +
  "유황으로 타는 못에 참예하리니 이것이 둘째 사망이라" }];
{
  const r = planBy(REV, 30);
  console.log("      실제 출력:");
  r.lines.forEach((l) => console.log(`        [${l.length}자] ${l}`));
  ok("모든 줄이 폭 안에 들어감", r.lines.every((l) => l.length <= 30),
     r.lines.map((l) => l.length).join(","));
  // '…과' 뒤에서 끊겨야지, 어절 중간이나 아무 데서나 끊기면 안 된다.
  const bad = r.lines.slice(0, -1).filter((l) => VB.wordTier(l.split(" ").pop()) === VB.TIER.WORD);
  ok("약한(어절경계) 자리를 쓰지 않음", bad.length === 0, "약한 줄: " + JSON.stringify(bad));
}

console.log("\n[⑤ 줄 수가 모자라면 실패] 호출자가 글자를 줄이라는 신호");
check("1줄에 못 담음 → null", planBy(MT, 36, 1), null);
ok("2줄에도 못 담음 → null", planBy(MT, 36, 2) === null);
ok("4줄이면 담김", planBy(MT, 36, 4) !== null);

console.log("\n[⑥ 짧은 절은 한 줄] 굳이 쪼개지 않는다");
check("짧은 절", planBy([{ text: "예수께서 우시더라" }], 30).lines,
      ["예수께서 우시더라"]);

console.log("\n[⑦ 고아 방지] 마지막 줄에 어절 하나만 남기지 않는다");
{
  // 폭을 넉넉히 주면 억지로 한 어절을 떨어뜨릴 이유가 없다.
  const r = planBy([{ text: "가나 다라 마바 사아 자차 카타 파하" }], 20);
  const last = r.lines[r.lines.length - 1];
  ok("마지막 줄이 어절 1개가 아님", r.lines.length === 1 || last.split(" ").length > 1,
     JSON.stringify(r.lines));
}

console.log("\n[⑧ 경계 입력]");
check("빈 입력", planBy([{ text: "" }], 30).lines, []);
check("어절 하나", planBy([{ text: "말씀" }], 30).lines, ["말씀"]);
// 한 어절이 폭보다 길면 어절 중간을 끊는 대신 넘치는 것을 허용한다.
{
  const r = planBy([{ text: "아주아주아주긴한단어" }], 5);
  ok("긴 어절은 쪼개지 않고 넘침 허용", r && r.lines.length === 1, JSON.stringify(r));
}

console.log("\n[⑨ 글자 크기 자동 맞춤] 들어가는 가장 큰 크기를 찾는다");
{
  // 글자 크기 s 에서 한 글자 폭 = s 라고 가정한 가짜 렌더러.
  const r = VB.fit(MT, {
    measureAt: (t, size) => t.length * size,
    maxWidth: 1000, maxHeight: 400, lineHeight: 1.4, min: 8, max: 120,
  });
  ok("맞는 크기를 찾음", r && r.size > 0, JSON.stringify(r && r.size));
  ok("한 줄이 폭을 넘지 않음",
     r.lines.every((l) => l.length * r.size <= 1000),
     r.lines.map((l) => l.length * r.size).join(","));
  ok("전체 높이가 상자 안", r.lines.length * r.size * 1.4 <= 400,
     `${r.lines.length}줄 × ${r.size}px`);
  // 한 단계 큰 크기는 반드시 실패해야 '가장 큰'이 맞다.
  const bigger = VB.fit(MT, {
    measureAt: (t, size) => t.length * size,
    maxWidth: 1000, maxHeight: 400, lineHeight: 1.4,
    min: r.size + 1, max: r.size + 1,
  });
  ok("한 단계 크면 안 들어감(최대성)", bigger === null, JSON.stringify(bigger));
  console.log(`      → ${r.size}px, ${r.lines.length}줄`);
}

console.log("\n[⑩ 등급 벌점이 여백보다 우선] 엔진의 존재 이유");
{
  // 어미 자리에서 끊으면 줄이 짧아지지만, 꽉 채우려고 어색한 자리를 쓰면 안 된다.
  // "…하시니라" 뒤가 자연스러운 자리, 그 다음 어절들은 전부 보통 어절.
  const v = [{ text: "여호와께서 그에게 말씀하시니라 아브라함이 장막 문에 앉았더라" }];
  const r = planBy(v, 22);
  ok("어미 자리에서 끊음", /하시니라$/.test(r.lines[0]),
     JSON.stringify(r.lines));
}

console.log("\n[⑪ 문장 경계는 강제] 한 줄에 두 문장이 섞이면 안 된다");
check("종결 -니라", VB.sentenceEnd("칭하시니라"), true);
check("종결 -더라", VB.sentenceEnd("좋았더라"), true);
check("종결 -나이다", VB.sentenceEnd("있나이다"), true);
check("문장부호로 끝나면 무조건", VB.sentenceEnd("말한다."), true);
check("닫는따옴표까지 붙어도", VB.sentenceEnd("있다.”"), true);
// 실제 본문 조사에서 드러난 오탐들 — 강제 줄바꿈이라 하나라도 걸리면 눈에 보인다.
check("'다'(부사 '모두')는 아님", VB.sentenceEnd("다"), false);
check("'아니라'(연결)는 아님", VB.sentenceEnd("아니라"), false);
check("'아니니라'는 진짜 문장 끝", VB.sentenceEnd("아니니라"), true);
check("'바다'(명사)는 아님", VB.sentenceEnd("바다"), false);
check("'따라'(조사)는 아님", VB.sentenceEnd("따라"), false);
check("'것이요'(나열)는 아님", VB.sentenceEnd("것이요"), false);
check("'것보다'(비교)는 아님", VB.sentenceEnd("것보다"), false);
{
  // 창 1:10 — 예전에는 2번째 줄이 "칭하시니라 하나님의 보시기에 좋았더라"가 되어
  // 서로 다른 두 문장이 한 줄에 섞였다(사용자가 지적한 바로 그 증상).
  const GEN = [{ text: "하나님이 뭍을 땅이라 칭하시고 모인 물을 바다라 칭하시니라 " +
                       "하나님의 보시기에 좋았더라" }];
  const r = planBy(GEN, 34);
  ok("문장이 줄을 넘어 섞이지 않음", /칭하시니라$/.test(r.lines[0]), JSON.stringify(r.lines));
  ok("둘째 문장이 제 줄에서 시작", /^하나님의 보시기에/.test(r.lines[1]), JSON.stringify(r.lines));
}
{
  // 강제로 끊긴 짧은 문장은 '고아'가 아니다 — 벌점을 물리면 DP 가 그 줄을 피하려고
  // 엉뚱한 배치를 고른다.
  const v = [{ text: "예수께서 우시더라 그러므로 유대인들이 말하되 보라 그를 어떻게 사랑하셨는가" }];
  const r = planBy(v, 30);
  ok("짧은 문장도 제 줄을 갖는다", r.lines.length >= 2, JSON.stringify(r.lines));
}

console.log("\n[⑫ 자동 분할] 한 화면에 안 들어가는 긴 본문은 여러 장으로");
{
  // 글자 크기 s 에서 한 글자 폭 = s*0.95 (한글 근사). 1920x1080 프로젝터 기준 상자.
  const measureAt = (t, s) => t.length * s * 0.95;
  const BOX = { measureAt, maxWidth: 1690, maxHeight: 800, lineHeight: 1.35,
                minSize: 28, min: 12, max: 160 };
  const verse = (n, words) => ({ n, text: Array.from({ length: words }, () => "가나다라").join(" ") });

  // 짧은 본문은 굳이 나누지 않는다.
  const one = VB.paginate([verse(1, 4)], BOX);
  check("짧은 절 → 1장", one.length, 1);
  ok("한 화면을 크게 채움", one[0].size >= 100, one[0].size + "px");

  // 긴 본문은 나뉘고, 모든 장이 '읽을 수 있는 크기'를 지킨다.
  const many = VB.paginate(Array.from({ length: 80 }, (_, i) => verse(i + 1, 8)), BOX);
  ok("여러 장으로 나뉨", many.length > 1, many.length + "장");
  ok("모든 장이 minSize 이상", many.every((p) => p.size >= 28),
     many.map((p) => p.size).join(","));
  ok("모든 장이 높이 안에", many.every((p) => p.lines.length * p.size * 1.35 <= 800),
     many.map((p) => (p.lines.length * p.size * 1.35).toFixed(0)).join(","));

  // ★ 절이 장을 넘어 쪼개지면 안 된다 — 순서대로, 빠짐없이, 겹치지 않게.
  const seen = [];
  many.forEach((p) => p.verses.forEach((v) => seen.push(v.n)));
  check("모든 절이 빠짐없이 한 번씩",
        seen.join(","), Array.from({ length: 80 }, (_, i) => i + 1).join(","));

  // 캐시를 씌우면서 measureAt 이 제 자신을 부르는 무한 재귀를 낸 적이 있다.
  // (테스트가 없어 놓쳤던 버그 — 여기서 고정한다.)
  let calls = 0;
  VB.paginate([verse(1, 10)], Object.assign({}, BOX,
    { measureAt: (t, s) => { calls++; return measureAt(t, s); } }));
  ok("measureAt 이 재귀하지 않음", calls > 0 && calls < 100000, calls + "회");

  // 빈 입력.
  check("빈 목록 → 0장", VB.paginate([], BOX).length, 0);
}

if (failures) {
  console.log(`\n${failures}개 실패`);
  process.exit(1);
}
console.log("\nALL VERSEBREAK TESTS PASSED");
