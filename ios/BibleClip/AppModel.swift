import BibleClipCore
import Foundation
import os

let log = Logger(subsystem: "com.bibleclip.app", category: "BibleClip")

/// 브리지가 함께 쓰는 Library 하나와 노트 · 형광펜 · 장바구니 — android BibleClipApp.kt 와 같은 일.
///
/// 데이터는 앱의 Documents 폴더("파일" 앱 → 나의 iPhone → BibleClip 에 보인다), 데스크톱과 같은 이름:
///   bibleclip_settings.json · userdata/ · bible_versions/(사용자가 넣은 역본 + aliases_override.json)
/// 기본 역본(KRV · KJV+)은 앱 안(Bundle/bible_versions)에서 읽기 전용으로 바로 연다.
///
/// 모든 엔진 호출은 [queue] 한 줄로 — Library 와 SQLite 연결은 여러 스레드에서 쓰지 않는다.
final class AppModel {
    static let shared = AppModel()

    let queue = DispatchQueue(label: "bibleclip.engine", qos: .userInitiated)
    let bundleDir = Bundle.main.bundleURL.appendingPathComponent("Bundle")
    let docs = FileManager.default.urls(for: .documentDirectory, in: .userDomainMask)[0]
    var bibleDir: URL { docs.appendingPathComponent("bible_versions") }
    private var settingsFile: URL { docs.appendingPathComponent("bibleclip_settings.json") }
    private var aliasFile: URL { bibleDir.appendingPathComponent("aliases_override.json") }
    private var userDir: URL { docs.appendingPathComponent("userdata") }

    private(set) lazy var notes = Notes(file: userDir.appendingPathComponent("user_notes.json"))
    private(set) lazy var highlights = Highlights(file: userDir.appendingPathComponent("user_highlights.json"))
    private(set) lazy var cart = Cart(file: userDir.appendingPathComponent("sermon_cart.json"))

    /// 처음 쓸 때 만든다(모든 역본을 연다) — [queue] 위에서.
    private(set) lazy var library: Library = load()

    private func load() -> Library {
        let t0 = Date()
        try? FileManager.default.createDirectory(at: bibleDir, withIntermediateDirectories: true)
        let tables = Tables(json: (try? String(contentsOf: bundleDir.appendingPathComponent("core/tables.json"),
                                                encoding: .utf8)) ?? "{}")
        let saved = readJson(settingsFile)
        let settings = Settings.of(tables.defaultSettings, saved)
        let aliasFile = self.aliasFile
        let lib = Library(tables, settings) { (try? Data(contentsOf: aliasFile)).flatMap { JSON.parse($0) as? [String: Any] } ?? [:] }
        // 앱 안 기본 역본 먼저, 그다음 사용자가 넣은 것(같은 이름이면 먼저 넣은 것이 이긴다).
        scan(bundleDir.appendingPathComponent("bible_versions"), into: lib)
        scan(bibleDir, into: lib)
        lib.validateSettings()
        let synFile = bundleDir.appendingPathComponent("web/data/bible_synonyms.json")
        lib.synonymsLoader = { Synonyms(json: try? String(contentsOf: synFile, encoding: .utf8)) }
        log.info("library: \(lib.order, privacy: .public) in \(Int(Date().timeIntervalSince(t0) * 1000)) ms")
        // 기본 검색 역본 색인을 미리 — 첫 검색이 바로 되게. 같은 줄이라 다른 호출과 겹치지 않는다.
        queue.async {
            let t1 = Date()
            _ = lib.synonyms
            if let v = lib.searchVersion() { lib.searcher(v)?.warm() }
            log.info("search index warm in \(Int(Date().timeIntervalSince(t1) * 1000)) ms")
        }
        return lib
    }

    /// [dir] 의 성경 파일 중 아직 안 넣은 것을 넣는다. 새로 넣은 이름들.
    @discardableResult
    func scan(_ dir: URL, into lib: Library? = nil) -> [String] {
        let lib = lib ?? library
        let files = (try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []
        var added: [String] = []
        for name in files.sorted() {
            let low = name.lowercased()
            guard low.hasSuffix(".sqlite3") || low.hasSuffix(".sqlite") || low.hasSuffix(".db") else { continue }
            if lib.dbs[BibleDb.nameOf(name)] != nil { continue }
            do {
                let db = try BibleDb(path: dir.appendingPathComponent(name).path, text: lib.text)
                if lib.add(db) { added.append(db.name) }
            } catch {
                log.warning("skip \(name, privacy: .public): \(error.localizedDescription, privacy: .public)")
            }
        }
        return added
    }

    func saveSettings() {
        let data = Data(JSON.string(library.settings.json, pretty: true).utf8)
        try? data.write(to: settingsFile, options: .atomic)
    }

    private func readJson(_ url: URL) -> [String: Any]? {
        guard let d = try? Data(contentsOf: url) else { return nil }
        return JSON.parse(d) as? [String: Any]
    }

    var appVersion: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "0"
    }
}
