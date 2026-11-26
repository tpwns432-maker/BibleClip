import Foundation

/// 앱과 공유 메뉴 확장(BibleClipAction)이 함께 보는 곳 — App Group 컨테이너.
///
/// 확장은 앱의 Documents 를 볼 수 없다. 그래서 앱이 설정 · 별칭 · 사용자가 넣은 역본을
/// 그룹 컨테이너에 비춰 두고(mirror), 확장은 거기서 읽는다. 원본은 늘 앱의 Documents.
///
/// 그룹 이름: 서명하는 Impactor 가 무료 계정용으로 이름 뒤에 팀 ID 를 붙인다
/// (group.com.bibleclip.app.sejun → group.com.bibleclip.app.sejun.ABCDE12345).
/// 그래서 실제 이름은 서명 때 넣어진 embedded.mobileprovision 의 권한 목록에서 찾는다.
enum SharedStore {
    static let baseGroup = "group.com.bibleclip.app.sejun"
    static let settingsName = "bibleclip_settings.json"
    static let biblesName = "bible_versions"
    static let aliasName = "aliases_override.json"

    static let groupID: String? = {
        if let groups = provisionedGroups() {
            return groups.first { $0.hasPrefix(baseGroup) } ?? groups.first
        }
        return baseGroup
    }()

    /// nil 이면 그룹을 쓸 수 없다(서명에 그룹 권한이 없음) — 앱은 그냥 넘어가고, 확장은 기본값으로.
    static let container: URL? = groupID.flatMap {
        FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: $0)
    }

    /// embedded.mobileprovision(CMS 로 감싼 plist)에서 application-groups 를 꺼낸다.
    private static func provisionedGroups() -> [String]? {
        guard let url = Bundle.main.url(forResource: "embedded", withExtension: "mobileprovision"),
              let data = try? Data(contentsOf: url),
              let start = data.range(of: Data("<?xml".utf8)),
              let end = data.range(of: Data("</plist>".utf8), in: start.lowerBound..<data.endIndex),
              let plist = try? PropertyListSerialization.propertyList(
                  from: data.subdata(in: start.lowerBound..<end.upperBound), format: nil) as? [String: Any],
              let ent = plist["Entitlements"] as? [String: Any]
        else { return nil }
        return ent["com.apple.security.application-groups"] as? [String]
    }

    static func isBible(_ name: String) -> Bool {
        let low = name.lowercased()
        return low.hasSuffix(".sqlite3") || low.hasSuffix(".sqlite") || low.hasSuffix(".db")
    }
}
