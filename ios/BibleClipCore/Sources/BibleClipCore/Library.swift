import Foundation

/// [Library.buildOutput] 의 결과 — Python 사전과 같은 꼴.
public enum Output {
    case keyword(String)
    case reference(bookNum: Int, chapter: Int, verses: [Int], shortName: String, text: String, nParts: Int)

    /// Python build_output 사전 그대로(JSON).
    public var json: [String: Any] {
        switch self {
        case .keyword(let k):
            return ["kind": "keyword", "keyword": k]
        case let .reference(b, c, vs, name, text, n):
            return ["kind": "reference", "book_num": b, "chapter": c, "verses": vs,
                    "short_name": name, "text": text, "n_parts": n]
        }
    }
}

/// 화면과 상관없는 핵심: 넣어 둔 역본 + 설정 + 참조 → 출력 글.
/// bibleclip/core/library.py 의 읽기·서식 절반 — Library.kt 이식.
///
/// [aliasOverrides] 는 aliases_override.json ({별칭: 책 번호 또는 이름}) 을 준다.
public final class Library {
    public let tables: Tables
    public let settings: Settings
    private let aliasOverrides: () -> [String: Any]
    public let text: TextUtils
    public let engine: Engine
    /// 넣은 순서를 지킨다(데스크톱 훑기와 같다).
    public private(set) var order: [String] = []
    public private(set) var dbs: [String: BibleDb] = [:]

    /// 유의어 사전(web/data/bible_synonyms.json), nil = 넓히지 않음. 직접 넣거나
    /// [synonymsLoader] 로 처음 쓸 때 읽게 한다(325KB JSON 을 앱 시작에서 빼려고).
    public var synonymsLoader: (() -> Synonyms?)?
    private var synonymsValue: Synonyms?
    public var synonyms: Synonyms? {
        get {
            if synonymsValue == nil, let load = synonymsLoader {
                synonymsLoader = nil
                synonymsValue = load()
            }
            return synonymsValue
        }
        set { synonymsValue = newValue }
    }
    private var searches: [String: VerseSearch] = [:]

    private var aliasKey: Set<String>?
    private var aliases: [String: Int] = [:]

    public init(_ tables: Tables, _ settings: Settings, aliasOverrides: @escaping () -> [String: Any] = { [:] }) {
        self.tables = tables
        self.settings = settings
        self.aliasOverrides = aliasOverrides
        text = TextUtils(tables)
        engine = Engine(tables, text)
    }

    /// 역본을 넣는다 — 같은 이름은 먼저 넣은 것이 이긴다.
    @discardableResult
    public func add(_ db: BibleDb) -> Bool {
        if dbs[db.name] != nil { return false }
        dbs[db.name] = db
        order.append(db.name)
        return true
    }

    /// 역본을 다 넣은 뒤의 Library.load_settings 검사: 출력/보기 목록이 비면 한국어 역본으로,
    /// 보기 순서에는 모든 역본, book_name 은 long_ko/short_ko, 글자 크기 8–400.
    public func validateSettings() {
        let fallback: [String] = ["KRV", "NRKV", "KNRSV"].first { dbs[$0] != nil }.map { [$0] }
            ?? order.first.map { [$0] } ?? []

        let out = settings.strings("output_order").filter { dbs[$0] != nil }
        settings["output_order"] = out.isEmpty ? fallback : out

        var viewer = settings.strings("viewer_versions").filter { dbs[$0] != nil }
        if viewer == ["KNRSV"] && dbs["KRV"] != nil { viewer = ["KRV"] }
        settings["viewer_versions"] = viewer.isEmpty ? fallback : viewer

        var vorder = settings.strings("viewer_version_order").filter { dbs[$0] != nil }
        for v in order where !vorder.contains(v) { vorder.append(v) }
        settings["viewer_version_order"] = vorder

        settings["book_name"] = settings.str("book_name", "short_ko").hasPrefix("long") ? "long_ko" : "short_ko"
        let size: Int
        switch JV(settings["viewer_font_size"]) {
        case .int(let i): size = i
        case .double(let d) where d.isFinite: size = Int(d)
        default: size = Int(settings.str("viewer_font_size", "11")) ?? 11
        }
        settings["viewer_font_size"] = min(max(size, 8), 400)
    }

    /// 한 역본의 검색 엔진(색인은 처음 쓸 때 만든다).
    public func searcher(_ version: String) -> VerseSearch? {
        guard let db = dbs[version] else { return nil }
        if let s = searches[version] { return s }
        let s = VerseSearch(db, text)
        searches[version] = s
        return s
    }

    /// 기본 검색 역본: 첫 보기 역본, 없으면 한국어 역본, 없으면 첫 역본 (routes._search_version).
    public func searchVersion() -> String? {
        if let p = primaryVersion(), dbs[p] != nil { return p }
        return ["KRV", "NRKV", "KNRSV"].first { dbs[$0] != nil } ?? order.first
    }

    /// 브리지의 검색 답 — webui/routes/bible.py BibleRoutes.search 이식:
    /// {keyword, version, display, mode, matched_tokens, highlight_tokens, expanded, hits}.
    /// matched_tokens = 조사 뗀 질의(강조가 찾는 것), highlight_tokens 는 함께 찾은 유의어까지.
    public func searchReply(_ keyword: String?, _ version: String?, limit: Int = 200, mode: String? = "and") -> [String: Any] {
        var kw = (keyword ?? "").trimmed
        while kw.hasPrefix("#") { kw.removeFirst() }
        kw = kw.trimmed
        let m = mode?.lowercased() == "or" ? "or" : "and"
        var matched = Korean.tokenize(kw)
        if matched.isEmpty && !kw.isEmpty { matched = [kw] }
        var reply: [String: Any] = ["keyword": kw, "mode": m, "matched_tokens": matched]
        let ver: String? = (version.map { !$0.isEmpty && dbs[$0] != nil } ?? false) ? version : searchVersion()
        guard !kw.isEmpty, let v = ver, let db = dbs[v] else {
            reply["version"] = kw.isEmpty ? NSNull() : (ver ?? NSNull()) as Any
            reply["display"] = ""
            reply["highlight_tokens"] = matched
            reply["expanded"] = [String: Any]()
            reply["hits"] = [Any]()
            return reply
        }
        let syn = settings.truthy("search_synonyms", true) ? synonyms : nil
        let rows = searcher(v)!.search(kw, mode: m, limit: limit, synonyms: syn)
        let expanded = syn?.expandAll(matched) ?? []
        var hl = matched
        for (_, alts) in expanded { for a in alts where !hl.contains(a) { hl.append(a) } }
        var exp: [String: Any] = [:]
        for (k, alts) in expanded { exp[k] = alts }
        reply["version"] = v
        reply["display"] = db.displayName
        reply["highlight_tokens"] = hl
        reply["expanded"] = exp
        reply["hits"] = rows.map { h -> [String: Any] in
            ["book": h.book, "chapter": h.chapter, "verse": h.verse,
             "short": db.books[h.book]?.short ?? "?", "text": h.text]
        }
        return reply
    }

    public func primaryVersion() -> String? {
        settings.strings("viewer_versions").first { dbs[$0] != nil } ?? order.first
    }

    /// {정규화한 책 이름: 책 번호} — 넣은 모든 역본 + 사용자 별칭.
    public func bookAliases() -> [String: Int] {
        let names = Set(order)
        if aliasKey != names {
            var amap: [String: Int] = [:]
            for name in order {
                for (bn, short, long) in dbs[name]!.bookList {
                    for nm in [short, long] {
                        let k = Engine.normBook(nm)
                        if !k.isEmpty && k != "?" && amap[k] == nil { amap[k] = bn }
                    }
                }
            }
            mergeAliasOverrides(&amap)
            aliases = amap
            aliasKey = names
        }
        return aliases
    }

    /// 별칭 캐시 비우기(aliases_override.json 이 바뀐 뒤).
    public func invalidateAliases() { aliasKey = nil }

    private func mergeAliasOverrides(_ amap: inout [String: Int]) {
        for (raw, v) in aliasOverrides() {
            if raw.hasPrefix("_") { continue }
            let key = Engine.normBook(raw)
            if key.isEmpty { continue }
            var bn: Int?
            switch JV(v) {
            case .int(let i): bn = i
            case .string(let s0):
                let s = s0.trimmed
                if !s.isEmpty && s.unicodeScalars.allSatisfy({ $0.properties.numericType == .decimal }) {
                    bn = pint(s)
                } else {
                    let k = Engine.normBook(s)
                    bn = amap[k] ?? tables.englishBookMap[k]
                }
            default: bn = nil
            }
            if let bn = bn { amap[key] = bn }
        }
    }

    public func parseReference(_ text: String) -> [Ref] { engine.parseReference(text, bookAliases()) }

    /// 클립보드/선택 글 → 키워드('#…') · 참조 · nil.
    public func buildOutput(_ input: String?) -> Output? {
        let s = (input ?? "").trimmed
        if s.isEmpty { return nil }
        if s.hasPrefix("#") {
            let keyword = String(s.dropFirst()).trimmed
            return keyword.isEmpty ? nil : .keyword(keyword)
        }
        guard let ref = parseReference(s).first else { return nil }
        let (out, nParts) = formatReference(ref.book.num, ref.chapter, ref.verses)
        if out.isEmpty { return nil }
        let name = displayBookName(ref.book.num) ?? ref.book.short
        return .reference(bookNum: ref.book.num, chapter: ref.chapter, verses: ref.verses,
                          shortName: name, text: out, nParts: nParts)
    }

    /// 장바구니 한꺼번에 복사 (api.copy_references): {book|book_num, chapter, verses} 마다
    /// 한 번 복사와 같은 서식, 빈 줄로 잇고 순서를 지킨다. 값이 잘못된 항목은 통째로 건너뛴다.
    public func copyReferences(_ items: [Any]?, _ order: [String]?) -> (String, Int) {
        var blocks: [String] = []
        for raw in items ?? [] {
            guard let it = raw as? [String: Any] else { continue }
            guard let book = pyInt(it["book"] != nil ? it["book"] : it["book_num"]),
                  let chapter = pyInt(it["chapter"]) else { continue }
            let vs = (it["verses"] as? [Any] ?? []).map { pyInt($0) }
            if vs.contains(where: { $0 == nil }) { continue }
            let (text, _) = formatReference(book, chapter, vs.compactMap { $0 }, order)
            if !text.isEmpty { blocks.append(text) }
        }
        return (blocks.joined(separator: "\n\n"), blocks.count)
    }

    /// 첫 출력 역본의 책 이름, 정식/약칭 설정대로.
    public func displayBookName(_ bookNum: Int, _ order: [String]? = nil) -> String? {
        let o = order ?? settings.strings("output_order")
        guard let primary = o.first ?? primaryVersion(), let b = dbs[primary]?.books[bookNum] else { return nil }
        let name = settings.str("book_name", "short").hasPrefix("long") ? b.long : b.short
        return name.isEmpty || name == "?" ? nil : name
    }

    /// 참조 하나를 [order](기본: output_order) 역본마다. 빈 [verses] = 장 전체.
    /// (글, 부분 수) — 맞는 것이 없으면 ("", 0).
    public func formatReference(_ bookNum: Int, _ chapter: Int, _ verses: [Int],
                                _ order: [String]? = nil) -> (String, Int) {
        let o = order ?? settings.strings("output_order")
        if o.isEmpty { return ("", 0) }
        let fmt = Formatter(settings)
        var cols: [(BibleDb, [(Int, String)])] = []
        for ver in o {
            guard let db = dbs[ver], db.books[bookNum] != nil else { continue }
            let data = (verses.isEmpty ? db.getVerses(bookNum, chapter)
                        : verses.map { ($0, db.getVerseText(bookNum, chapter, $0)) }).filter { !$0.1.isEmpty }
            if !data.isEmpty { cols.append((db, data)) }
        }
        if cols.isEmpty { return ("", 0) }

        let tmpl = settings.str("custom_format_template", "")
        if settings.truthy("custom_format_enabled") && !tmpl.trimmed.isEmpty &&
            (tmpl.contains("{content2}") || tmpl.contains("{version2}")) && cols.count >= 2 {
            return (fmt.formatParallel(bookNum, chapter, cols[0], cols[1]), 2)
        }
        let parts = cols.map { db, data in
            fmt.formatVersionOutput(db, bookNum, chapter, data.map { $0.0 }, data)
        }.filter { !$0.isEmpty }
        if parts.isEmpty { return ("", 0) }
        return (parts.joined(separator: "\n\n"), parts.count)
    }
}
