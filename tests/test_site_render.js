// 웹판 커뮤니티 글 그리기 테스트 (bibleclip/server/static/site.js 의 renderText).
//
//   node tests/test_site_render.js
//
// 상대가 쓴 글 속 HTML 이 실행되지 않는지(전부 글자로), 구절 · 웹 주소만 링크가 되는지 본다.
const fs = require("fs");
const path = require("path");
const assert = require("assert");

global.window = {};
new Function(fs.readFileSync(path.join(__dirname, "..", "bibleclip", "server", "static", "site.js"), "utf8"))();
const { renderText, esc, goHref } = window.Site;

// HTML 은 글자로.
const evil = '<img src=x onerror="alert(1)"><script>alert(2)</script> & \'q\'';
const out = renderText(evil, []);
assert(!/<img|<script/i.test(out), out);
assert.strictEqual(out, esc(evil));
assert(out.includes("&lt;script&gt;") && out.includes("&amp;") && out.includes("&#39;"));

// 구절: 서버가 준 위치(JS 문자열 위치)에 링크. 이모지가 앞에 있어도 맞는다.
const text = "😀 오늘은 요 3:16 을";
const s = text.indexOf("요 3:16");
const ref = { s, e: s + 6, book: 500, chapter: 3, verses: [16], label: "요 3:16" };
const html = renderText(text, [ref]);
assert(html.includes('<a class="vref" href="bible#go=500.3.16"'), html);
assert(html.includes(">요 3:16</a>"), html);
assert.strictEqual(goHref({ book: 500, chapter: 3, verses: [16, 17, 18] }), "bible#go=500.3.16,17,18");
// 범위를 벗어나거나 겹치는 위치는 무시(글이 깨지지 않게).
assert.strictEqual(renderText("abc", [{ s: 1, e: 99, book: 1, chapter: 1, verses: [1], label: "x" }]), "abc");

// 웹 주소: http(s) 만 링크, 끝의 문장부호는 빼고, 새 창 · 출처 안 넘김.
const u = renderText("영상 https://example.com/a?b=1&c=2). 끝", []);
assert(u.includes('<a href="https://example.com/a?b=1&amp;c=2" target="_blank" rel="noopener noreferrer">'), u);
assert(u.endsWith("). 끝"), u);
assert(!renderText("javascript:alert(1)", []).includes("<a"));
// 주소 안에 따옴표로 속성을 깨려는 시도.
assert(!renderText('https://x.com/"onmouseover="alert(1)', []).includes('"onmouseover'));

console.log("test_site_render: ok");
