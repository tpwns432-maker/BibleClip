import Foundation

/// 한 역본의 절들 → 출력 글, 사용자의 서식 설정대로 — bibleclip/core/formatter.py 이식
/// (Formatter.kt 와 같다). tests/golden/format.json 이 고정한다.
public final class Formatter {
    private let s: Settings

    public init(_ settings: Settings) { s = settings }

    public func formatVersionOutput(_ db: BibleDb, _ bookNum: Int, _ chapter: Int, _ verses: [Int],
                                    _ verseData: [(Int, String)]) -> String {
        // 역본마다 제 책 이름을 쓴다(KRV 룻기 / ESV Ruth).
        let (dbShort, dbLong) = db.books[bookNum].map { ($0.short, $0.long) } ?? ("?", "?")
        let bookDisplay = useLong() ? dbLong : dbShort

        let verseList = verses.isEmpty ? "" : Formatter.formatVerseList(verses, s.str("range_symbol", "-"))
        let ref: String
        if s.str("chapter_verse_format", "") == "korean" {
            ref = verseList.isEmpty ? "\(bookDisplay) \(chapter)장" : "\(bookDisplay) \(chapter)장 \(verseList)절"
        } else {
            ref = verseList.isEmpty ? "\(bookDisplay) \(chapter)" : "\(bookDisplay) \(chapter):\(verseList)"
        }

        let header = s.truthy("show_version_header", true) ? "[\(db.name)]" : ""
        let body = buildBody(verseData, chapter)

        // FEAT-02 사용자 틀을 켜면 표준 조립 대신 쓴다.
        let tmpl = s.str("custom_format_template", "")
        if s.truthy("custom_format_enabled") && !tmpl.trimmed.isEmpty {
            return Formatter.applyTemplate(tmpl, dbLong, dbShort, chapter, verseList, body, db.name)
        }

        if s.truthy("hide_reference") {
            return header.isEmpty ? body : "\(header)\n\(body)"
        }

        let refDisplay: String
        switch s.str("bracket_style", "none") {
        case "[]": refDisplay = "[\(ref)]"
        case "()": refDisplay = "(\(ref))"
        default: refDisplay = ref
        }
        let sep = s.str("ref_body_separator", " ")
        if s.str("ref_position", "before") == "before" {
            return header.isEmpty ? "\(refDisplay)\(sep)\(body)" : "\(header) \(refDisplay)\(sep)\(body)"
        }
        return header.isEmpty ? "\(body)\(sep)\(refDisplay)" : "\(header) \(body)\(sep)\(refDisplay)"
    }

    /// FEAT-05: 앞의 두 역본을 {content}/{content2} 로 한 덩어리에.
    public func formatParallel(_ bookNum: Int, _ chapter: Int,
                               _ col1: (BibleDb, [(Int, String)]), _ col2: (BibleDb, [(Int, String)])) -> String {
        let (db1, vd1) = col1
        let (db2, vd2) = col2
        let (short1, long1) = db1.books[bookNum].map { ($0.short, $0.long) } ?? ("?", "?")
        let verses1 = vd1.map { $0.0 }
        let verseList = verses1.isEmpty ? "" : Formatter.formatVerseList(verses1, s.str("range_symbol", "-"))
        return Formatter.applyTemplate(s.str("custom_format_template", ""), long1, short1, chapter, verseList,
                                       buildBody(vd1, chapter), db1.name, buildBody(vd2, chapter), db2.name)
    }

    private func buildBody(_ verseData: [(Int, String)], _ chapter: Int) -> String {
        if s.str("output_mode", "") == "newline" && verseData.count > 1 {
            let cv = s.truthy("newline_show_cv")
            return verseData.map { cv ? "\(chapter):\($0.0) \($0.1)" : "\($0.0) \($0.1)" }.joined(separator: "\n")
        }
        // 한 줄 — 이어지지 않는 절 묶음 사이는 ' // ' (1-2,4-6).
        var out = ""
        var prev: Int?
        for (v, t) in verseData {
            if let p = prev { out += v != p + 1 ? " // " : " " }
            out += t
            prev = v
        }
        return out
    }

    private func useLong() -> Bool { s.str("book_name", "short").hasPrefix("long") }

    private static let tag = Rx(#"\{(\w+)\}"#)

    /// 모르는 {꼬리표} 는 그대로 둔다(오타가 보이게).
    public static func applyTemplate(_ tmpl: String, _ bookFull: String, _ bookShort: String, _ chapter: Int,
                                     _ verseList: String, _ content: String, _ version: String,
                                     _ content2: String = "", _ version2: String = "") -> String {
        let repl = [
            "book_full": bookFull, "book_short": bookShort,
            "chap": String(chapter), "verse": verseList,
            "content": content, "version": version,
            "content2": content2, "version2": version2,
        ]
        return tag.replace(tmpl) { m in repl[m.g(1)!] ?? m.g(0)! }
    }

    /// [16,17,18,20] → "16-18,20".
    public static func formatVerseList(_ verses: [Int], _ rangeSym: String = "-") -> String {
        guard var start = verses.first else { return "" }
        var end = start
        var ranges: [String] = []
        for v in verses.dropFirst() {
            if v == end + 1 {
                end = v
            } else {
                ranges.append(start != end ? "\(start)\(rangeSym)\(end)" : "\(start)")
                start = v
                end = v
            }
        }
        ranges.append(start != end ? "\(start)\(rangeSym)\(end)" : "\(start)")
        return ranges.joined(separator: ",")
    }
}
