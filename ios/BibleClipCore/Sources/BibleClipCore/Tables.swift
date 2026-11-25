import Foundation

/// 정경 책 하나: MyBible 번호 + 한국어 약칭/정식 이름 (KOREAN_BOOK_MAP 값).
public struct Book: Equatable {
    public let num: Int
    public let short: String
    public let long: String
}

/// bibleclip/constants.py 와 Library.DEFAULT_SETTINGS 의 고정 표 — Tables.kt 이식.
///
/// tests/make_golden.py 가 android/app/src/main/assets/core/tables.json 으로 쓴다.
/// 그 파일을 고치거나 내용을 Swift 로 옮겨 적지 말고 constants.py 를 고쳐 스크립트를 다시 돌린다.
public final class Tables {
    public let koreanBookMap: [String: Book]
    public let englishBookMap: [String: Int]
    let qwertyToHangul: [Unicode.Scalar: String]
    let choseong: [String]
    let jungseong: [String]
    let jongseong: [String]
    let complexJungseong: [String: String]   // "a\u{0}b" → 합친 모음
    let complexJongseong: [String: String]
    public let englishVersions: Set<String>
    public let defaultSettings: [String: Any]
    /// {책 번호: Book} — 한 책의 모든 별칭이 같은 Book 으로 (Engine._canon).
    public let canon: [Int: Book]

    public static let asset = "core/tables.json"

    public init(json: String) {
        let o = JSON.parse(json) as? [String: Any] ?? [:]
        var kb: [String: Book] = [:]
        for (k, v) in o["korean_book_map"] as? [String: Any] ?? [:] {
            let a = v as? [Any] ?? []
            kb[k] = Book(num: pyInt(a[0]) ?? 0, short: a[1] as? String ?? "", long: a[2] as? String ?? "")
        }
        koreanBookMap = kb
        englishBookMap = (o["english_book_map"] as? [String: Any] ?? [:]).compactMapValues { pyInt($0) }
        var q: [Unicode.Scalar: String] = [:]
        for (k, v) in o["qwerty_to_hangul"] as? [String: Any] ?? [:] {
            if let u = k.unicodeScalars.first { q[u] = v as? String ?? "" }
        }
        qwertyToHangul = q
        choseong = o["choseong"] as? [String] ?? []
        jungseong = o["jungseong"] as? [String] ?? []
        jongseong = o["jongseong"] as? [String] ?? []
        complexJungseong = Tables.pairs(o["complex_jungseong"])
        complexJongseong = Tables.pairs(o["complex_jongseong"])
        englishVersions = Set(o["english_versions"] as? [String] ?? [])
        defaultSettings = o["default_settings"] as? [String: Any] ?? [:]
        var c: [Int: Book] = [:]
        for b in kb.values { c[b.num] = b }
        canon = c
    }

    static func pairKey(_ a: String, _ b: String) -> String { a + "\u{0}" + b }

    private static func pairs(_ v: Any?) -> [String: String] {
        var out: [String: String] = [:]
        for t in v as? [[String]] ?? [] where t.count >= 3 {
            out[pairKey(t[0], t[1])] = t[2]
        }
        return out
    }
}
