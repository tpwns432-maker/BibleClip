// BibleClip — 성경 구절 자동 줄바꿈 엔진 (자막/PPT 화면용, v1.2.0).
//
// 목표: 사람이 손대지 않고, 문맥이 끊기지 않는 자리에서 줄을 나눈다.
//
// 왜 규칙이 통하는가 — 한국어 성경은 절 경계 어미가 극도로 정형화돼 있다.
// 4개 역본 319절을 조사한 결과, 절 하나당 내부 절경계 후보가 평균 2.7개,
// 후보가 하나라도 있는 절이 92~93%였다. 예:
//     진실로 다시 너희에게 이르노니 / 너희 중에 … 구하면 /
//     하늘에 계신 … 이루게 하시리라
// 사람이 고른 자리가 아니라 어미(-니, -면, -라)가 알려주는 자리다.
//
// 그래서 이 모듈은 두 단계로 나뉜다.
//   ① 후보 추출 — 어절마다 "여기서 끊으면 얼마나 자연스러운가"를 등급으로.
//   ② 배치 최적화 — 실제 렌더 폭을 재서, 줄 여백²과 등급 벌점의 합을 최소화.
//
// ★ 폭은 반드시 '지금 그 화면의 글꼴로' 재야 한다(measure 주입). 줄바꿈을 미리
//   구워두면 역본·글꼴·창 크기가 바뀔 때마다 어긋난다. 동적인 게 문제가 아니라
//   동적으로 푸는 것이 정답이다. measure 를 주입받으므로 브라우저 없이도 테스트된다.
"use strict";

window.VerseBreak = (() => {

  // ---- ① 후보 추출 ----

  // 종결어미 — 문장이 끝나는 자리. 여기서 끊으면 거의 항상 자연스럽다.
  const FINAL = ["느니라", "니라", "리라", "도다", "노라", "지라", "으라", "하라",
                 "이라", "라", "다", "요", "까", "냐", "랴"];
  // 연결어미 — 절과 절을 잇는 자리. 끊어도 되지만 필수는 아니다.
  const CONN = ["거니와", "거늘", "로되", "지만", "므로", "든지", "면", "니", "고",
                "며", "나", "되", "여", "매", "자"];
  // 나열 조사 — 어미가 없는 열거문("…자들과 …자들과 …")을 구제한다.
  // 계 21:8 은 어미 후보가 0개라 89자 한 덩어리로 남는데, 이 등급이 쪼갠다.
  const LIST = ["와", "과"];

  const TIER = { CLAUSE: 1, CONN: 2, LIST: 3, WORD: 4 };

  // ---- 문장 경계(강제 줄바꿈) ----
  //
  // 등급은 '선호'일 뿐이라 폭이 아까우면 DP 가 서로 다른 두 문장을 한 줄에 묶는다.
  // 한 줄에 두 문장이 섞이면 읽는 사람이 의미를 끊어 읽지 못한다 → 문장 경계만은
  // 강제로 나눈다.
  //
  // ★ 여기 목록은 위의 FINAL 보다 훨씬 보수적이어야 한다. 강제 줄바꿈은 오탐이
  //   그대로 '잘못된 줄바꿈'으로 보이기 때문이다. 실제 본문을 조사해 아래를 뺐다:
  //     · 단독 "다"  → "모두"라는 부사 (22회로 최다 오탐)
  //     · "아니라"   → "A가 아니라 B" 연결
  //     · "것이요"/"아니요" → 나열 연결 (-요 단독 제외)
  //     · "것보다"/"바다"/"따라" → 비교·명사·조사 (-다/-라 단독 제외)
  //   남은 목록으로 다시 조사했을 때 60개 어절 전부가 실제 문장 끝이었다.
  const SENT_FINAL = ["느니라", "니라", "리라", "더라", "도다", "로다", "노라", "지라",
                      "나이다", "나이까", "리이까", "니이까", "찌어다", "지어다",
                      "느냐", "나냐", "리요", "옵소서", "하소서"];
  // 위 꼬리를 갖지만 문장 끝이 아닌 낱말 — '정확히 일치'할 때만 제외한다
  // ("아니라"는 연결이지만 "아니니라"는 진짜 문장 끝이므로 접미사로 빼면 안 된다).
  const SENT_EXCEPT = ["아니라"];
  // 한두 글자 낱말이 우연히 꼬리와 겹치는 것을 막는다(대표적으로 "다").
  const SENT_MIN_LEN = 3;
  // 문장부호로 끝나면 어미와 무관하게 문장 끝이다 — 개역한글·개역개정에는 문장부호가
  // 아예 없지만 현대어 역본(현대인의 성경 등)에는 있어서, 그쪽에서 훨씬 정확해진다.
  const SENT_PUNCT = /[.!?]["'”’」』）)\]]*$/;

  // 이 어절 뒤에서 문장이 끝나는가(= 반드시 줄을 바꿔야 하는가).
  function sentenceEnd(word) {
    const raw = String(word);
    if (SENT_PUNCT.test(raw)) return true;
    const w = bare(raw);
    if (w.length < SENT_MIN_LEN) return false;
    if (SENT_EXCEPT.indexOf(w) >= 0) return false;
    return SENT_FINAL.some((e) => w.endsWith(e));
  }

  // 끊기 등급이 낮을수록 자연스럽다. 벌점은 "폭이 급하지 않으면 약한 자리를 쓰지
  // 말라"는 뜻 — 등급 간 격차를 크게 둬야 DP 가 억지 줄바꿈을 피한다.
  const TIER_PENALTY = { 1: 0, 2: 60, 3: 300, 4: 1200 };

  // 어미 판정 전에 뒤쪽 문장부호를 떼어낸다("하시리라." / "있느니라”" 도 종결이다).
  const TRAIL_PUNCT = /[.,!?;:"'”’」』）)\]】…·]+$/;
  const bare = (w) => String(w).replace(TRAIL_PUNCT, "");

  const endsWithAny = (w, list) => list.some((e) => w.endsWith(e));

  // 어절 하나의 '뒤에서 끊을 때'의 등급.
  function wordTier(word) {
    const w = bare(word);
    if (!w) return TIER.WORD;
    // 쉼표로 끝나면 그 자체가 호흡 자리 — 나열과 같은 등급.
    if (/[,·]$/.test(String(word))) return TIER.LIST;
    if (endsWithAny(w, FINAL)) return TIER.CLAUSE;
    if (endsWithAny(w, CONN)) return TIER.CONN;
    if (endsWithAny(w, LIST)) return TIER.LIST;
    return TIER.WORD;
  }

  // 절 목록 → 어절 배열 + 어절별 끊기 등급.
  // 절과 절 사이는 항상 최상급 후보다(샘플 슬라이드도 19절↔20절에서 줄을 나눈다).
  function tokenize(verses) {
    const words = [], tiers = [], hard = [];
    const list = Array.isArray(verses) ? verses : [{ text: String(verses || "") }];
    list.forEach((v, vi) => {
      const ws = String((v && v.text) || "").trim().split(/\s+/).filter(Boolean);
      ws.forEach((w, i) => {
        words.push(w);
        const lastOfVerse = i === ws.length - 1;
        tiers.push(lastOfVerse && vi < list.length - 1 ? TIER.CLAUSE : wordTier(w));
        hard.push(sentenceEnd(w));
      });
    });
    // 마지막 어절은 어차피 글의 끝이라 '강제'가 의미 없다(줄을 하나 더 만들지 않게).
    if (hard.length) hard[hard.length - 1] = false;
    return { words, tiers, hard };
  }

  // ---- ② 배치 최적화 (Knuth–Plass 식 최소 여백 DP) ----

  // 줄 하나가 짧게 남을수록 제곱으로 벌점 → 자연히 줄 길이가 고르게 맞는다.
  // 마지막 줄도 예외 없이 벌점을 준다: 문단 조판과 달리 가운데 정렬 슬라이드는
  // 모든 줄이 비슷해야 예쁘다.
  //
  // ★ 반드시 '비율'로 정규화한다. 폭을 px 로 재면 여백²이 수백만까지 가서 등급
  //   벌점(0~1200)이 반올림 오차 수준으로 묻힌다 — 그러면 DP 가 어미를 무시하고
  //   글자만 꽉 채우게 되어 이 엔진을 만든 이유가 사라진다. 0~10000 범위로 맞춰
  //   두면 measure 의 단위(px/문자수)가 무엇이든 등급 벌점이 같은 무게를 갖는다.
  const RAGGED_SCALE = 10000;
  const RAGGED = (slack, maxWidth) => {
    const r = maxWidth > 0 ? slack / maxWidth : 0;
    return r * r * RAGGED_SCALE;
  };
  // 마지막 줄에 어절이 하나만 남는 것(고아)은 눈에 띄게 볼썽사납다.
  // 등급 벌점과 같은 척도 — 줄 하나가 절반쯤 비는 것(2500)과 맞먹게 둔다.
  const WIDOW_PENALTY = 2500;

  /**
   * 어절들을 maxWidth 안에서 최적으로 줄 나눔.
   * @param {string[]} words
   * @param {number[]} tiers          어절별 끊기 등급(1~4)
   * @param {object} o
   *   measure(text) -> number        실제 렌더 폭(px). 반드시 주입.
   *   maxWidth      한 줄 최대 폭
   *   maxLines      허용 줄 수(초과하면 실패)
   * @returns {{lines:string[], cost:number}|null}  실패 시 null
   */
  function layout(words, tiers, o) {
    const n = words.length;
    if (!n) return { lines: [], cost: 0 };
    const measure = o.measure, maxWidth = o.maxWidth;
    const maxLines = o.maxLines || 99;
    // hard[j] = 이 어절 뒤에서 문장이 끝난다 → 다음 어절은 반드시 새 줄.
    const hard = o.hard || [];

    // 어절 폭 **누적합**. 예전엔 widthOf 가 매번 slice+join 해서 다시 쟀는데, DP 가
    // 같은 구간을 줄 수(k)마다 되풀이해 재는 바람에 시편 119편이 3.2초 걸렸다.
    // 어절 폭을 한 번씩만 재고 누적합으로 구간 폭을 O(1) 에 얻는다(측정 O(n)).
    // 공백 폭은 "가 가" 와 "가가" 의 차이로 한 번 구한다 — 글꼴마다 다르기 때문.
    const wW = new Array(n);
    for (let i = 0; i < n; i++) wW[i] = measure(words[i]);
    const space = Math.max(0, measure("가 가") - measure("가가"));
    const pre = new Array(n + 1);
    pre[0] = 0;
    for (let i = 0; i < n; i++) pre[i + 1] = pre[i] + wW[i];
    const widthOf = (i, j) => pre[j + 1] - pre[i] + space * (j - i);

    // best[i][k] = 어절 i 부터 끝까지를 k 줄로 담을 때의 최소 비용
    // 키는 문자열로 — i*100+k 같은 산술 키는 줄 수가 100을 넘는 순간 조용히 충돌한다.
    const memo = new Map();
    const key = (i, k) => i + ":" + k;

    function solve(i, k) {
      if (i === n) return { cost: 0, next: -1 };
      if (k === 0) return null;                 // 줄이 모자람
      const kk = key(i, k);
      if (memo.has(kk)) return memo.get(kk);
      let best = null;
      for (let j = i; j < n; j++) {
        const w = widthOf(i, j);
        // 한 어절이 통째로 폭을 넘으면 어쩔 수 없이 허용(어절 중간은 절대 안 끊는다).
        if (w > maxWidth && j > i) break;
        const rest = solve(j + 1, k - 1);
        if (rest) { addCandidate(i, j, w, rest); }
        // 문장이 여기서 끝났다면 이 줄은 여기까지다 — 더 붙이면 한 줄에 두 문장이 섞인다.
        if (hard[j]) break;
      }
      memo.set(kk, best);
      return best;

      function addCandidate(i, j, w, rest) {
        const isLast = j === n - 1;
        let c = RAGGED(Math.max(0, maxWidth - w), maxWidth) + rest.cost;
        // ⚠️ `|| TIER_PENALTY[4]` 로 쓰면 안 된다 — 최상급(CLAUSE)의 벌점이 0 이고
        //    0 은 falsy 라서 곧바로 1200(최악)으로 바뀐다. 즉 '가장 자연스러운 자리'가
        //    '가장 비싼 자리'가 되어 엔진의 목적이 정확히 뒤집힌다(실제로 그랬다).
        if (!isLast) {
          const pen = TIER_PENALTY[tiers[j]];
          c += (pen === undefined ? TIER_PENALTY[TIER.WORD] : pen);
        }
        // 문장 하나가 통째로 한 줄이면 짧아도 고아가 아니다 — 강제로 끊긴 결과이므로
        // 벌점을 물리면 DP 가 그 줄을 피하려고 엉뚱한 선택을 한다.
        const forced = j > 0 && hard[j - 1];
        if (isLast && j === i && n > 1 && !forced) c += WIDOW_PENALTY;
        if (!best || c < best.cost) best = { cost: c, next: j };
      }
    }

    // 줄 수를 늘려가며 최초로 담기는 구성을 찾되, 그 줄 수에서의 최적을 쓴다.
    // 줄이 적을수록 글자를 크게 쓸 수 있으므로 적은 쪽을 먼저 시도한다.
    //
    // ⚠️ 여기서 memo 를 비우면 안 된다. 키가 (i, k) 라 k 가 달라도 하위 문제는 그대로
    //    재사용되는데, 매 k 마다 지우면 DP 를 통째로 다시 돌게 된다(21줄짜리 본문이면
    //    21번). 시편 119편이 800ms 걸리던 진짜 이유가 이것이었다.
    //
    // 시작 k 도 바닥값부터 — 전체 폭을 한 줄 폭으로 나눈 값과 강제 줄바꿈 개수보다
    // 적은 줄로는 애초에 담을 수 없으므로, 그 아래는 시도할 가치가 없다.
    let kMin = Math.max(1, Math.ceil(widthOf(0, n - 1) / Math.max(1, maxWidth)));
    for (let i = 0; i < n - 1; i++) if (hard[i]) kMin++;
    for (let k = Math.min(kMin, maxLines); k <= maxLines; k++) {
      const r = solve(0, k);
      if (!r) continue;
      const lines = [];
      let i = 0, kk = k;
      while (i < n) {
        const step = solve(i, kk);
        if (!step) return null;
        lines.push(words.slice(i, step.next + 1).join(" "));
        i = step.next + 1;
        kk--;
      }
      return { lines, cost: r.cost };
    }
    return null;
  }

  /**
   * 절 목록을 그대로 받아 줄 나눔(토큰화 + 배치).
   * @returns {{lines:string[], cost:number}|null}
   */
  function plan(verses, o) {
    const { words, tiers, hard } = tokenize(verses);
    return layout(words, tiers, Object.assign({}, o, { hard }));
  }

  /**
   * 글자 크기까지 자동으로 맞춘다 — 화면을 알맞게 채우는 가장 큰 크기를 이분 탐색.
   * @param {object} o
   *   measureAt(text, size) -> number   그 크기에서의 렌더 폭
   *   maxWidth, maxHeight               들어가야 할 상자
   *   lineHeight                        행간 배수(예: 1.35)
   *   min, max                          글자 크기 탐색 범위(px)
   *   maxLines                          줄 수 상한(선택)
   * @returns {{size:number, lines:string[]}|null}
   */
  function fit(verses, o) {
    const lo0 = o.min || 12, hi0 = o.max || 200;
    const lh = o.lineHeight || 1.35;
    const tryAt = (size) => {
      const maxLines = Math.max(1, Math.min(o.maxLines || 99,
        Math.floor(o.maxHeight / (size * lh))));
      return plan(verses, {
        measure: (t) => o.measureAt(t, size),
        maxWidth: o.maxWidth,
        maxLines,
      });
    };
    let lo = lo0, hi = hi0, bestSize = null, bestLines = null;
    // 정수 px 단위 이분 탐색 — 들어가는 가장 큰 크기.
    while (lo <= hi) {
      const mid = Math.floor((lo + hi) / 2);
      const r = tryAt(mid);
      if (r) { bestSize = mid; bestLines = r.lines; lo = mid + 1; }
      else { hi = mid - 1; }
    }
    if (bestSize == null) {
      // 최소 크기로도 안 들어감 — 호출자가 슬라이드를 쪼개야 한다는 신호.
      return null;
    }
    return { size: bestSize, lines: bestLines };
  }

  /**
   * 한 화면에 안 들어가는 긴 구절을 여러 장으로 나눈다.
   *
   * 왜 필요한가: 시편 119편처럼 절이 많은 본문을 담으면 한 화면에 우겨넣느라 글자가
   * 읽을 수 없을 만큼 작아진다. 투사 화면에서 '작아서 안 보이는 것'은 '안 띄운 것'과
   * 같으므로, 읽을 수 있는 최소 크기(minSize)를 바닥으로 두고 그 아래로 내려가야 할
   * 상황이면 장을 넘긴다.
   *
   * 페이지는 **절 경계에서만** 나눈다 — 한 절이 두 장에 걸치면 읽는 흐름이 끊긴다.
   *
   * 글자 크기는 장마다 따로 맞춘다. 전 장을 같은 크기로 맞추면 가장 빡빡한 장에
   * 전체가 끌려가 나머지가 다 작아진다(발표에서는 장마다 꽉 채우는 편이 잘 읽힌다).
   *
   * @returns {Array<{lines:string[], size:number, verses:Array}>} 최소 1장
   */
  function paginate(verses, o) {
    const list = (verses || []).slice();
    if (!list.length) return [];
    const minSize = o.minSize || 28;          // 투사 기준 '읽을 수 있는' 바닥
    const floor = o.min || 12;                // 그래도 안 되면 여기까지 양보
    const pages = [];
    let start = 0;

    // 페이지 경계를 이분 탐색하면 후보 구간이 겹쳐 같은 어절을 같은 크기로 되풀이해
    // 재게 된다(시편 119편에서 measure 9만 회). 호출 한 번 수명의 캐시로 없앤다 —
    // 수명이 짧아 글꼴이 바뀌어도 낡은 값이 남지 않는다.
    const memo = new Map();
    // ⚠️ 원본을 먼저 붙잡아 둔다. 아래에서 o 를 갈아끼우므로 o.measureAt 을 그대로
    //    참조하면 캐시 함수가 제 자신을 불러 무한 재귀가 된다(실제로 밟았다).
    const rawMeasureAt = o.measureAt;
    const cachedMeasureAt = function (t, size) {
      const k = size + " " + t;
      let w = memo.get(k);
      if (w === undefined) { w = rawMeasureAt(t, size); memo.set(k, w); }
      return w;
    };
    o = Object.assign({}, o, { measureAt: cachedMeasureAt });

    while (start < list.length) {
      // 들어가는 가장 큰 묶음을 찾는다. '절이 적을수록 쉽다'가 단조라서 이분 탐색이
      // 성립한다 — 절마다 시도하면 시편 119편(176절)에서 수백 번 재게 된다.
      let lo = start + 1, hi = list.length, best = null, bestEnd = start + 1;
      while (lo <= hi) {
        const mid = Math.floor((lo + hi) / 2);
        const r = fit(list.slice(start, mid), Object.assign({}, o, { min: minSize }));
        if (r) { best = r; bestEnd = mid; lo = mid + 1; }
        else { hi = mid - 1; }
      }
      if (!best) {
        // 절 하나조차 최소 크기로 안 들어간다 → 그 절만 담고 바닥까지 양보한다.
        // (넘치더라도 보여주는 편이 아무것도 안 띄우는 것보다 낫다.)
        best = fit(list.slice(start, start + 1),
                   Object.assign({}, o, { min: floor })) ||
               { size: floor, lines: (plan(list.slice(start, start + 1), {
                   measure: function (t) { return o.measureAt(t, floor); },
                   maxWidth: o.maxWidth, maxLines: 999,
                 }) || { lines: [] }).lines };
        bestEnd = start + 1;
      }
      pages.push({ lines: best.lines, size: best.size,
                   verses: list.slice(start, bestEnd) });
      start = bestEnd;
    }
    return pages;
  }

  return { plan, layout, tokenize, fit, paginate, wordTier, sentenceEnd,
           TIER, TIER_PENALTY };
})();
