import Foundation
import SQLite3

/// 저장된 그대로의 절 (표시 꼬리표 포함).
public struct RawVerse {
    public let book: Int, chapter: Int, verse: Int, text: String
}

/// MyBible 형식 성경 하나(.SQLite3: info / books / verses 표) — BibleDb.kt 이식.
/// Android 와 달리 드라이버가 하나(시스템 SQLite)라 추상 클래스로 나누지 않았다.
/// 한 연결을 여러 스레드가 쓰지 않도록, 앱은 엔진 호출을 한 줄(직렬 큐)로 보낸다.
public final class BibleDb {
    public let name: String
    private let text: TextUtils
    private var handle: OpaquePointer?

    /// 읽기 전용으로 연다. 못 열면 throw.
    public init(path: String, text: TextUtils) throws {
        name = BibleDb.nameOf((path as NSString).lastPathComponent)
        self.text = text
        var h: OpaquePointer?
        let rc = sqlite3_open_v2(path, &h, SQLITE_OPEN_READONLY | SQLITE_OPEN_FULLMUTEX, nil)
        if rc != SQLITE_OK {
            sqlite3_close(h)
            throw NSError(domain: "BibleDb", code: Int(rc),
                          userInfo: [NSLocalizedDescriptionKey: "cannot open \(path)"])
        }
        handle = h
    }

    deinit { close() }

    public func close() {
        if let h = handle { sqlite3_close(h) }
        handle = nil
    }

    private static let transient = unsafeBitCast(-1, to: sqlite3_destructor_type.self)

    /// [sql] 의 행들 — 행마다 열 값 목록 (Int64 · Double · String · nil).
    func query(_ sql: String, _ args: Any...) throws -> [[Any?]] {
        guard let h = handle else { throw NSError(domain: "BibleDb", code: -1) }
        var st: OpaquePointer?
        guard sqlite3_prepare_v2(h, sql, -1, &st, nil) == SQLITE_OK else {
            throw NSError(domain: "BibleDb", code: Int(sqlite3_errcode(h)),
                          userInfo: [NSLocalizedDescriptionKey: String(cString: sqlite3_errmsg(h))])
        }
        defer { sqlite3_finalize(st) }
        for (i, a) in args.enumerated() {
            let idx = Int32(i + 1)
            switch a {
            case let v as Int: sqlite3_bind_int64(st, idx, Int64(v))
            case let v as Int64: sqlite3_bind_int64(st, idx, v)
            case let v as Double: sqlite3_bind_double(st, idx, v)
            case let v as String: sqlite3_bind_text(st, idx, v, -1, BibleDb.transient)
            default: sqlite3_bind_null(st, idx)
            }
        }
        var rows: [[Any?]] = []
        let n = sqlite3_column_count(st)
        while true {
            let rc = sqlite3_step(st)
            if rc == SQLITE_DONE { break }
            guard rc == SQLITE_ROW else {
                throw NSError(domain: "BibleDb", code: Int(rc),
                              userInfo: [NSLocalizedDescriptionKey: String(cString: sqlite3_errmsg(h))])
            }
            var row: [Any?] = []
            row.reserveCapacity(Int(n))
            for c in 0..<n {
                switch sqlite3_column_type(st, c) {
                case SQLITE_INTEGER: row.append(sqlite3_column_int64(st, c))
                case SQLITE_FLOAT: row.append(sqlite3_column_double(st, c))
                case SQLITE_NULL: row.append(nil)
                default:
                    if let p = sqlite3_column_text(st, c) {
                        row.append(String(cString: p))
                    } else {
                        row.append(nil)
                    }
                }
            }
            rows.append(row)
        }
        return rows
    }

    public private(set) lazy var info: [String: String] = {
        var m: [String: String] = [:]
        for r in (try? query("SELECT name, value FROM info")) ?? [] {
            m[str(r[0])] = r[1].map { str($0) } ?? ""
        }
        return m
    }()

    public var description: String { info["description"] ?? name }
    public var language: String { info["language"] ?? "ko" }
    public var displayName: String { "\(description) [\(name)]" }
    public var hasStrongs: Bool { (info["strong_numbers"] ?? "").trimmed.lowercased() == "true" }

    /// (책 번호, 약칭, 정식) — 정경 순서.
    public private(set) lazy var bookList: [(Int, String, String)] = {
        ((try? query("SELECT book_number, short_name, long_name FROM books ORDER BY book_number")) ?? []).map {
            (num($0[0]), $0[1].map { str($0) } ?? "", $0[2].map { str($0) } ?? "")
        }
    }()

    public private(set) lazy var books: [Int: (short: String, long: String)] = {
        var m: [Int: (short: String, long: String)] = [:]
        for (bn, s, l) in bookList { m[bn] = (s, l) }
        return m
    }()

    public func getChapters(_ book: Int) -> [Int] {
        ((try? query("SELECT DISTINCT chapter FROM verses WHERE book_number=? ORDER BY chapter", book)) ?? [])
            .map { num($0[0]) }
    }

    /// [(절, 정리한 본문)] — 한 장.
    public func getVerses(_ book: Int, _ chapter: Int) -> [(Int, String)] {
        ((try? query("SELECT verse, text FROM verses WHERE book_number=? AND chapter=? ORDER BY verse",
                     book, chapter)) ?? [])
            .map { (num($0[0]), text.cleanText($0[1].map { str($0) })) }
    }

    /// 모든 절(정경 순서, 원문 그대로) — 검색 색인의 재료.
    public func allVerses() -> [RawVerse] {
        ((try? query("SELECT book_number, chapter, verse, text FROM verses ORDER BY book_number, chapter, verse")) ?? [])
            .map { RawVerse(book: num($0[0]), chapter: num($0[1]), verse: num($0[2]), text: $0[3].map { str($0) } ?? "") }
    }

    /// 한 절의 정리한 본문, 없으면 ''.
    public func getVerseText(_ book: Int, _ chapter: Int, _ verse: Int) -> String {
        guard let r = ((try? query("SELECT text FROM verses WHERE book_number=? AND chapter=? AND verse=?",
                                   book, chapter, verse)) ?? []).first else { return "" }
        return text.cleanText(r[0].map { str($0) })
    }

    /// MyBible 성경으로 열리는가 — info/books/verses 표와 절이 있다 (Library._is_bible_db).
    public func looksLikeBible() -> Bool {
        guard let t = try? query("SELECT name FROM sqlite_master WHERE type='table'") else { return false }
        let tables = Set(t.map { str($0[0]) })
        guard tables.isSuperset(of: ["info", "books", "verses"]) else { return false }
        return !((try? query("SELECT 1 FROM verses LIMIT 1")) ?? []).isEmpty
    }

    /// 역본 이름 = 확장자를 뺀 파일 이름 ('KJV+.SQLite3' → 'KJV+').
    public static func nameOf(_ fileName: String) -> String { fileName.beforeLast(".") }
}

private func str(_ v: Any?) -> String {
    switch v {
    case let s as String: return s
    case let i as Int64: return String(i)
    case let d as Double: return String(d)
    case nil: return ""
    default: return "\(v!)"
    }
}

/// MyBible 은 숫자를 NUMERIC 으로 둔다 — 정수 · 실수 · 글자 어느 것이든.
private func num(_ v: Any?) -> Int {
    switch v {
    case let i as Int64: return Int(i)
    case let d as Double: return Int(d)
    case let s as String: return Int(Double(s.trimmed) ?? 0)
    default: return 0
    }
}
