import Foundation

/*
 * 노트 · 형광펜 · 장바구니 — bibleclip/notes.py · highlights.py · cart.py 이식 (UserData.kt 와 같다).
 * 같은 파일, 같은 JSON (userdata/user_notes.json · user_highlights.json · sermon_cart.json) 이라
 * 데스크톱 · 안드로이드 파일을 그대로 옮겨 와도 같은 뜻이다. 바꿀 때마다 바로 쓰고, 읽기 · 쓰기가
 * 실패해도 죽지 않는다(없거나 깨진 파일 = 빈 저장소). tests/golden/userdata.json 이 고정한다.
 */

/// 지역 시각 "YYYY-MM-DDTHH:MM:SS" (datetime.now().isoformat(timespec='seconds')).
public func isoNow() -> String {
    let f = DateFormatter()
    f.locale = Locale(identifier: "en_US_POSIX")
    f.calendar = Calendar(identifier: .gregorian)
    f.dateFormat = "yyyy-MM-dd'T'HH:mm:ss"
    return f.string(from: Date())
}

/// 실패해도 죽지 않게 읽고, 통째로 바꿔 쓰는 JSON 파일.
struct JsonFile {
    let url: URL

    func read() -> Any? {
        guard let d = try? Data(contentsOf: url) else { return nil }
        return JSON.parse(d)
    }

    @discardableResult
    func write(_ value: Any) -> Bool {
        do {
            try FileManager.default.createDirectory(at: url.deletingLastPathComponent(), withIntermediateDirectories: true)
            try Data(JSON.string(value, pretty: true).utf8).write(to: url, options: .atomic)
            return true
        } catch {
            return false
        }
    }
}

/// 절에 붙인 묵상 노트: {"책:장:절": {text, ts}}.
public final class Notes {
    private let store: JsonFile
    private let now: () -> String
    public private(set) var data: [String: Any]
    private let lock = NSLock()

    public init(file: URL, now: @escaping () -> String = isoNow) {
        store = JsonFile(url: file)
        self.now = now
        data = store.read() as? [String: Any] ?? [:]
    }

    private func key(_ b: Int, _ c: Int, _ v: Int) -> String { "\(b):\(c):\(v)" }

    public func get(_ b: Int, _ c: Int, _ v: Int) -> [String: Any]? {
        lock.lock(); defer { lock.unlock() }
        return data[key(b, c, v)] as? [String: Any]
    }

    /// 만들기/고치기 — 빈 글이면 지운다. 저장한 노트 또는 nil.
    @discardableResult
    public func set(_ b: Int, _ c: Int, _ v: Int, _ text: String?) -> [String: Any]? {
        lock.lock(); defer { lock.unlock() }
        let k = key(b, c, v)
        let t = (text ?? "").trimmed
        if t.isEmpty {
            data.removeValue(forKey: k)
            store.write(data)
            return nil
        }
        let entry: [String: Any] = ["text": t, "ts": now()]
        data[k] = entry
        store.write(data)
        return entry
    }

    @discardableResult
    public func delete(_ b: Int, _ c: Int, _ v: Int) -> Bool {
        lock.lock(); defer { lock.unlock() }
        data.removeValue(forKey: key(b, c, v))
        store.write(data)
        return true
    }

    /// 모든 노트, 성경 순서: [{book, chapter, verse, text, ts}].
    public func all() -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        var out: [((Int, Int, Int), [String: Any])] = []
        for (k, raw) in data {
            let p = k.split(separator: ":", omittingEmptySubsequences: false).map { Int($0) ?? -1 }
            guard p.count == 3, !p.contains(where: { $0 < 0 }) else { continue }
            let n = raw as? [String: Any] ?? [:]
            out.append(((p[0], p[1], p[2]), ["book": p[0], "chapter": p[1], "verse": p[2],
                                             "text": optString(n["text"]), "ts": optString(n["ts"])]))
        }
        return out.sorted { $0.0 < $1.0 }.map { $0.1 }
    }

    /// {절: 글} 한 장 — 📄 표시용.
    public func forChapter(_ b: Int, _ c: Int) -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        let prefix = "\(b):\(c):"
        var out: [String: Any] = [:]
        for (k, raw) in data where k.hasPrefix(prefix) {
            let parts = k.split(separator: ":", omittingEmptySubsequences: false)
            guard parts.count > 2, let v = Int(parts[2]) else { continue }
            out[String(v)] = optString((raw as? [String: Any])?["text"])
        }
        return out
    }
}

/// 형광펜: {"책:장:절:역본": [{s, e, t, c, ts}]} — 구간은 정렬되고 겹치지 않는다.
public final class Highlights {
    private let store: JsonFile
    private let now: () -> String
    public private(set) var data: [String: Any]
    private let lock = NSLock()

    public static let colors = ["y", "g", "b", "p"]
    public static let maxRanges = 64
    public static let maxSnippet = 400

    public init(file: URL, now: @escaping () -> String = isoNow) {
        store = JsonFile(url: file)
        self.now = now
        var d: [String: Any] = [:]
        for (k, v) in store.read() as? [String: Any] ?? [:] where v is [Any] { d[k] = v }
        data = d
    }

    private func key(_ b: Int, _ c: Int, _ v: Int, _ ver: String) -> String { "\(b):\(c):\(v):\(ver)" }

    /// 정리: 쓰레기 빼기, 정렬, 겹치면 앞 구간이 이기게 자르기, 최대 [maxRanges] 개.
    public func norm(_ ranges: [Any]?) -> [[String: Any]] {
        struct R { var s: Int; let e: Int; var t: String; let c: String; let ts: String }
        var clean: [R] = []
        for raw in ranges ?? [] {
            guard let r = raw as? [String: Any], let s = pyInt(r["s"]), let e = pyInt(r["e"]) else { continue }
            if s < 0 || e <= s { continue }
            let c = (r["c"] as? String).flatMap { Highlights.colors.contains($0) ? $0 : nil } ?? Highlights.colors[0]
            let t = (r["t"] as? String).map { $0.scalarPrefix(Highlights.maxSnippet) } ?? ""
            let ts = (r["ts"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? now()
            clean.append(R(s: s, e: e, t: t, c: c, ts: ts))
        }
        // 안정 정렬 — (s, e) 가 같으면 들어온 순서.
        let sorted = clean.enumerated().sorted { a, b in
            (a.element.s, a.element.e, a.offset) < (b.element.s, b.element.e, b.offset)
        }.map { $0.element }
        var out: [R] = []
        for var r in sorted {
            if let last = out.last, r.s < last.e {
                r.s = last.e
                if r.e <= r.s { continue }
                r.t = ""
            }
            out.append(r)
            if out.count >= Highlights.maxRanges { break }
        }
        return out.map { ["s": $0.s, "e": $0.e, "t": $0.t, "c": $0.c, "ts": $0.ts] }
    }

    public func get(_ b: Int, _ c: Int, _ v: Int, _ ver: String) -> [Any] {
        lock.lock(); defer { lock.unlock() }
        return data[key(b, c, v, ver)] as? [Any] ?? []
    }

    /// 한 절+역본의 구간을 통째로 바꾼다 — 비면 지운다. 저장한 목록.
    @discardableResult
    public func setVerse(_ b: Int, _ c: Int, _ v: Int, _ ver: String, _ ranges: [Any]?) -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        let k = key(b, c, v, ver)
        let stored = norm(ranges)
        if stored.isEmpty { data.removeValue(forKey: k) } else { data[k] = stored }
        store.write(data)
        return stored
    }

    @discardableResult
    public func clearVerse(_ b: Int, _ c: Int, _ v: Int, _ ver: String) -> Bool {
        lock.lock(); defer { lock.unlock() }
        data.removeValue(forKey: key(b, c, v, ver))
        store.write(data)
        return true
    }

    /// {절: [구간]} — 한 역본의 한 장.
    public func forChapter(_ b: Int, _ c: Int, _ ver: String) -> [String: Any] {
        lock.lock(); defer { lock.unlock() }
        let prefix = "\(b):\(c):"
        var out: [String: Any] = [:]
        for (k, raw) in data where k.hasPrefix(prefix) {
            let p = split4(k)   // 역본 이름에 ':' 가 있을 수 있다
            guard p.count == 4, p[3] == ver, let v = Int(p[2]) else { continue }
            out[String(v)] = raw
        }
        return out
    }

    /// 모든 형광펜, 성경 순서: [{book, chapter, verse, version, s, e, t, c, ts}].
    public func all() -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        struct H { let b: Int, c: Int, v: Int; let ver: String; let s: Int; let o: [String: Any] }
        var out: [H] = []
        for (k, raw) in data {
            let p = split4(k)
            guard p.count == 4, let b = Int(p[0]), let c = Int(p[1]), let v = Int(p[2]),
                  let ranges = raw as? [Any] else { continue }
            for e in ranges {
                guard let r = e as? [String: Any] else { continue }
                out.append(H(b: b, c: c, v: v, ver: p[3], s: optInt(r["s"]), o: [
                    "book": b, "chapter": c, "verse": v, "version": p[3],
                    "s": r["s"] ?? NSNull(), "e": r["e"] ?? NSNull(),
                    "t": optString(r["t"]), "c": { if case .null = JV(r["c"]) { return Highlights.colors[0] }; return optString(r["c"]) }(),
                    "ts": optString(r["ts"]),
                ]))
            }
        }
        // 안정 정렬: (책, 장, 절, 역본, s)
        return out.enumerated().sorted { a, b in
            let x = a.element, y = b.element
            if (x.b, x.c, x.v) != (y.b, y.c, y.v) { return (x.b, x.c, x.v) < (y.b, y.c, y.v) }
            if x.ver != y.ver { return x.ver.unicodeScalars.lexicographicallyPrecedes(y.ver.unicodeScalars) }
            return (x.s, a.offset) < (y.s, b.offset)
        }.map { $0.element.o }
    }

    private func split4(_ k: String) -> [String] {
        k.split(separator: ":", maxSplits: 3, omittingEmptySubsequences: false).map(String.init)
    }
}

/// 설교 장바구니: [{book_num, chapter, verses, short_name}] — 바꿀 때마다 통째로 바꾼다.
public final class Cart {
    private let store: JsonFile
    public private(set) var items: [[String: Any]]
    private let lock = NSLock()

    public init(file: URL) {
        store = JsonFile(url: file)
        items = (store.read() as? [Any]).map { Cart.sanitize($0) } ?? []
    }

    public func all() -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        return items
    }

    @discardableResult
    public func replace(_ raw: [Any]?) -> [[String: Any]] {
        lock.lock(); defer { lock.unlock() }
        items = Cart.sanitize(raw)
        store.write(items)
        return items
    }

    /// 잘못된 항목을 뺀다 — 화면이 저장하고 읽는 꼴 그대로.
    public static func sanitize(_ raw: [Any]?) -> [[String: Any]] {
        var out: [[String: Any]] = []
        for e in raw ?? [] {
            guard let it = e as? [String: Any] else { continue }
            // Python: it.get("book_num", it.get("book")) — book_num 이 null 로 있으면 그것이 이긴다.
            guard let book = pyInt(it["book_num"] != nil ? it["book_num"] : it["book"]),
                  let chapter = pyInt(it["chapter"]) else { continue }
            let verses = (it["verses"] as? [Any] ?? []).compactMap { pyInt($0) }
            // Python: str(it.get("short_name") or "")
            let sn = it["short_name"]
            let short = pyTruthy(sn) ? ((sn as? String) ?? jsonText(sn)) : ""
            out.append(["book_num": book, "chapter": chapter, "verses": verses, "short_name": short])
        }
        return out
    }
}

/// org.json optString — 없거나 null 이면 "", 아니면 글로.
func optString(_ v: Any?) -> String {
    if case .null = JV(v) { return "" }
    return jsonText(v)
}

/// org.json optInt — 숫자(또는 숫자 글)면 정수, 아니면 0.
func optInt(_ v: Any?) -> Int {
    switch JV(v) {
    case .int(let i): return i
    case .double(let d): return d.isFinite ? Int(d) : 0
    case .string(let s): return Int(s.trimmed) ?? Int(Double(s.trimmed) ?? 0)
    default: return 0
    }
}
