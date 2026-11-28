// 말로 구절 찾기 — 들린 문장 → 참조 문자열 다듬기 테스트.
//
//   node tests/test_voice_ref.js
//
// android/.../assets/android/voice.js 를 그대로 읽어 spokenRef 만 쓴다
// (document 가 없으면 버튼 배선은 건너뛴다).
const path = require("path");

global.window = {};
require(path.join(__dirname, "..", "android", "app", "src", "main", "assets", "android", "voice.js"));
const { spokenRef, koNumber } = window.BibleClipVoice;

let failures = 0;
function check(input, want) {
  const got = spokenRef(input);
  if (got === want) { console.log("  ok  " + input + " → " + got); return; }
  failures++;
  console.log("  FAIL " + input + "\n       got  " + got + "\n       want " + want);
}

console.log("한글 숫자");
for (const [s, n] of [["일", 1], ["십", 10], ["십육", 16], ["이십삼", 23], ["백", 100], ["백오", 105], ["백십구", 119], ["백오십", 150]]) {
  if (koNumber(s) !== n) { failures++; console.log("  FAIL koNumber " + s + " = " + koNumber(s)); }
}

console.log("참조");
check("요한복음 3장 16절", "요한복음 3:16");
check("요한복음 3장", "요한복음 3");
check("요한복음3장16절", "요한복음 3:16");
check("요한 복음 3장 16절", "요한복음 3:16");
check("시편 23편", "시편 23");
check("시편 119편 105절", "시편 119:105");
check("요한복음 삼 장 십육 절", "요한복음 3:16");
check("이사야 오십삼 장", "이사야 53");
check("사도행전 이 장", "사도행전 2");
check("요한일서 4장 8절", "요한1서 4:8");
check("요한 삼서 1장", "요한3서 1");
check("창세기 1장 1절에서 3절", "창세기 1:1-3");
check("창세기 1장 1절부터 3절까지", "창세기 1:1-3");
check("에베소서 6장 10절에서 18절까지", "에베소서 6:10-18");
check("로마서 8장 28절로 가 줘", "로마서 8:28");
check("시편 23편 찾아 줘", "시편 23");
check("요한복음 3장 16절.", "요한복음 3:16");
check("요 3:16", "요 3:16");
check("John 3:16", "John 3:16");
check("John 3 16", "John 3:16");
check("John chapter 3 verse 16", "John 3:16");
check("first John 4:8", "1 John 4:8");
check("Genesis 1:1 to 3", "Genesis 1:1-3");
check("Psalm 23", "Psalm 23");
console.log("참조 아님 — 그대로");
check("사랑", "사랑");
check("여호와는 나의 목자시니", "여호와는 나의 목자시니");

if (failures) { console.log(`\n${failures} 건 실패`); process.exit(1); }
console.log("\n모두 통과");
