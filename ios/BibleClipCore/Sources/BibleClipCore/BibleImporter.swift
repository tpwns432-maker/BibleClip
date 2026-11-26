import Compression
import Foundation

/// 고른 파일 하나: 보이는 이름 + 읽을 곳.
public struct ImportSource {
    public let name: String
    public let url: URL
    public init(name: String, url: URL) {
        self.name = name
        self.url = url
    }
}

/// 넣지 못한 파일 하나: code = exists | invalid | empty_zip | read_error | copy_error.
public struct ImportError: Equatable {
    public let file: String
    public let code: String
    public init(file: String, code: String) {
        self.file = file
        self.code = code
    }

    public var json: [String: Any] { ["file": file, "code": code] }
}

/// [＋ 성경 파일 추가…] — Library.import_bible_files(데스크톱 v1.2.1) 이식, BibleImporter.kt 와 같다.
///
/// 성경 DB 파일, 또는 .zip 안의 DB 들을 같은 검사 뒤 [dest] 로 복사한다: 성경으로 열려야 하고
/// (info/books/verses, 절이 있음) 이름이 [taken] 이나 [dest] 의 파일과 대소문자 없이 겹치면 안 된다.
/// zip 항목은 맨 파일 이름만 쓰므로 [dest] 밖에 떨어지는 것이 없다. [tmp] 는 작업 자리.
public final class BibleImporter {
    private let dest: URL
    private let tmp: URL
    private let text: TextUtils
    private let fm = FileManager.default

    public static let maxBibleBytes: Int64 = 512 * 1024 * 1024
    static let bibleExts = [".sqlite3", ".sqlite", ".db"]

    public init(dest: URL, tmp: URL, text: TextUtils) {
        self.dest = dest
        self.tmp = tmp
        self.text = text
    }

    /// [dest] 로 복사한 파일 이름들과 거절한 것들.
    public func `import`(_ sources: [ImportSource], taken: Set<String>) -> ([String], [ImportError]) {
        try? fm.createDirectory(at: dest, withIntermediateDirectories: true)
        var names = Set(taken.map { $0.lowercased() })
        for f in (try? fm.contentsOfDirectory(atPath: dest.path)) ?? [] { names.insert(f.beforeLast(".").lowercased()) }
        var errors: [ImportError] = []
        var added: [String] = []
        let work = tmp.appendingPathComponent("bibleclip_add_\(UUID().uuidString)")
        try? fm.createDirectory(at: work, withIntermediateDirectories: true)
        defer { try? fm.removeItem(at: work) }

        var cands: [(String, URL)] = []
        for src in sources {
            if src.name.lowercased().hasSuffix(".zip") {
                guard let found = try? extractBibles(src, work) else {
                    errors.append(ImportError(file: src.name, code: "read_error"))
                    continue
                }
                if found.isEmpty { errors.append(ImportError(file: src.name, code: "empty_zip")) }
                cands += found
            } else {
                let dir = work.appendingPathComponent("f\(cands.count)_\(UUID().uuidString)")
                let f = dir.appendingPathComponent("in")
                do {
                    try fm.createDirectory(at: dir, withIntermediateDirectories: true)
                    try copyCapped(from: src.url, to: f)
                } catch {
                    errors.append(ImportError(file: src.name, code: "read_error"))
                    continue
                }
                cands.append((src.name, f))
            }
        }
        for (fname, file) in cands {
            let key = fname.beforeLast(".").lowercased()
            if names.contains(key) {
                errors.append(ImportError(file: fname, code: "exists"))
                continue
            }
            let low = fname.lowercased()
            if !BibleImporter.bibleExts.contains(where: { low.hasSuffix($0) }) || !isBible(file) {
                errors.append(ImportError(file: fname, code: "invalid"))
                continue
            }
            let target = dest.appendingPathComponent(fname)
            if fm.fileExists(atPath: target.path) {
                errors.append(ImportError(file: fname, code: "copy_error"))
                continue
            }
            do {
                try fm.copyItem(at: file, to: target)
            } catch {
                errors.append(ImportError(file: fname, code: "copy_error"))
                continue
            }
            names.insert(key)
            added.append(fname)
        }
        return (added, errors)
    }

    private func isBible(_ f: URL) -> Bool {
        guard let db = try? BibleDb(path: f.path, text: text) else { return false }
        defer { db.close() }
        return db.looksLikeBible()
    }

    private struct TooBig: Error {}
    private struct BadZip: Error {}

    /// 복사하되 [maxBibleBytes] 를 넘으면 거절(성경 하나는 5–50MB).
    private func copyCapped(from: URL, to: URL) throws {
        let attrs = try fm.attributesOfItem(atPath: from.path)
        if let size = attrs[.size] as? NSNumber, size.int64Value > BibleImporter.maxBibleBytes { throw TooBig() }
        try fm.copyItem(at: from, to: to)
    }

    /// zip 안의 성경 DB 항목들, 하나씩 제 폴더에 풀어서. UTF-8 표시가 없는 이름은 cp949 로 읽는다
    /// (윈도우에서 만든 한국어 zip).
    private func extractBibles(_ src: ImportSource, _ work: URL) throws -> [(String, URL)] {
        let data = try Data(contentsOf: src.url, options: .alwaysMapped)
        let entries = try Zip.entries(data)
        var out: [(String, URL)] = []
        for (n, e) in entries.enumerated() {
            if e.name.hasSuffix("/") || e.name.hasPrefix("__MACOSX/") { continue }
            let base = e.name.replacingOccurrences(of: "\\", with: "/").components(separatedBy: "/").last ?? ""
            let low = base.lowercased()
            if base.isEmpty || base.hasPrefix(".") || base.contains(":") ||
                !BibleImporter.bibleExts.contains(where: { low.hasSuffix($0) }) ||
                Int64(e.size) > BibleImporter.maxBibleBytes { continue }
            let dir = work.appendingPathComponent("z\(n)")
            try fm.createDirectory(at: dir, withIntermediateDirectories: true)
            let f = dir.appendingPathComponent(base)
            do {
                try Zip.extract(data, e, to: f, cap: BibleImporter.maxBibleBytes)
            } catch is Zip.TooBig {
                try? fm.removeItem(at: f)
                continue
            }
            out.append((base, f))
        }
        return out
    }
}

/// 아주 작은 zip 읽개 — 중앙 디렉터리로 항목을 찾고, 저장(0) · deflate(8) 만 푼다.
/// iOS 에는 zip 을 푸는 공개 API 가 없다. 압축 풀기는 Compression(COMPRESSION_ZLIB = 날 deflate).
enum Zip {
    struct Entry {
        let name: String
        let method: Int
        let compressedSize: Int
        let size: Int
        let localOffset: Int
    }

    struct TooBig: Error {}
    struct Bad: Error {}

    private static func u16(_ d: Data, _ o: Int) -> Int { Int(d[d.startIndex + o]) | Int(d[d.startIndex + o + 1]) << 8 }
    private static func u32(_ d: Data, _ o: Int) -> Int { u16(d, o) | u16(d, o + 2) << 16 }

    private static let cp949 = String.Encoding(rawValue: CFStringConvertEncodingToNSStringEncoding(
        CFStringEncoding(CFStringEncodings.dosKorean.rawValue)))

    static func entries(_ d: Data) throws -> [Entry] {
        // 끝에서 '끝 기록'(PK\5\6)을 찾는다 — 뒤에 주석이 최대 64KB 붙을 수 있다.
        let n = d.count
        guard n >= 22 else { throw Bad() }
        var eocd = -1
        var i = n - 22
        let stop = max(0, n - 22 - 65535)
        while i >= stop {
            if u32(d, i) == 0x06054b50 { eocd = i; break }
            i -= 1
        }
        guard eocd >= 0 else { throw Bad() }
        let count = u16(d, eocd + 10)
        var p = u32(d, eocd + 16)
        var out: [Entry] = []
        for _ in 0..<count {
            guard p + 46 <= n, u32(d, p) == 0x02014b50 else { throw Bad() }
            let flags = u16(d, p + 8)
            let method = u16(d, p + 10)
            let csize = u32(d, p + 20)
            let usize = u32(d, p + 24)
            let nlen = u16(d, p + 28)
            let xlen = u16(d, p + 30)
            let clen = u16(d, p + 32)
            let local = u32(d, p + 42)
            guard p + 46 + nlen <= n else { throw Bad() }
            let raw = d.subdata(in: (d.startIndex + p + 46)..<(d.startIndex + p + 46 + nlen))
            let name = (flags & 0x800 != 0 ? String(data: raw, encoding: .utf8) : String(data: raw, encoding: cp949))
                ?? String(decoding: raw, as: UTF8.self)
            out.append(Entry(name: name, method: method, compressedSize: csize, size: usize, localOffset: local))
            p += 46 + nlen + xlen + clen
        }
        return out
    }

    static func extract(_ d: Data, _ e: Entry, to url: URL, cap: Int64) throws {
        let n = d.count
        guard e.localOffset + 30 <= n, u32(d, e.localOffset) == 0x04034b50 else { throw Bad() }
        let start = e.localOffset + 30 + u16(d, e.localOffset + 26) + u16(d, e.localOffset + 28)
        guard start + e.compressedSize <= n else { throw Bad() }
        let body = d.subdata(in: (d.startIndex + start)..<(d.startIndex + start + e.compressedSize))
        FileManager.default.createFile(atPath: url.path, contents: nil)
        let out = try FileHandle(forWritingTo: url)
        defer { try? out.close() }
        switch e.method {
        case 0:
            if Int64(body.count) > cap { throw TooBig() }
            try out.write(contentsOf: body)
        case 8:
            try inflate(body, into: out, cap: cap)
        default:
            throw Bad()
        }
    }

    /// 날 deflate 를 [out] 으로 — [cap] 바이트를 넘으면 TooBig (zip 폭탄 막기).
    private static func inflate(_ src: Data, into out: FileHandle, cap: Int64) throws {
        let bufSize = 64 * 1024
        let dst = UnsafeMutablePointer<UInt8>.allocate(capacity: bufSize)
        defer { dst.deallocate() }
        var stream = compression_stream(dst_ptr: dst, dst_size: 0, src_ptr: UnsafePointer(dst), src_size: 0, state: nil)
        guard compression_stream_init(&stream, COMPRESSION_STREAM_DECODE, COMPRESSION_ZLIB) == COMPRESSION_STATUS_OK else { throw Bad() }
        defer { compression_stream_destroy(&stream) }
        var total: Int64 = 0
        try src.withUnsafeBytes { (raw: UnsafeRawBufferPointer) in
            guard let base = raw.bindMemory(to: UInt8.self).baseAddress else { return }
            stream.src_ptr = base
            stream.src_size = src.count
            while true {
                stream.dst_ptr = dst
                stream.dst_size = bufSize
                let st = compression_stream_process(&stream, Int32(COMPRESSION_STREAM_FINALIZE.rawValue))
                let produced = bufSize - stream.dst_size
                if produced > 0 {
                    total += Int64(produced)
                    if total > cap { throw TooBig() }
                    try out.write(contentsOf: Data(bytes: dst, count: produced))
                }
                if st == COMPRESSION_STATUS_END { break }
                if st != COMPRESSION_STATUS_OK { throw Bad() }
                if produced == 0 && stream.src_size == 0 { throw Bad() }
            }
        }
    }
}
