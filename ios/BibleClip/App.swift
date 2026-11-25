import SwiftUI
import UniformTypeIdentifiers
import WebKit

// 데스크톱 웹 화면(web/, 빌드 때 앱 안 Bundle/web 으로 복사)을 WKWebView 로 띄운다.
// bibleclip://app/ 에서 읽게 해(WKURLSchemeHandler) fetch() 와 저장소가 보통 출처처럼 돈다.
// index.html 에는 bridge.js(window.pywebview.api)와 안드로이드 휴대폰 화면(mobile.css · mobile.js)을 끼운다.

@main
struct BibleClipApp: App {
    var body: some Scene {
        WindowGroup {
            // 노치 · 홈 막대는 피한다(안전 영역 안에만 그린다). 여백 맞춤은 2단계.
            WebView().background(Color(uiColor: .systemBackground))
        }
    }
}

struct WebView: UIViewRepresentable {
    static let scheme = "bibleclip"
    static let start = URL(string: "\(scheme)://app/web/index.html")!

    func makeCoordinator() -> Coordinator { Coordinator() }

    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        config.setURLSchemeHandler(BundleSchemeHandler(), forURLScheme: Self.scheme)
        config.userContentController.addScriptMessageHandler(Bridge(), contentWorld: .page, name: "api")
        let web = WKWebView(frame: .zero, configuration: config)
        web.isInspectable = true  // 윈도우의 ios-webkit-debug-proxy 로 붙어 보기
        web.allowsBackForwardNavigationGestures = false
        web.scrollView.contentInsetAdjustmentBehavior = .never
        web.navigationDelegate = context.coordinator
        web.isOpaque = false
        web.backgroundColor = .systemBackground
        web.load(URLRequest(url: Self.start))
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    final class Coordinator: NSObject, WKNavigationDelegate {
        /// 바깥 링크(GitHub · 릴리스)는 사파리로.
        func webView(_ webView: WKWebView, decidePolicyFor action: WKNavigationAction,
                     decisionHandler: @escaping (WKNavigationActionPolicy) -> Void) {
            guard let url = action.request.url, url.scheme != WebView.scheme, url.scheme != "about" else {
                decisionHandler(.allow); return
            }
            UIApplication.shared.open(url)
            decisionHandler(.cancel)
        }
    }
}

/// bibleclip://app/<경로> → 앱 안 Bundle/<경로>. web/index.html 만 고쳐서 준다.
final class BundleSchemeHandler: NSObject, WKURLSchemeHandler {
    private let root = AppModel.shared.bundleDir.standardizedFileURL

    func webView(_ webView: WKWebView, start task: WKURLSchemeTask) {
        guard let url = task.request.url else { return }
        let path = url.path.hasPrefix("/") ? String(url.path.dropFirst()) : url.path
        let file = root.appendingPathComponent(path).standardizedFileURL
        // Bundle 밖으로 나가는 경로(../)는 막는다.
        guard file.path.hasPrefix(root.path + "/"), var data = try? Data(contentsOf: file) else {
            task.didReceive(HTTPURLResponse(url: url, statusCode: 404, httpVersion: "HTTP/1.1", headerFields: nil)!)
            task.didFinish()
            return
        }
        if path == "web/index.html", let html = String(data: data, encoding: .utf8) {
            data = Data(Self.inject(html).utf8)
        }
        let type = UTType(filenameExtension: file.pathExtension)?.preferredMIMEType ?? "application/octet-stream"
        let headers = ["Content-Type": type.hasPrefix("text/") || type.hasSuffix("javascript") || type.hasSuffix("json")
                       ? "\(type); charset=utf-8" : type,
                       "Content-Length": String(data.count), "Cache-Control": "no-cache"]
        task.didReceive(HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: headers)!)
        task.didReceive(data)
        task.didFinish()
    }

    func webView(_ webView: WKWebView, stop task: WKURLSchemeTask) {}

    /// 휴대폰 스타일은 페이지 것 뒤에(이기게), bridge.js 는 첫 스크립트 앞에, mobile.js 는 마지막 뒤에.
    static func inject(_ html: String) -> String {
        var h = html
        h = insertBefore(h, "</head>", "<link rel=\"stylesheet\" href=\"../android/mobile.css\">\n")
        h = insertBefore(h, "<script", "<script src=\"../ios/bridge.js\"></script>\n")
        h = insertBefore(h, "</body>", "<script src=\"../android/mobile.js\"></script>\n")
        return h
    }

    private static func insertBefore(_ html: String, _ marker: String, _ tag: String) -> String {
        guard let r = html.range(of: marker) else { return html + tag }
        return html.replacingCharacters(in: r.lowerBound..<r.lowerBound, with: tag)
    }
}
