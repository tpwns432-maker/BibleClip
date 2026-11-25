import CryptoKit
import Foundation
import XCTest
@testable import BibleClipCore

/// 저장소 뿌리 (이 파일: ios/BibleClipCore/Tests/BibleClipCoreTests/GoldenTests.swift).
let repoRoot: URL = {
    var u = URL(fileURLWithPath: #filePath)
    for _ in 0..<5 { u.deleteLastPathComponent() }
    return u
}()

func readText(_ rel: String) -> String {
    (try? String(contentsOf: repoRoot.appendingPathComponent(rel), encoding: .utf8)) ?? ""
}

func golden(_ name: String) -> [String: Any] {
    JSON.parse(readText("tests/golden/\(name)")) as? [String: Any] ?? [:]
}

/// Swift 엔진을 Python 엔진이 쓴 tests/golden JSON 과 비교한다 (tests/make_golden.py) —
/// Kotlin GoldenTest.kt 와 같은 시험. 실패 = 두 엔진의 답이 다르다.
final class GoldenTests: XCTestCase {
    static let tables = Tables(json: readText("android/app/src/main/assets/\(Tables.asset)"))

    func library(_ overrides: [String: Any] = [:], _ order: [Any] = []) -> Library {
        var saved = overrides
        saved["output_order"] = order
        let lib = Library(Self.tables, Settings.of(Self.tables.defaultSettings, saved))
        for v in ["KRV", "KJV+"] {
            lib.add(try! BibleDb(path: repoRoot.appendingPathComponent("bible_versions/\(v).SQLite3").path,
                                 text: lib.text))
        }
        return lib
    }

    func refsJson(_ refs: [Ref]) -> [Any] {
        refs.map { [$0.book.num, $0.book.short, $0.book.long, $0.chapter, $0.verses] as [Any] }
    }

    func testTablesLoaded() {
        XCTAssertFalse(Self.tables.koreanBookMap.isEmpty)
        XCTAssertFalse(Self.tables.defaultSettings.isEmpty)
    }

    func testAliasMapMatches() {
        let want = golden("engine.json")["aliases"] as? [String: Any] ?? [:]
        let got = library().bookAliases()
        XCTAssertEqual(Set(want.keys), Set(got.keys))
        for (k, v) in want { XCTAssertEqual(pyInt(v), got[k], "alias \(k)") }
    }

    func testReferencesMatch() {
        let g = golden("engine.json")
        let lib = library()
        var failures: [String] = []
        for (key, aliases) in [("with_aliases", lib.bookAliases()), ("without_aliases", nil)] as [(String, [String: Int]?)] {
            let cases = g[key] as? [[String: Any]] ?? []
            XCTAssertFalse(cases.isEmpty, key)
            for c in cases {
                let inp = c["in"] as! String
                let got = refsJson(lib.engine.parseReference(inp, aliases))
                if !JSON.equal(c["out"], got) {
                    failures.append("\(key) '\(inp)': want \(JSON.string(c["out"]!)) got \(JSON.string(got))")
                }
            }
        }
        XCTAssertEqual(failures.count, 0, failures.joined(separator: "\n"))
    }

    func testTextHelpersMatch() {
        let g = golden("text.json")
        let text = TextUtils(Self.tables)
        for c in g["clean_text"] as? [[String: Any]] ?? [] {
            XCTAssertEqual(text.cleanText(c["in"] as? String), c["out"] as? String, "\(c["in"]!)")
        }
        for c in g["qwerty"] as? [[String: Any]] ?? [] {
            XCTAssertEqual(text.convertQwertyToHangul(c["in"] as! String), c["out"] as? String, "\(c["in"]!)")
        }
    }

    func testOutputsMatch() {
        var failures: [String] = []
        let cases = golden("format.json")["cases"] as? [[String: Any]] ?? []
        XCTAssertFalse(cases.isEmpty)
        for c in cases {
            let lib = library(c["settings"] as? [String: Any] ?? [:], c["order"] as? [Any] ?? [])
            let got: Any = lib.buildOutput(c["in"] as? String)?.json ?? NSNull()
            if !JSON.equal(c["out"], got) {
                failures.append("\(c["label"]!):\n  want \(JSON.string(c["out"] ?? NSNull()))\n  got  \(JSON.string(got))")
            }
        }
        XCTAssertEqual(failures.count, 0, failures.joined(separator: "\n"))
    }

    func testTokenizerMatches() {
        for c in golden("search.json")["tokenize"] as? [[String: Any]] ?? [] {
            let got = Korean.tokenize(c["in"] as? String)
            XCTAssertTrue(JSON.equal(c["out"], got), "\(c["in"]!): want \(c["out"]!) got \(got)")
        }
    }

    func testSearchMatches() {
        let syn = Synonyms(json: readText(Synonyms.asset))
        var failures: [String] = []
        let cases = golden("search.json")["cases"] as? [[String: Any]] ?? []
        XCTAssertFalse(cases.isEmpty)
        for c in cases {
            let inp = c["in"] as! [String: Any]
            let lib = library(["search_synonyms": inp["synonyms"]!, "viewer_versions": ["KRV"]])
            lib.synonyms = syn
            let version = inp["version"] as? String
            var r = lib.searchReply(inp["q"] as? String, version,
                                    limit: pyInt(inp["limit"]) ?? 200, mode: inp["mode"] as? String)
            let hits = r.removeValue(forKey: "hits") as? [[String: Any]] ?? []
            r["hit_count"] = hits.count
            r["hit_refs"] = hits.prefix(60).map { [$0["book"]!, $0["chapter"]!, $0["verse"]!] }
            r["hit_heads"] = Array(hits.prefix(3))
            // 걸린 절 전부의 순서 (make_golden search_case 와 같은 줄 꼴의 sha256).
            if inp["limit"] != nil {
                let lines = hits.map { "\(pyInt($0["book"])!):\(pyInt($0["chapter"])!):\(pyInt($0["verse"])!)\n" }.joined()
                r["hit_digest"] = SHA256.hash(data: Data(lines.utf8)).map { String(format: "%02x", $0) }.joined()
            }
            if !JSON.equal(c["out"], r) {
                failures.append("\(JSON.string(inp)):\n  want \(JSON.string(c["out"]!))\n  got  \(JSON.string(r))")
            }
        }
        XCTAssertEqual(failures.count, 0, failures.joined(separator: "\n"))
    }

    // 골든 밖 — 앱이 쓰는 것들이 돌아가는지만.
    func testValidateSettingsAndCopy() {
        let lib = library()
        lib.validateSettings()
        XCTAssertEqual(lib.settings.strings("output_order"), ["KRV"])
        XCTAssertEqual(Set(lib.settings.strings("viewer_version_order")), ["KRV", "KJV+"])
        let (text, n) = lib.copyReferences([["book": 500, "chapter": 3, "verses": [16]],
                                            ["book_num": 10, "chapter": 1, "verses": [1, 2]],
                                            ["book": 500, "chapter": "x", "verses": [1]]], nil)
        XCTAssertEqual(n, 2)
        XCTAssertTrue(text.hasPrefix("[KRV] 요 3:16 하나님이"), text)
    }
}
