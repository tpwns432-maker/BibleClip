/* BibleClip — 사용자 색 테마 (docs/CUSTOM_THEME_PLAN.md).
   테마 = 기준 색 묶음 {base, bg, text, accent}. 라이트·다크는 tokens.css 그대로 쓰고,
   나머지는 <html data-palette> + 인라인 변수(--pal-*)로 tokens.css 의 계산 블록을 켠다.
   data-theme 는 늘 바탕(light|dark)만 뜻한다 — 사전 창·[data-theme="dark"] 규칙이 그대로 맞는다.
   DOM 을 건드리지 않는 함수(대비·섞기·검사)는 tests/test_theme.js 가 node 로 돌린다. */
(function (global) {
  "use strict";

  const ORDER = ["light", "dark", "paper", "sage", "navy", "black", "custom"];
  // light/dark 는 tokens.css 의 기본 값과 같은 기준 색(견본·"가져오기"용).
  const PRESETS = {
    light: { base: "light", bg: "#faf9fc", text: "#241d33", accent: "#6d4dff" },
    dark:  { base: "dark",  bg: "#0f0b1a", text: "#ece9f5", accent: "#6d4dff" },
    paper: { base: "light", bg: "#f3ebdc", text: "#3a2e22", accent: "#9b5b2c" },
    sage:  { base: "light", bg: "#edf2ec", text: "#1f2a22", accent: "#2e7a52" },
    navy:  { base: "dark",  bg: "#0e1729", text: "#e3e9f4", accent: "#5b9bff" },
    black: { base: "dark",  bg: "#000000", text: "#e6e6e6", accent: "#8e7cff" },
  };
  const HEX = /^#[0-9a-f]{6}$/;

  function isHex(v) { return typeof v === "string" && HEX.test(v.toLowerCase()); }

  /** 저장된 값을 믿지 않고 고친다. 틀린 칸은 라이트 값으로. */
  function cleanCustom(c) {
    const d = PRESETS.light, o = c && typeof c === "object" ? c : {};
    return {
      base: o.base === "dark" ? "dark" : "light",
      bg: isHex(o.bg) ? o.bg.toLowerCase() : d.bg,
      text: isHex(o.text) ? o.text.toLowerCase() : d.text,
      accent: isHex(o.accent) ? o.accent.toLowerCase() : d.accent,
    };
  }

  function seedsOf(theme, custom) {
    if (theme === "custom") return cleanCustom(custom);
    return PRESETS[theme] || PRESETS.light;
  }

  // ---- 색 계산 (CSS color-mix(in oklab) 와 같은 결과를 내야 대비 경고가 화면과 맞는다) ----
  function rgb(hex) {
    const n = parseInt(hex.slice(1), 16);
    return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
  }
  function hex(c) {
    return "#" + c.map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, "0")).join("");
  }
  const lin = (v) => { v /= 255; return v <= 0.04045 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4); };
  const delin = (v) => 255 * (v <= 0.0031308 ? v * 12.92 : 1.055 * Math.pow(v, 1 / 2.4) - 0.055);

  function toOklab(h) {
    const [r, g, b] = rgb(h).map(lin);
    const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
    const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
    const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
    return [0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
            1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s,
            0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s];
  }
  function fromOklab([L, A, B]) {
    const l = Math.pow(L + 0.3963377774 * A + 0.2158037573 * B, 3);
    const m = Math.pow(L - 0.1055613458 * A - 0.0638541728 * B, 3);
    const s = Math.pow(L - 0.0894841775 * A - 1.2914855480 * B, 3);
    return hex([4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
                -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
                -0.0041960863 * l - 0.7034186147 * m + 1.7076147010 * s].map(delin));
  }
  /** color-mix(in oklab, a p, b) — p 는 a 의 몫(0~1). */
  function mix(a, b, p) {
    const x = toOklab(a), y = toOklab(b);
    return fromOklab(x.map((v, i) => v * p + y[i] * (1 - p)));
  }

  function luminance(h) {
    const [r, g, b] = rgb(h).map(lin);
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }
  /** WCAG 대비(1~21). */
  function contrast(a, b) {
    const x = luminance(a), y = luminance(b);
    return (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05);
  }

  /** 강조색 위 글자: 흰색과 거의 검정 중 더 잘 보이는 쪽. 비슷하면 흰색(지금 모양). */
  function onAccent(accent) {
    return contrast("#ffffff", accent) >= contrast("#1a1625", accent) * 0.8 ? "#ffffff" : "#1a1625";
  }

  /** 글자가 실제로 놓이는 면(카드)과 강조 글자색 — tokens.css 의 섞는 비율과 같게. */
  function derived(s) {
    const dark = s.base === "dark";
    return {
      card: dark ? mix(s.bg, "#ffffff", 0.95) : mix(s.bg, "#ffffff", 0.4),
      accentText: dark ? mix(s.accent, "#ffffff", 0.72) : s.accent,
    };
  }

  /** 읽기 어려운 조합. [{kind: 'text'|'accent', ratio}] — 비어 있으면 괜찮다. */
  function warnings(s) {
    const d = derived(s), out = [];
    const t = contrast(s.text, d.card), a = contrast(d.accentText, d.card);
    if (t < 4.5) out.push({ kind: "text", ratio: t });
    if (a < 3) out.push({ kind: "accent", ratio: a });
    return out;
  }

  // ---- 화면에 적용 ----
  const VARS = ["--pal-bg", "--pal-text", "--pal-accent", "--pal-on-accent"];

  function supported() {
    try { return !!(global.CSS && CSS.supports("color", "color-mix(in oklab, red, blue)")); }
    catch (_) { return false; }
  }

  /** theme 을 화면에 입힌다. 못 쓰는 테마(색 섞기 미지원)면 바탕만 따른다. */
  function apply(theme, custom) {
    const root = document.documentElement;
    const s = seedsOf(theme, custom);
    root.dataset.theme = s.base;
    if (theme === "light" || theme === "dark" || !supported()) {
      delete root.dataset.palette;
      VARS.forEach((v) => root.style.removeProperty(v));
      return;
    }
    root.dataset.palette = theme;
    root.style.setProperty("--pal-bg", s.bg);
    root.style.setProperty("--pal-text", s.text);
    root.style.setProperty("--pal-accent", s.accent);
    root.style.setProperty("--pal-on-accent", onAccent(s.accent));
  }

  /** 저장된 설정 → 테마 이름. 예전 설정(theme 없음)은 dark_mode 로. */
  function fromSettings(theme, darkMode) {
    return ORDER.includes(theme) ? theme : (darkMode ? "dark" : "light");
  }

  /** ☀/🌙 버튼: 라이트↔다크. 다른 테마에서는 그 테마의 반대 바탕으로. */
  function toggled(theme, custom) {
    return seedsOf(theme, custom).base === "dark" ? "light" : "dark";
  }

  const api = { ORDER, PRESETS, cleanCustom, seedsOf, mix, contrast, onAccent, derived,
                warnings, supported, apply, fromSettings, toggled };
  global.Theme = api;
})(typeof window !== "undefined" ? window : globalThis);
