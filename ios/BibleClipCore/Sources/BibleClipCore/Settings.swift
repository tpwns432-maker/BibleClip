import Foundation

/// 데스크톱 설정 사전(bibleclip_settings.json) — 같은 키, 같은 JSON. 읽기는 Python 의
/// `s.get(key, default)` + 참거짓을 따른다(서식기가 거기에 기댄다). Settings.kt 이식.
public final class Settings {
    public var json: [String: Any]

    public init(_ json: [String: Any]) { self.json = json }

    /// 값, JSON null 이면 nil.
    public subscript(key: String) -> Any? {
        get {
            guard let v = json[key], !(v is NSNull) else { return nil }
            return v
        }
        set { json[key] = newValue ?? NSNull() }
    }

    public func str(_ key: String, _ def: String) -> String {
        guard let v = self[key] else { return def }
        return jsonText(v)
    }

    /// `s.get(key, default)` 의 Python 참거짓.
    public func truthy(_ key: String, _ def: Bool = false) -> Bool {
        json[key] == nil ? def : pyTruthy(self[key])
    }

    public func strings(_ key: String) -> [String] {
        guard let a = self[key] as? [Any] else { return [] }
        return a.map { $0 is NSNull ? "" : jsonText($0) }
    }

    /// 기본값(Library.DEFAULT_SETTINGS) 위에 [saved] 의 아는 키만 덮는다.
    public static func of(_ defaults: [String: Any], _ saved: [String: Any]? = nil) -> Settings {
        var o = defaults
        for (k, v) in saved ?? [:] where o[k] != nil { o[k] = v }
        return Settings(o)
    }
}
