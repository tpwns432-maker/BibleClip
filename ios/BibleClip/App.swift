import SwiftUI
import WebKit

// 시험 앱 (docs/IOS_PLAN.md '위험' 단계): 이 아이폰에 무료 Apple ID로 서명한 앱이 깔리고,
// WKWebView ↔ Swift 브리지가 도는지만 본다. 1단계에서 이 화면이 web/ 로 바뀐다.

@main
struct BibleClipApp: App {
    var body: some Scene {
        WindowGroup {
            WebView().ignoresSafeArea()
        }
    }
}

struct WebView: UIViewRepresentable {
    func makeUIView(context: Context) -> WKWebView {
        let config = WKWebViewConfiguration()
        // window.webkit.messageHandlers.api.postMessage(...) → Promise 로 답이 온다.
        // 1단계의 bridge.js 가 window.pywebview.api 를 이 길 위에 얹는다.
        config.userContentController.addScriptMessageHandler(
            Bridge(), contentWorld: .page, name: "api")
        let web = WKWebView(frame: .zero, configuration: config)
        web.isInspectable = true  // 윈도우의 ios-webkit-debug-proxy 로 붙어 보기
        web.loadHTMLString(Self.page, baseURL: nil)
        return web
    }

    func updateUIView(_ uiView: WKWebView, context: Context) {}

    static let page = """
    <!doctype html><html lang="ko"><head><meta charset="utf-8">
    <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
    <style>
      :root { color-scheme: light dark; }
      body { font: 17px -apple-system, sans-serif; margin: 0;
             padding: calc(env(safe-area-inset-top) + 24px) 20px 24px; }
      h1 { font-size: 26px; } .ok { color: #2e8b57; } .bad { color: #c0392b; }
      li { margin: 8px 0; }
    </style></head><body>
    <h1>BibleClip 시험 앱</h1>
    <p>이 화면이 보이면 <b>설치는 성공</b>입니다.</p>
    <ul>
      <li>브리지: <span id="bridge">확인 중…</span></li>
      <li>기기: <span id="info">—</span></li>
    </ul>
    <script>
      const el = id => document.getElementById(id);
      window.webkit.messageHandlers.api.postMessage({ method: "ping" })
        .then(r => { el("bridge").textContent = "동작함 ✓"; el("bridge").className = "ok";
                     el("info").textContent = r; })
        .catch(e => { el("bridge").textContent = "실패: " + e; el("bridge").className = "bad"; });
    </script>
    </body></html>
    """
}

final class Bridge: NSObject, WKScriptMessageHandlerWithReply {
    func userContentController(_ controller: WKUserContentController,
                               didReceive message: WKScriptMessage,
                               replyHandler: @escaping (Any?, String?) -> Void) {
        guard let body = message.body as? [String: Any],
              let method = body["method"] as? String else {
            replyHandler(nil, "bad message"); return
        }
        switch method {
        case "ping":
            let d = UIDevice.current
            let ver = Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "?"
            replyHandler("\(d.model) · \(d.systemName) \(d.systemVersion) · 앱 \(ver)", nil)
        default:
            replyHandler(nil, "unknown method: \(method)")
        }
    }
}
