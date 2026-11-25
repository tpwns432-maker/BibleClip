import Foundation
import XCTest
@testable import BibleClipCore

/// 노트 · 형광펜 · 장바구니를 tests/golden/userdata.json 과 — Python 저장소가 같은 명령을
/// 돌린 결과다. 반환값마다, 디스크에 남은 파일, 깨진 파일 읽기가 같아야 한다 (UserDataTest.kt 와 같다).
final class UserDataTests: XCTestCase {
    let g = golden("userdata.json")
    var now: String { g["now"] as! String }

    func tmpFile(_ name: String) -> URL {
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent(UUID().uuidString)
        try! FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        return dir.appendingPathComponent(name)
    }

    func i(_ op: [Any], _ k: Int) -> Int { pyInt(op[k])! }

    func replay(_ section: String, _ file: URL, _ run: ([Any]) -> Any?) {
        let s = g[section] as! [String: Any]
        let ops = s["ops"] as! [[Any]]
        let want = s["results"] as! [Any]
        var failures: [String] = []
        for (k, op) in ops.enumerated() {
            let got = run(op)
            if !JSON.equal(want[k], got) {
                failures.append("\(section) #\(k) \(JSON.string(op)):\n  want \(JSON.string(want[k]))\n  got  \(JSON.string(got ?? NSNull()))")
            }
        }
        let onDisk = JSON.parse((try? Data(contentsOf: file)) ?? Data())
        if !JSON.equal(s["final"], onDisk) {
            failures.append("\(section) file:\n  want \(JSON.string(s["final"]!))\n  got  \(JSON.string(onDisk ?? NSNull()))")
        }
        XCTAssertEqual(failures.count, 0, failures.joined(separator: "\n"))
    }

    func testNotes() {
        let f = tmpFile("user_notes.json")
        let s = Notes(file: f, now: { self.now })
        replay("notes", f) { op in
            switch op[0] as! String {
            case "set": return s.set(i(op, 1), i(op, 2), i(op, 3), op[4] as? String)
            case "get": return s.get(i(op, 1), i(op, 2), i(op, 3))
            case "delete": return s.delete(i(op, 1), i(op, 2), i(op, 3))
            case "for_chapter": return s.forChapter(i(op, 1), i(op, 2))
            case "all": return s.all()
            default: XCTFail("op \(op[0])"); return nil
            }
        }
    }

    func testHighlights() {
        let f = tmpFile("user_highlights.json")
        let s = Highlights(file: f, now: { self.now })
        replay("highlights", f) { op in
            switch op[0] as! String {
            case "set_verse": return s.setVerse(i(op, 1), i(op, 2), i(op, 3), op[4] as! String, op[5] as? [Any])
            case "get": return s.get(i(op, 1), i(op, 2), i(op, 3), op[4] as! String)
            case "clear_verse": return s.clearVerse(i(op, 1), i(op, 2), i(op, 3), op[4] as! String)
            case "for_chapter": return s.forChapter(i(op, 1), i(op, 2), op[3] as! String)
            case "all": return s.all()
            default: XCTFail("op \(op[0])"); return nil
            }
        }
    }

    func testCart() {
        let f = tmpFile("sermon_cart.json")
        let s = Cart(file: f)
        replay("cart", f) { op in
            switch op[0] as! String {
            case "replace": return s.replace(op[1] as? [Any])
            case "all": return s.all()
            default: XCTFail("op \(op[0])"); return nil
            }
        }
    }

    func testBrokenFilesLoadSoft() {
        for c in g["loads"] as! [[String: Any]] {
            let f = tmpFile("data.json")
            try! Data((c["file"] as! String).utf8).write(to: f)
            let got: Any
            switch c["store"] as! String {
            case "notes": got = Notes(file: f, now: { self.now }).data
            case "highlights": got = Highlights(file: f, now: { self.now }).data
            default: got = Cart(file: f).items
            }
            XCTAssertTrue(JSON.equal(c["loaded"], got), "\(c["store"]!) \(c["file"]!): got \(JSON.string(got))")
        }
    }
}
