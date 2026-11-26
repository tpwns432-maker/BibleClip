import BibleClipCore
import UIKit
import UniformTypeIdentifiers
import WebKit

/// bridge.js 의 Swift 쪽 — 데스크톱 bibleclip/webui routes 와 같은 메서드 이름 · 인자 · 답 꼴이라
/// web/ 를 갈라 고칠 일이 없다. android Bridge.kt 의 이식.
/// 모르는 메서드는 null 로 답한다(한 번 기록) — 화면은 머리 없이 돌 때처럼 물러선다.
final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    private let model = AppModel.shared
    private var unknown = Set<String>()
    private lazy var haptic = UISelectionFeedbackGenerator()
    private var lib: Library { model.library }

    func userContentController(_ controller: WKUserContentController, didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any], let method = body["method"] as? String else {
            replyHandler(nil, "bad message"); return
        }
        let args = (body["args"] as? String).flatMap { JSON.parse($0) as? [Any] } ?? []
        if method == "haptic" {
            // 검색 분포 막대를 문지를 때 칸마다 — 검색 같은 느린 일 뒤에 줄 세우지 않는다.
            haptic.selectionChanged()
            replyHandler("true", nil)
            return
        }
        model.queue.async {
            let reply: String
            do {
                reply = JSON.string(try self.dispatch(method, A(args)) ?? NSNull())
            } catch {
                log.warning("bridge \(method, privacy: .public) failed: \(String(describing: error), privacy: .public)")
                let msg = String(describing: error)
                DispatchQueue.main.async { replyHandler(nil, msg) }
                return
            }
            DispatchQueue.main.async { replyHandler(reply, nil) }
        }
    }

    // MARK: - 메서드

    private func dispatch(_ m: String, _ a: A) throws -> Any? {
        switch m {
        case "get_initial": return initial()
        case "get_books": return books(a.str(0))
        case "get_chapters": return lib.dbs[a.str(0)]?.getChapters(a.int(1)) ?? []
        case "get_chapter": return chapter(a.str(0), a.int(1), a.int(2))
        case "resolve_reference":
            guard let r = lib.parseReference(a.str(0)).first else { return nil }
            return ["book_num": r.book.num, "short": r.book.short, "long": r.book.long,
                    "chapter": r.chapter, "verses": r.verses]
        case "copy_reference": return copyReference(a)
        case "copy_text":
            let t = a.str(0)
            if t.isEmpty { return ok(false) }
            clip(t)
            return ok(true)
        case "get_locale": return locale(a.str(0))
        case "get_settings":
            var f: [String: Any] = [:]
            for k in Bridge.formatKeys.keys { f[k] = lib.settings[k] ?? NSNull() }
            return ["format": f, "output_order": lib.settings.strings("output_order"), "versions": versions()]
        case "get_preview":
            if case let .reference(_, _, _, _, text, _)? = lib.buildOutput("요 1:1-3") { return text }
            return ""
        case "get_app_settings":
            var o: [String: Any] = [:]
            for k in Bridge.appKeys.keys { o[k] = lib.settings[k] ?? NSNull() }
            return o
        case "set_setting": return setChecked(a.str(0), a[1], Bridge.formatKeys)
        case "set_app_setting":
            switch a.str(0) {
            case "custom_theme":
                guard let v = cleanCustomTheme(a[1]) else { return ok(false, ["error": "invalid value for custom_theme"]) }
                save("custom_theme", v)
                syncDarkMode()
                return ok(true, ["value": v])
            case "theme":
                let r = setChecked("theme", a[1], Bridge.appKeys)
                if r["ok"] as? Bool == true { syncDarkMode() }
                return r
            default:
                return setChecked(a.str(0), a[1], Bridge.appKeys)
            }
        case "save_cards_layout": return save("web_cards_layout", a[0])
        case "set_dark_mode":
            let dark = a.bool(0)
            save("theme", dark ? "dark" : "light")
            return save("dark_mode", dark)
        case "set_font_size":
            let size = min(max(a.int(0, 11), 8), 400)
            save("viewer_font_size", size)
            return size
        case "set_viewer_versions": return setViewer(a.strings(0), keepOrder: false)
        case "set_viewer_order": return setViewer(a.strings(0), keepOrder: true)
        case "set_output_order":
            var seen = Set<String>()
            let names = a.strings(0).filter { lib.dbs[$0] != nil && seen.insert($0).inserted }
            save("output_order", names)
            return names
        case "search":
            return lib.searchReply(a.str(0), a.isNull(1) ? nil : a.str(1),
                                   limit: a.isNull(2) ? 200 : a.int(2, 200), mode: a.isNull(3) ? "and" : a.str(3))
        // 노트 · 형광펜 · 장바구니 (routes/notes.py · routes/highlights.py)
        case "get_chapter_notes": return model.notes.forChapter(try a.pyint(0), try a.pyint(1))
        case "get_all_notes": return model.notes.all()
        case "get_note": return model.notes.get(try a.pyint(0), try a.pyint(1), try a.pyint(2))
        case "set_note":
            let n = model.notes.set(try a.pyint(0), try a.pyint(1), try a.pyint(2), a.str(3))
            return ok(true, ["note": nn(n)])
        case "delete_note":
            model.notes.delete(try a.pyint(0), try a.pyint(1), try a.pyint(2))
            return ok(true)
        case "get_cart": return model.cart.all()
        case "set_cart": return ok(true, ["items": model.cart.replace(a[0] as? [Any])])
        case "copy_references": return copyReferences(a)
        case "get_chapter_highlights":
            let names = (a[2] as? String).map { [$0] } ?? a.strings(2)
            var o: [String: Any] = [:]
            for v in names { o[v] = model.highlights.forChapter(try a.pyint(0), try a.pyint(1), v) }
            return o
        case "get_verse_highlights":
            return model.highlights.get(try a.pyint(0), try a.pyint(1), try a.pyint(2), a.str(3))
        case "set_verse_highlights":
            return ok(true, ["ranges": model.highlights.setVerse(try a.pyint(0), try a.pyint(1), try a.pyint(2),
                                                                 a.str(3), a[4] as? [Any])])
        case "clear_verse_highlights":
            model.highlights.clearVerse(try a.pyint(0), try a.pyint(1), try a.pyint(2), a.str(3))
            return ok(true)
        case "get_all_highlights": return model.highlights.all()
        case "add_bible_files": return addBibleFiles()
        case "refresh_databases":
            return ["added": model.scan(model.bibleDir), "versions": versions()]
        case "note_position":
            lib.settings["last_book_num"] = a.int(0)
            lib.settings["last_chapter"] = a.int(1)
            return nil
        default:
            if unknown.insert(m).inserted { log.info("bridge: not on iOS yet: \(m, privacy: .public)") }
            return nil
        }
    }

    private func initial() -> [String: Any] {
        let s = lib.settings
        let primary = lib.primaryVersion()
        let bookList = primary.flatMap { lib.dbs[$0] }?.bookList ?? []
        var lastBook = intValue(s["last_book_num"])
        var lastChapter = intValue(s["last_chapter"])
        if !bookList.contains(where: { $0.0 == lastBook }) {
            lastBook = bookList.first?.0
            lastChapter = nil
        }
        if let b = lastBook, lastChapter == nil {
            lastChapter = primary.flatMap { lib.dbs[$0]?.getChapters(b).first } ?? 1
        }
        let theme = s.str("theme", "")
        let sort = s.str("search_sort", "rank")
        return [
            "versions": versions(),
            "primary": nn(primary),
            "viewer": s.strings("viewer_versions"),
            "books": primary.map { books($0) } ?? [],
            "last": ["version": nn(primary), "book": nn(lastBook), "chapter": nn(lastChapter)] as [String: Any],
            "dark_mode": s.truthy("dark_mode"),
            "theme": Bridge.themes.contains(theme) ? theme : "",
            "custom_theme": nn(cleanCustomTheme(s["custom_theme"])),
            "font_size": intValue(s["viewer_font_size"]) ?? 11,
            "auto_update_check": false,
            "lex_lang": s.str("lex_lang", "ko") == "en" ? "en" : "ko",
            "ui_lang": s.str("ui_lang", "ko").isEmpty ? "ko" : s.str("ui_lang", "ko"),
            "reading_font": s.str("reading_font", ""),
            "subtitle_preset": s.str("subtitle_preset", "green"),
            "lex": ["ko": false, "en": false],
            "interlin_sources": [Any](),
            "is_premium": true,
            "search_click_navigates": s.truthy("search_click_navigates"),
            "auto_copy_top_result": s.truthy("auto_copy_top_result"),
            "search_sort": Bridge.searchSorts.contains(sort) ? sort : "rank",
            "search_synonyms": s.truthy("search_synonyms", true),
            "view_mode": s.str("view_mode", "") == "split" ? "split" : "interleave",
            "web_cards_layout": s["web_cards_layout"] ?? NSNull(),
            // 첫 실행 안내는 데스크톱(감시 · F 키)을 돈다 — 휴대폰에는 아직.
            "tour_done": true,
            "cart": model.cart.all(),
            "version": model.appVersion,
        ]
    }

    private func versions() -> [[String: Any]] {
        lib.order.compactMap { name in
            guard let db = lib.dbs[name] else { return nil }
            return ["name": name, "display": db.displayName,
                    "lang": (db.info["language"] ?? "").trimmingCharacters(in: .whitespaces).lowercased()]
        }
    }

    private func books(_ version: String) -> [[String: Any]] {
        (lib.dbs[version]?.bookList ?? []).map { ["num": $0.0, "short": $0.1, "long": $0.2] }
    }

    private func chapter(_ version: String, _ book: Int, _ chapter: Int) -> [String: Any] {
        let db = lib.dbs[version]
        let b = db?.books[book]
        return [
            "ref": ["version": version, "book": book, "short": b?.short ?? "?", "long": b?.long ?? "?",
                    "chapter": chapter] as [String: Any],
            "verses": (db?.getVerses(book, chapter) ?? []).map { ["n": $0.0, "text": $0.1] as [String: Any] },
        ]
    }

    private func copyReference(_ a: A) -> [String: Any] {
        let book = a.int(0)
        let chapter = a.int(1)
        let verses = (a[2] as? [Any])?.map { A.optInt($0) } ?? []
        let order = (a[3] as? [Any]).map { A.strings($0).filter { lib.dbs[$0] != nil } }.flatMap { $0.isEmpty ? nil : $0 }
        let (text, nParts) = lib.formatReference(book, chapter, verses, order)
        if text.isEmpty { return ok(false) }
        clip(text)
        return ok(true, ["text": text, "n_parts": nParts,
                         "short_name": nn(lib.displayBookName(book, order) ?? lib.engine.canon(book)?.short)])
    }

    /// [＋ 성경 파일 추가…]: 파일 고르기 창 → 검사한 뒤 Documents/bible_versions 로 복사 → 넣기.
    /// 답은 데스크톱 add_bible_files 와 같은 꼴이라 web/ 가 그대로 처리한다.
    /// 엔진 줄([queue]) 위에서 고르기 창이 닫힐 때까지 기다린다(android 와 같다).
    private func addBibleFiles() -> [String: Any] {
        let done = DispatchSemaphore(value: 0)
        var picked: [URL] = []
        DispatchQueue.main.async {
            FilePicker.shared.pick { urls in
                picked = urls
                done.signal()
            }
        }
        done.wait()
        if picked.isEmpty { return ok(false, ["error": "cancelled"]) }
        let sources = picked.map { ImportSource(name: $0.lastPathComponent, url: $0) }
        let (_, errors) = model.importBibles(sources)
        for u in picked { try? FileManager.default.removeItem(at: u) }   // 고르기 창이 만든 사본
        let added = model.scan(model.bibleDir)
        return ok(true, [
            "added": added.map { ["name": $0, "display": lib.dbs[$0]?.displayName ?? $0] },
            "errors": errors.map { $0.json },
            "versions": versions(),
        ])
    }

    /// 장바구니 한꺼번에 → 클립보드. {ok, text, n_items} 또는 {ok:false}.
    private func copyReferences(_ a: A) -> [String: Any] {
        let order = (a[1] as? [Any]).map { A.strings($0).filter { lib.dbs[$0] != nil } }.flatMap { $0.isEmpty ? nil : $0 }
        let (text, n) = lib.copyReferences(a[0] as? [Any], order)
        if n == 0 { return ok(false) }
        clip(text)
        return ok(true, ["text": text, "n_items": n])
    }

    private func locale(_ lang: String) -> [String: Any] {
        guard lang.range(of: #"^[a-z]{2,3}(?:-[A-Za-z]{2,4})?$"#, options: .regularExpression) != nil else { return [:] }
        let url = model.bundleDir.appendingPathComponent("web/locales/\(lang).json")
        return (try? Data(contentsOf: url)).flatMap { JSON.parse($0) as? [String: Any] } ?? [:]
    }

    private func setViewer(_ names: [String], keepOrder: Bool) -> [String] {
        let s = lib.settings
        let current = s.strings("viewer_versions")
        if keepOrder {
            let valid = names.filter { lib.dbs[$0] != nil }
            if valid.isEmpty { return current }
            s["viewer_versions"] = valid
            s["viewer_version_order"] = valid + s.strings("viewer_version_order").filter { lib.dbs[$0] != nil && !valid.contains($0) }
            model.saveSettings()
            return valid
        }
        var order = s.strings("viewer_version_order")
        if order.isEmpty { order = lib.order }
        var ordered = order.filter { names.contains($0) && lib.dbs[$0] != nil }
        for n in names where lib.dbs[n] != nil && !ordered.contains(n) { ordered.append(n) }
        if ordered.isEmpty { return current }
        save("viewer_versions", ordered)
        return ordered
    }

    /// set_setting / set_app_setting: 허용한 키만 — 허용 값 집합, nil = 참거짓.
    private func setChecked(_ key: String, _ value: Any?, _ spec: [String: Set<String>?]) -> [String: Any] {
        guard let allowed = spec[key] else { return ok(false, ["error": "unknown key: \(key)"]) }
        let v: Any
        if key == "custom_format_template" {
            let t = (value == nil || value is NSNull) ? "" : A.text(value)
            v = String(t.prefix(500))
        } else if Bridge.freeKeys.contains(key) {
            v = value ?? NSNull()
        } else if allowed == nil {
            v = A.truthy(value)
        } else if let t = value.map({ A.text($0) }), allowed!.contains(t) {
            v = t
        } else {
            return ok(false, ["error": "invalid value for \(key): \(value.map { A.text($0) } ?? "null")"])
        }
        save(key, v)
        return ok(true, ["value": v])
    }

    /// 색 테마 "직접 만들기" 값 검사(system.py _clean_custom_theme 과 같이). 틀리면 nil.
    private func cleanCustomTheme(_ v: Any?) -> [String: Any]? {
        guard let o = v as? [String: Any], let base = o["base"] as? String, base == "light" || base == "dark" else { return nil }
        var out: [String: Any] = ["base": base]
        for k in ["bg", "text", "accent"] {
            guard let c = o[k] as? String, c.range(of: "^#[0-9a-fA-F]{6}$", options: .regularExpression) != nil else { return nil }
            out[k] = c.lowercased()
        }
        return out
    }

    /// theme 의 바탕을 dark_mode 에도 — 데스크톱 설정 파일과 같은 뜻.
    private func syncDarkMode() {
        let t = lib.settings.str("theme", "")
        let dark: Bool
        if t == "custom" {
            guard let base = cleanCustomTheme(lib.settings["custom_theme"])?["base"] as? String else { return }
            dark = base == "dark"
        } else if Bridge.themes.contains(t) {
            dark = Bridge.darkThemes.contains(t)
        } else {
            return
        }
        save("dark_mode", dark)
    }

    @discardableResult
    private func save(_ key: String, _ value: Any?) -> [String: Any] {
        lib.settings[key] = value
        model.saveSettings()
        return ok(true)
    }

    private func clip(_ text: String) {
        DispatchQueue.main.async { UIPasteboard.general.string = text }
    }

    private func ok(_ v: Bool, _ extra: [String: Any] = [:]) -> [String: Any] {
        var o = extra
        o["ok"] = v
        return o
    }

    private func intValue(_ v: Any?) -> Int? {
        guard let n = v as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() else { return nil }
        return n.intValue
    }

    // MARK: - 표 (Bridge.kt 와 같다)

    /// 데스크톱 _FORMAT_KEYS (system.py) — nil = 참거짓.
    static let formatKeys: [String: Set<String>?] = [
        "book_name": ["long_ko", "short_ko"],
        "chapter_verse_format": ["colon", "korean"],
        "bracket_style": ["none", "[]", "()"],
        "ref_position": ["before", "after"],
        "range_symbol": ["-", "~"],
        "ref_body_separator": [" - ", ": ", " "],
        "output_mode": ["inline", "newline"],
        "newline_show_cv": nil,
        "show_version_header": nil,
        "hide_reference": nil,
        "custom_format_enabled": nil,
        "custom_format_template": [],
    ]

    /// 검색 결과 정렬(화면이 계산 — docs/SEARCH_SORT_PLAN.md).
    static let searchSorts: Set<String> = ["rank", "bible", "freq", "short", "orig"]

    /// 색 테마(docs/CUSTOM_THEME_PLAN.md) — web/js/theme.js · system.py 와 같은 이름.
    static let themes: Set<String> = ["light", "dark", "paper", "sage", "navy", "black", "custom"]
    static let darkThemes: Set<String> = ["dark", "navy", "black"]

    /// 데스크톱 _APP_KEYS 중 휴대폰에서 뜻이 있는 것.
    static let appKeys: [String: Set<String>?] = [
        "search_click_navigates": nil,
        "auto_copy_top_result": nil,
        "search_synonyms": nil,
        "search_sort": searchSorts,
        "tour_done": nil,
        "lex_lang": ["ko", "en"],
        "ui_lang": ["ko", "en"],
        "view_mode": ["interleave", "split"],
        "reading_font": [],
        "web_cards_layout": [],
        "theme": themes,
    ]

    /// 받은 그대로 저장('str' / 'any').
    static let freeKeys: Set<String> = ["custom_format_template", "reading_font", "web_cards_layout"]
}

/// nil → JSON null.
func nn(_ v: Any?) -> Any { v ?? NSNull() }

/// JS 인자 배열 — org.json JSONArray 의 opt* 처럼 읽는다.
struct A {
    let a: [Any]
    init(_ a: [Any]) { self.a = a }

    subscript(i: Int) -> Any? {
        guard i < a.count, !(a[i] is NSNull) else { return nil }
        return a[i]
    }

    func isNull(_ i: Int) -> Bool { self[i] == nil }

    /// optString — 없거나 null 이면 "".
    func str(_ i: Int) -> String { self[i].map { A.text($0) } ?? "" }

    /// optInt — 숫자(또는 숫자 글)가 아니면 [def].
    func int(_ i: Int, _ def: Int = 0) -> Int { A.optInt(self[i], def) }

    /// optBoolean.
    func bool(_ i: Int) -> Bool {
        if let n = self[i] as? NSNumber { return n.boolValue }
        return (self[i] as? String)?.lowercased() == "true"
    }

    func strings(_ i: Int) -> [String] { (self[i] as? [Any]).map { A.strings($0) } ?? [] }

    /// 데스크톱 라우트의 int(x) 처럼 — 숫자가 아니면 오류.
    func pyint(_ i: Int) throws -> Int {
        let v = self[i]
        if let n = v as? NSNumber { return n.intValue }
        if let s = v as? String, let n = Int(s.trimmingCharacters(in: .whitespaces)) { return n }
        throw NSError(domain: "Bridge", code: 1, userInfo: [NSLocalizedDescriptionKey: "argument \(i) is not a number"])
    }

    static func strings(_ a: [Any]) -> [String] { a.map { $0 is NSNull ? "" : text($0) } }

    static func text(_ v: Any) -> String {
        if let s = v as? String { return s }
        if let n = v as? NSNumber {
            if CFGetTypeID(n) == CFBooleanGetTypeID() { return n.boolValue ? "true" : "false" }
            return n.stringValue
        }
        return JSON.string(v)
    }

    static func optInt(_ v: Any?, _ def: Int = 0) -> Int {
        if let n = v as? NSNumber, CFGetTypeID(n) != CFBooleanGetTypeID() { return n.intValue }
        if let s = v as? String, let d = Double(s.trimmingCharacters(in: .whitespaces)) { return Int(d) }
        return def
    }

    static func truthy(_ v: Any?) -> Bool {
        switch v {
        case nil, is NSNull: return false
        case let s as String: return !s.isEmpty
        case let n as NSNumber: return n.boolValue
        case let a as [Any]: return !a.isEmpty
        case let o as [String: Any]: return !o.isEmpty
        default: return true
        }
    }
}

/// 시스템 파일 고르기 창("파일" 앱) — 아무 종류나: .SQLite3 은 제 형식 이름이 없어 거르면
/// 찾는 파일이 숨는다. asCopy 라 앱의 임시 폴더에 사본이 와서 따로 권한을 쥘 일이 없다.
final class FilePicker: NSObject, UIDocumentPickerDelegate {
    static let shared = FilePicker()
    private var done: (([URL]) -> Void)?

    func pick(_ done: @escaping ([URL]) -> Void) {
        self.done?([])
        self.done = done
        let p = UIDocumentPickerViewController(forOpeningContentTypes: [.item], asCopy: true)
        p.allowsMultipleSelection = true
        p.delegate = self
        guard let top = Self.topController() else { finish([]); return }
        top.present(p, animated: true)
    }

    func documentPicker(_ controller: UIDocumentPickerViewController, didPickDocumentsAt urls: [URL]) { finish(urls) }
    func documentPickerWasCancelled(_ controller: UIDocumentPickerViewController) { finish([]) }

    private func finish(_ urls: [URL]) {
        let d = done
        done = nil
        d?(urls)
    }

    private static func topController() -> UIViewController? {
        let scene = UIApplication.shared.connectedScenes.compactMap { $0 as? UIWindowScene }
            .first { $0.activationState == .foregroundActive } ?? UIApplication.shared.connectedScenes.first as? UIWindowScene
        var c = scene?.windows.first { $0.isKeyWindow }?.rootViewController ?? scene?.windows.first?.rootViewController
        while let next = c?.presentedViewController { c = next }
        return c
    }
}
