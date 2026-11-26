import Foundation
import XCTest
@testable import BibleClipCore

/// [＋ 성경 파일 추가…] 검사 — BibleImporterTest.kt (데스크톱 tests/test_core.py import_bibles_check) 와 같은 경우들.
final class BibleImporterTests: XCTestCase {
    let text = TextUtils(GoldenTests.tables)
    let krv = repoRoot.appendingPathComponent("bible_versions/KRV.SQLite3")

    func newDir(_ name: String = "d") -> URL {
        let u = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString).appendingPathComponent(name)
        try! FileManager.default.createDirectory(at: u, withIntermediateDirectories: true)
        return u
    }

    func importer(_ dest: URL) -> BibleImporter { BibleImporter(dest: dest, tmp: newDir("tmp"), text: text) }

    /// [bytes] 를 [name] 이라는 고른 파일로.
    func file(_ name: String, _ bytes: Data) -> ImportSource {
        let u = newDir("src").appendingPathComponent(name)
        try! bytes.write(to: u)
        return ImportSource(name: name, url: u)
    }

    var krvData: Data { try! Data(contentsOf: krv) }

    func testAddsBibleRefusesClashAndJunk() {
        let dest = newDir("bible_versions")
        let (added, errors) = importer(dest).import([
            file("MyBible.SQLite3", krvData),
            file("KRV.SQLite3", krvData),                 // 넣어 둔 역본과 겹침
            file("notes.SQLite3", Data("not a database".utf8)),
            file("photo.jpg", krvData),                   // 성경이지만 성경 파일 이름이 아님
        ], taken: ["KRV"])
        XCTAssertEqual(added, ["MyBible.SQLite3"])
        XCTAssertEqual(errors, [ImportError(file: "KRV.SQLite3", code: "exists"),
                                ImportError(file: "notes.SQLite3", code: "invalid"),
                                ImportError(file: "photo.jpg", code: "invalid")])
        XCTAssertEqual(try! Data(contentsOf: dest.appendingPathComponent("MyBible.SQLite3")).count, krvData.count)
        // 폴더에 이미 있는 파일과 대소문자 없이 겹침.
        let (again, errs2) = importer(dest).import([file("mybible.sqlite3", krvData)], taken: [])
        XCTAssertEqual(again, [])
        XCTAssertEqual(errs2, [ImportError(file: "mybible.sqlite3", code: "exists")])
    }

    func testZipTakesBareNamesOnly() {
        let dest = newDir("bible_versions")
        let z = storedZip([
            ("folder/Inner.SQLite3", krvData),
            ("../Escape.SQLite3", krvData),               // zip-slip: 맨 이름 Escape.SQLite3 로
            ("__MACOSX/folder/._Inner.SQLite3", Data(count: 10)),
            ("readme.txt", Data("hi".utf8)),
        ])
        let (added, errors) = importer(dest).import([file("pack.zip", z)], taken: [])
        XCTAssertEqual(added, ["Inner.SQLite3", "Escape.SQLite3"])
        XCTAssertEqual(errors, [])
        XCTAssertFalse(FileManager.default.fileExists(atPath: dest.deletingLastPathComponent().appendingPathComponent("Escape.SQLite3").path))
        XCTAssertEqual(Set(try! FileManager.default.contentsOfDirectory(atPath: dest.path)), ["Inner.SQLite3", "Escape.SQLite3"])
    }

    /// 보통 zip 도구(deflate, 한글 이름)로 만든 것.
    func testDeflatedZipFromZipTool() throws {
        let work = newDir("w")
        let inner = work.appendingPathComponent("성경")
        try FileManager.default.createDirectory(at: inner, withIntermediateDirectories: true)
        try krvData.write(to: inner.appendingPathComponent("개역.SQLite3"))
        let zipURL = newDir("z").appendingPathComponent("bibles.zip")
        let p = Process()
        p.executableURL = URL(fileURLWithPath: "/usr/bin/zip")
        p.currentDirectoryURL = work
        p.arguments = ["-q", "-r", zipURL.path, "성경"]
        try p.run()
        p.waitUntilExit()
        XCTAssertEqual(p.terminationStatus, 0)
        let dest = newDir("bible_versions")
        let (added, errors) = importer(dest).import([ImportSource(name: "bibles.zip", url: zipURL)], taken: [])
        XCTAssertEqual(errors, [])
        XCTAssertEqual(added.map { $0.precomposedStringWithCanonicalMapping }, ["개역.SQLite3"])
        let got = try Data(contentsOf: dest.appendingPathComponent(added[0]))
        XCTAssertEqual(got, krvData)
    }

    func testZipErrors() {
        let dest = newDir("bible_versions")
        let (added, errors) = importer(dest).import([
            file("empty.zip", storedZip([("readme.txt", Data("hi".utf8))])),
            file("broken.zip", Data("PK junk".utf8)),
        ], taken: [])
        XCTAssertEqual(added, [])
        XCTAssertEqual(errors, [ImportError(file: "empty.zip", code: "empty_zip"),
                                ImportError(file: "broken.zip", code: "read_error")])
    }

    // MARK: - 시험용 zip 만들개(저장 방식, 이름 그대로 — zip-slip 이름도 넣을 수 있게)

    func storedZip(_ entries: [(String, Data)]) -> Data {
        var out = Data()
        var central = Data()
        func le16(_ v: Int) -> Data { Data([UInt8(v & 0xff), UInt8(v >> 8 & 0xff)]) }
        func le32(_ v: Int) -> Data { le16(v & 0xffff) + le16(v >> 16 & 0xffff) }
        for (name, body) in entries {
            let nm = Data(name.utf8)
            let crc = crc32(body)
            let offset = out.count
            out += le32(0x04034b50) + le16(20) + le16(0x800) + le16(0) + le16(0) + le16(0)
            out += le32(crc) + le32(body.count) + le32(body.count) + le16(nm.count) + le16(0) + nm + body
            central += le32(0x02014b50) + le16(20) + le16(20) + le16(0x800) + le16(0) + le16(0) + le16(0)
            central += le32(crc) + le32(body.count) + le32(body.count) + le16(nm.count) + le16(0) + le16(0)
            central += le16(0) + le16(0) + le32(0) + le32(offset) + nm
        }
        let cdOffset = out.count
        out += central
        out += le32(0x06054b50) + le16(0) + le16(0) + le16(entries.count) + le16(entries.count)
        out += le32(central.count) + le32(cdOffset) + le16(0)
        return out
    }

    func crc32(_ d: Data) -> Int {
        var c: UInt32 = 0xffffffff
        for b in d {
            c ^= UInt32(b)
            for _ in 0..<8 { c = (c >> 1) ^ (0xedb88320 & (0 &- (c & 1))) }
        }
        return Int(~c)
    }
}
