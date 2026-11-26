import BibleClipCore
import SwiftUI
import UIKit
import UniformTypeIdentifiers

/// 다른 앱에서 글자를 고르고 공유… → "BibleClip 구절" — android ProcessTextActivity 의 아이폰판.
/// 고른 참조("요 3:16")를 설정대로 본문으로 바꿔 클립보드에 넣고, 미리보기를 띄운다.
/// [바꾸기] 는 고른 글자를 본문으로 바꿔 돌려준다 — 받아 주는 앱(편집 중인 글)에서만 바뀐다.
final class ActionViewController: UIViewController {
    private let model = ActionModel()

    override func viewDidLoad() {
        super.viewDidLoad()
        let host = UIHostingController(rootView: ActionView(model: model,
                                                            close: { [weak self] in self?.finish(nil) },
                                                            replace: { [weak self] t in self?.finish(t) }))
        addChild(host)
        host.view.frame = view.bounds
        host.view.autoresizingMask = [.flexibleWidth, .flexibleHeight]
        view.addSubview(host.view)
        host.didMove(toParent: self)
        readInput { [model] text in model.run(text) }
    }

    /// 넘어온 글자 — 일반 글자 또는 꾸민 글자(attributedContentText).
    private func readInput(_ done: @escaping (String) -> Void) {
        let items = extensionContext?.inputItems as? [NSExtensionItem] ?? []
        if let t = items.lazy.compactMap({ $0.attributedContentText?.string }).first(where: { !$0.isEmpty }) {
            return done(t)
        }
        let type = UTType.plainText.identifier
        guard let p = items.lazy.flatMap({ $0.attachments ?? [] }).first(where: { $0.hasItemConformingToTypeIdentifier(type) })
        else { return done("") }
        p.loadItem(forTypeIdentifier: type) { v, _ in
            let s = (v as? String) ?? (v as? NSAttributedString)?.string
                ?? (v as? Data).flatMap { String(data: $0, encoding: .utf8) } ?? ""
            DispatchQueue.main.async { done(s) }
        }
    }

    private func finish(_ replacement: String?) {
        var out: [NSExtensionItem] = []
        if let r = replacement {
            let item = NSExtensionItem()
            item.attributedContentText = NSAttributedString(string: r)
            item.attachments = [NSItemProvider(item: r as NSString, typeIdentifier: UTType.plainText.identifier)]
            out = [item]
        }
        extensionContext?.completeRequest(returningItems: out, completionHandler: nil)
    }
}

final class ActionModel: ObservableObject {
    enum State {
        case working
        case done(label: String, text: String)
        case failed(String)
    }

    @Published var state: State = .working

    func run(_ input: String) {
        DispatchQueue.global(qos: .userInitiated).async {
            let result = Self.convert(input)
            DispatchQueue.main.async { self.state = result }
        }
    }

    private static func convert(_ input: String) -> State {
        let trimmed = input.trimmingCharacters(in: .whitespacesAndNewlines)
        if trimmed.isEmpty { return .failed("고른 글자가 없어요.") }
        guard let lib = makeLibrary() else { return .failed("성경 파일을 열지 못했어요.") }
        switch lib.buildOutput(trimmed) {
        case let .reference(_, chapter, verses, shortName, text, _)?:
            DispatchQueue.main.sync { UIPasteboard.general.string = text }
            let vs = BibleClipCore.Formatter.formatVerseList(verses)
            return .done(label: vs.isEmpty ? "\(shortName) \(chapter)" : "\(shortName) \(chapter):\(vs)", text: text)
        case .keyword?, nil:
            return .failed("‘\(trimmed.prefix(30))’ 에서 성경 구절을 찾지 못했어요.\n예: 요 3:16, 창세기 1:1-3")
        }
    }

    /// 앱 안 기본 역본 + 앱이 그룹 컨테이너에 비춰 둔 설정 · 역본(SharedStore) — AppModel.load 와 같은 순서.
    private static func makeLibrary() -> Library? {
        // 확장은 BibleClip.app/PlugIns/BibleClipAction.appex — 앱 묶음은 두 단계 위.
        let app = Bundle.main.bundleURL.deletingLastPathComponent().deletingLastPathComponent()
        let bundleDir = app.appendingPathComponent("Bundle")
        guard let tablesJson = try? String(contentsOf: bundleDir.appendingPathComponent("core/tables.json"), encoding: .utf8)
        else { return nil }
        let tables = Tables(json: tablesJson)
        let shared = SharedStore.container
        let saved = shared.flatMap { try? Data(contentsOf: $0.appendingPathComponent(SharedStore.settingsName)) }
            .flatMap { JSON.parse($0) as? [String: Any] }
        let settings = Settings.of(tables.defaultSettings, saved)
        let aliasFile = shared?.appendingPathComponent(SharedStore.biblesName).appendingPathComponent(SharedStore.aliasName)
        let lib = Library(tables, settings) {
            aliasFile.flatMap { try? Data(contentsOf: $0) }.flatMap { JSON.parse($0) as? [String: Any] } ?? [:]
        }
        var dirs = [bundleDir.appendingPathComponent("bible_versions")]
        if let shared { dirs.append(shared.appendingPathComponent(SharedStore.biblesName)) }
        for dir in dirs {
            for name in ((try? FileManager.default.contentsOfDirectory(atPath: dir.path)) ?? []).sorted()
            where SharedStore.isBible(name) && lib.dbs[BibleDb.nameOf(name)] == nil {
                if let db = try? BibleDb(path: dir.appendingPathComponent(name).path, text: lib.text) { _ = lib.add(db) }
            }
        }
        if lib.order.isEmpty { return nil }
        lib.validateSettings()
        return lib
    }
}

struct ActionView: View {
    @ObservedObject var model: ActionModel
    let close: () -> Void
    let replace: (String) -> Void

    var body: some View {
        NavigationStack {
            Group {
                switch model.state {
                case .working:
                    ProgressView()
                case let .done(_, text):
                    ScrollView {
                        Text(text)
                            .font(.body)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                            .padding()
                    }
                    .safeAreaInset(edge: .bottom) {
                        Button { replace(text) } label: {
                            Text("고른 글자를 본문으로 바꾸기").frame(maxWidth: .infinity)
                        }
                        .buttonStyle(.bordered)
                        .padding()
                    }
                case let .failed(msg):
                    Text(msg)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(.secondary)
                        .padding()
                }
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .navigationTitle(title)
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .confirmationAction) { Button("완료", action: close) }
            }
        }
    }

    private var title: String {
        switch model.state {
        case .working: return "BibleClip"
        case let .done(label, _): return "\(label) 복사됨"
        case .failed: return "BibleClip"
        }
    }
}
