import Foundation

/// bibleclip/korean.py 이식 — 색인과 질의가 함께 쓰는 단 하나의 낱말 나누개: 꼬리표 빼기,
/// 빈칸으로 나누기, 가장자리 문장부호 떼기, 끝 조사 하나 떼기(긴 것부터), 불용어 버리기.
public enum Korean {
    private static let particles = [
        "으로서", "으로써", "에게서", "에서", "에게", "으로", "이라",
        "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만",
    ].enumerated().sorted { a, b in   // 길이 내림차순, 같은 길이는 원래 순서(안정 정렬)
        a.element.scalarCount != b.element.scalarCount
            ? a.element.scalarCount > b.element.scalarCount : a.offset < b.offset
    }.map { $0.element }
    private static let stopwords: Set<String> = ["그", "또", "또한", "및", "곧", "그리고", "그러나", "하지만", "그것", "이것", "저것"]
    private static let edgePunct = Set(" \t\r\n.,;:!?'\"()[]{}「」『』《》〈〉·…“”‘’~—".unicodeScalars)
    private static let tag = Rx("<[^>]+>")
    private static let spaces = Rx(#"\s+"#)

    public static func stripParticle(_ token: String) -> String {
        let n = token.scalarCount
        for p in particles where token.scalarHasSuffix(p) && n > p.scalarCount {
            return token.scalarDropLast(p.scalarCount)
        }
        return token
    }

    public static func tokenize(_ text: String?) -> [String] {
        guard let text = text, !text.isEmpty else { return [] }
        var out: [String] = []
        for raw in spaces.split(tag.replace(text, " ")) {
            var tok = raw.strip(edgePunct)
            if tok.isEmpty { continue }
            tok = stripParticle(tok)
            if tok.isEmpty || stopwords.contains(tok) { continue }
            out.append(tok)
        }
        return out
    }
}

/// bibleclip/data/synonyms.py 이식 — 고어↔현대어 검색 넓히기
/// (web/data/bible_synonyms.json, {map: {낱말: [[대안, 확신도], ...]}}).
/// 파일이 없거나 깨졌으면 빈 사전: 검색은 넓히지 않고 그대로 된다.
public final class Synonyms {
    private let map: [String: [(String, Double)]]

    public static let maxExpand = 3
    public static let asset = "web/data/bible_synonyms.json"

    public init(json: String?) {
        var m: [String: [(String, Double)]] = [:]
        if let root = JSON.parse(json ?? "{}") as? [String: Any], let mp = root["map"] as? [String: Any] {
            for (k, v) in mp {
                var alts: [(String, Double)] = []
                for e in v as? [Any] ?? [] {
                    switch JV(e) {
                    case .array(let a) where a.count >= 2:
                        let conf: Double
                        switch JV(a[1]) {
                        case .int(let i): conf = Double(i)
                        case .double(let d): conf = d
                        case .string(let s): conf = Double(s) ?? .nan
                        default: conf = .nan
                        }
                        alts.append((a[0] as? String ?? jsonText(a[0]), conf))
                    case .string(let s):
                        alts.append((s, 1.0))
                    default: break
                    }
                }
                if !alts.isEmpty { m[k] = alts }
            }
        }
        map = m
    }

    /// [(대안, 확신도)] 파일 순서, 최대 [limit] 개.
    public func expand(_ token: String, _ limit: Int = Synonyms.maxExpand) -> [(String, Double)] {
        token.isEmpty ? [] : Array((map[token] ?? []).prefix(limit))
    }

    /// {낱말: [대안]} — 대안이 있는 낱말만, 강조 표시용. 순서는 [tokens] 순서.
    public func expandAll(_ tokens: [String], _ limit: Int = Synonyms.maxExpand) -> [(String, [String])] {
        var out: [(String, [String])] = []
        for t in tokens {
            let alts = expand(t, limit).map { $0.0 }
            if !alts.isEmpty {
                if let i = out.firstIndex(where: { $0.0 == t }) { out[i].1 = alts } else { out.append((t, alts)) }
            }
        }
        return out
    }
}

/// 검색 결과 한 절: 책/장/절 + 정리한 본문.
public struct Hit {
    public let book: Int, chapter: Int, verse: Int, text: String
}

/// BibleDB.search (bibleclip/data/bible_db.py) 를 한 역본에 — Search.kt 의 VerseSearch 이식:
///   1. 조사 뗀 역색인 위 BM25, 유의어 넓히기(대안은 확신도만큼 가중, 질의 낱말마다 가장 좋은 것);
///   2. 없으면 → 띄어쓰기 무시 그대로 찾기;
///   3. 그래도 없으면 → 세 글자 조각 겹침 ≥ 0.7 (오타 허용).
/// tests/golden/search.json 이 고정한다.
public final class VerseSearch {
    private final class Verse {
        let key: Int64, book: Int, chapter: Int, verse: Int
        let clean: String
        let tokens: [String]
        lazy var despaced: String = VerseSearch.despace(clean)

        init(key: Int64, book: Int, chapter: Int, verse: Int, clean: String, tokens: [String]) {
            self.key = key; self.book = book; self.chapter = chapter; self.verse = verse
            self.clean = clean; self.tokens = tokens
        }
    }

    private let db: BibleDb
    private let text: TextUtils

    public init(_ db: BibleDb, _ text: TextUtils) {
        self.db = db
        self.text = text
    }

    private lazy var verses: [Verse] = db.allVerses().map { r in
        let clean = text.cleanText(r.text)
        return Verse(key: VerseSearch.key(r.book, r.chapter, r.verse), book: r.book, chapter: r.chapter,
                     verse: r.verse, clean: clean, tokens: Korean.tokenize(clean))
    }

    private lazy var byKey: [Int64: Verse] = {
        var m: [Int64: Verse] = [:]
        for v in verses { m[v.key] = v }
        return m
    }()

    /// 원형 낱말 → 절 키 (BM25 색인). 부분 일치로 훑으므로 배열로 둔다.
    private lazy var inverted: [(String, Set<Int64>)] = {
        var idx: [String: Set<Int64>] = [:]
        for v in verses { for t in v.tokens { idx[t, default: []].insert(v.key) } }
        return idx.map { ($0.key, $0.value) }
    }()

    /// (N, avgdl) — BM25 길이 정규화.
    private lazy var stats: (Int, Double) = {
        let n = max(verses.count, 1)
        let total = verses.reduce(0) { $0 + $1.tokens.count }
        let avg = Double(total) / Double(n)
        return (n, avg == 0 ? 1.0 : avg)
    }()

    /// 색인을 지금 만든다(주 스레드 밖에서) — 첫 검색이 바로 되게.
    public func warm() {
        _ = inverted.count
        _ = stats
    }

    public func search(_ keyword: String?, mode: String = "and", limit: Int = 300, synonyms: Synonyms? = nil,
                       fuzzyThreshold: Double = 0.7) -> [Hit] {
        let kw = (keyword ?? "").trimmed
        if kw.isEmpty { return [] }
        let bm = bm25(kw, mode, limit, synonyms)
        if !bm.isEmpty { return bm }
        let qd = VerseSearch.despace(kw)
        if qd.isEmpty { return [] }
        let exact = verses.filter { $0.despaced.has(qd) }
        if !exact.isEmpty { return exact.prefix(limit).map { hit($0) } }
        let qtri = VerseSearch.trigrams(qd)
        if qtri.isEmpty { return [] }
        var scored: [(Double, Verse)] = []
        for v in verses {
            let tri = VerseSearch.trigrams(v.despaced)
            if tri.isEmpty { continue }
            let inter = qtri.filter { tri.contains($0) }.count
            if inter == 0 { continue }
            let score = Double(inter) / Double(qtri.count)
            if score >= fuzzyThreshold { scored.append((score, v)) }
        }
        return scored.sorted { $0.0 != $1.0 ? $0.0 > $1.0 : $0.1.key < $1.1.key }
            .prefix(limit).map { hit($0.1) }
    }

    private func hit(_ v: Verse) -> Hit { Hit(book: v.book, chapter: v.chapter, verse: v.verse, text: v.clean) }

    private func termKeys(_ term: String) -> Set<Int64> {
        var out = Set<Int64>()
        for (k, keys) in inverted where k.has(term) { out.formUnion(keys) }
        return out
    }

    private struct Member {
        let term: String, weight: Double, keys: Set<Int64>, idf: Double
    }

    private func bm25(_ keyword: String, _ mode: String, _ limit: Int, _ syn: Synonyms?) -> [Hit] {
        let (n, avgdl) = stats
        let tokens = Korean.tokenize(keyword)
        if tokens.isEmpty { return [] }

        var groups: [[Member]] = []
        for t in tokens {
            var members: [(String, Double)] = [(t, 1.0)]
            if let syn = syn {
                let span = VerseSearch.synWMax - VerseSearch.synWMin
                for (alt, c) in syn.expand(t) {
                    let conf = c < 0.0 ? 0.0 : (c > 1.0 ? 1.0 : c)
                    members.append((alt, VerseSearch.synWMin + span * conf))
                }
            }
            let info: [Member] = members.compactMap { term, w in
                let keys = termKeys(term)
                if keys.isEmpty { return nil }
                let idf = log(1.0 + (Double(n - keys.count) + 0.5) / (Double(keys.count) + 0.5))
                return Member(term: term, weight: w, keys: keys, idf: idf)
            }
            if !info.isEmpty { groups.append(info) }
        }
        if groups.isEmpty { return [] }

        let gsets = groups.map { g in g.reduce(into: Set<Int64>()) { $0.formUnion($1.keys) } }
        let cands: Set<Int64> = mode == "or"
            ? gsets.reduce(into: Set<Int64>()) { $0.formUnion($1) }
            : gsets.dropFirst().reduce(gsets[0]) { $0.intersection($1) }
        if cands.isEmpty { return [] }

        var scored: [(Double, Int64)] = []
        for key in cands {
            let toks = byKey[key]?.tokens ?? []
            let dl = toks.isEmpty ? 1 : toks.count
            let norm = VerseSearch.k1 * (1.0 - VerseSearch.b + VerseSearch.b * Double(dl) / avgdl)
            var total = 0.0
            var firsts: [Int] = []
            for g in groups {
                var best = 0.0
                var bestPos: Int?
                for m in g {
                    if !m.keys.contains(key) { continue }
                    var tf = 0
                    var pos: Int?
                    for (i, tk) in toks.enumerated() where tk.has(m.term) {
                        tf += 1
                        if pos == nil { pos = i }
                    }
                    if tf == 0 { continue }
                    let sc = m.weight * m.idf * Double(tf) * (VerseSearch.k1 + 1.0) / (Double(tf) + norm)
                    if sc > best {
                        best = sc
                        bestPos = pos
                    }
                }
                if best != 0.0 {
                    total += best
                    if let p = bestPos { firsts.append(p) }
                }
            }
            if total <= 0.0 { continue }
            if firsts.count >= 2 {
                let span = firsts.max()! - firsts.min()!
                total += VerseSearch.proxWeight * max(0.0, 1.0 - Double(span) / Double(dl))
            }
            scored.append((total, key))
        }
        return scored.sorted { $0.0 != $1.0 ? $0.0 > $1.0 : $0.1 < $1.1 }
            .prefix(limit).map { hit(byKey[$0.1]!) }
    }

    static let k1 = 1.5
    static let b = 0.75
    static let synWMin = 0.15
    static let synWMax = 0.75
    static let proxWeight = 1.2

    private static let spaces = Rx(#"\s+"#)
    static func despace(_ s: String) -> String { spaces.replace(s, "") }

    /// 세 글자 조각(짧으면 통째로).
    static func trigrams(_ s: String) -> Set<String> {
        let u = Array(s.unicodeScalars)
        if u.isEmpty { return [] }
        if u.count < 3 { return [s] }
        var out = Set<String>()
        for i in 0...(u.count - 3) {
            var t = String.UnicodeScalarView()
            t.append(contentsOf: u[i..<(i + 3)])
            out.insert(String(t))
        }
        return out
    }

    /// (책, 장, 절) 을 정렬 가능한 수 하나로 — 튜플과 같은 순서.
    static func key(_ b: Int, _ c: Int, _ v: Int) -> Int64 { Int64(b) * 1_000_000 + Int64(c) * 1_000 + Int64(v) }
}
