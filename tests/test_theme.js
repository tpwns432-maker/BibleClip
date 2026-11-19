// 사용자 색 테마 테스트 (docs/CUSTOM_THEME_PLAN.md).
//
//   node tests/test_theme.js
//
// web/js/theme.js 의 DOM 밖 함수(대비·섞기·검사)를 브라우저에서 도는 파일 그대로 읽어 돌린다.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.window = {};
new Function(fs.readFileSync(path.join(__dirname, "..", "web", "js", "theme.js"), "utf8"))();
const T = window.Theme;

// WCAG 대비: 흰/검 21, 같은 색 1.
assert.strictEqual(Math.round(T.contrast("#ffffff", "#000000")), 21);
assert.strictEqual(T.contrast("#777777", "#777777"), 1);

// oklab 섞기: 양 끝은 그대로, 흰+검 반은 oklab 중간 회색 #636363(sRGB 로 섞은 #808080 이 아님 — 브라우저 color-mix 와 같은 값).
assert.strictEqual(T.mix("#336699", "#ffffff", 1), "#336699");
assert.strictEqual(T.mix("#336699", "#ffffff", 0), "#ffffff");
const grey = T.mix("#000000", "#ffffff", 0.5);
assert.strictEqual(grey, "#636363");

// 강조 위 글자: 진한 색엔 흰색, 밝은 노랑엔 검정 쪽.
assert.strictEqual(T.onAccent("#6d4dff"), "#ffffff");
assert.strictEqual(T.onAccent("#2e7a52"), "#ffffff");
assert.strictEqual(T.onAccent("#ffe14d"), "#1a1625");

// 미리 만든 테마는 모두 읽기 경고가 없어야 한다(테마를 고치면 여기서 걸린다).
for (const name of T.ORDER.filter((n) => n !== "custom")) {
  assert.deepStrictEqual(T.warnings(T.PRESETS[name]), [], `${name} 대비 부족`);
}

// 읽기 어려운 조합은 경고.
const bad = T.warnings({ base: "light", bg: "#ffffff", text: "#bbbbbb", accent: "#ffee88" });
assert.deepStrictEqual(bad.map((w) => w.kind), ["text", "accent"]);

// 저장 값 검사: 틀린 칸은 라이트 값, 대문자는 소문자로.
assert.deepStrictEqual(T.cleanCustom({ base: "dark", bg: "#ABCDEF", text: "red", accent: 5 }),
  { base: "dark", bg: "#abcdef", text: "#241d33", accent: "#6d4dff" });
assert.deepStrictEqual(T.cleanCustom(null), T.PRESETS.light);

// 예전 설정(theme 없음)은 dark_mode 로.
assert.strictEqual(T.fromSettings(undefined, true), "dark");
assert.strictEqual(T.fromSettings("", false), "light");
assert.strictEqual(T.fromSettings("paper", true), "paper");
assert.strictEqual(T.fromSettings("rainbow", false), "light");

// ☀/🌙: 반대 바탕으로.
assert.strictEqual(T.toggled("light"), "dark");
assert.strictEqual(T.toggled("paper"), "dark");
assert.strictEqual(T.toggled("navy"), "light");
assert.strictEqual(T.toggled("custom", { base: "dark" }), "light");

console.log("test_theme: ok");
