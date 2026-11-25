import Foundation

// 공용 도구 — 정규식, JSON 값 다루기, Python 과 같은 문자열 연산.
//
// 문자열은 Python 처럼 **코드 포인트(유니코드 스칼라)** 로 다룬다. Swift 의 String 연산
// (contains · hasSuffix · count) 은 글자(grapheme)와 정준 등가로 비교해서, 조합 문자가
// 섞이면 Python · Kotlin 과 다른 답을 낸다.

// MARK: - 정규식

/// NSRegularExpression(ICU) — \d \s \w 가 유니코드라 Android 의 ICU 정규식과 같다.
public final class Rx {
    let re: NSRegularExpression

    public init(_ pattern: String) {
        re = try! NSRegularExpression(pattern: pattern)
    }

    /// 첫 일치 (Kotlin Regex.find).
    func find(_ s: String) -> RxMatch? {
        let ns = s as NSString
        guard let m = re.firstMatch(in: s, range: NSRange(location: 0, length: ns.length)) else { return nil }
        return RxMatch(ns: ns, m: m)
    }

    /// 글자 그대로 바꾼다($ · \ 를 특수 문자로 보지 않음).
    func replace(_ s: String, _ with: String) -> String {
        let ns = s as NSString
        return re.stringByReplacingMatches(in: s, range: NSRange(location: 0, length: ns.length),
                                           withTemplate: NSRegularExpression.escapedTemplate(for: with))
    }

    func replace(_ s: String, _ transform: (RxMatch) -> String) -> String {
        let ns = s as NSString
        var out = ""
        var last = 0
        for m in re.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
            out += ns.substring(with: NSRange(location: last, length: m.range.location - last))
            out += transform(RxMatch(ns: ns, m: m))
            last = m.range.location + m.range.length
        }
        out += ns.substring(from: last)
        return out
    }

    /// Kotlin Regex.split / Python re.split (빈 조각도 남긴다).
    func split(_ s: String) -> [String] {
        let ns = s as NSString
        var out: [String] = []
        var last = 0
        for m in re.matches(in: s, range: NSRange(location: 0, length: ns.length)) {
            out.append(ns.substring(with: NSRange(location: last, length: m.range.location - last)))
            last = m.range.location + m.range.length
        }
        out.append(ns.substring(from: last))
        return out
    }
}

struct RxMatch {
    let ns: NSString
    let m: NSTextCheckingResult

    /// i번째 묶음, 걸리지 않았으면 nil.
    func g(_ i: Int) -> String? {
        let r = m.range(at: i)
        return r.location == NSNotFound ? nil : ns.substring(with: r)
    }
}

// MARK: - 코드 포인트 문자열 연산

extension String {
    /// Python `needle in self`.
    func has(_ needle: String) -> Bool {
        if needle.isEmpty { return true }
        // UTF-8 바이트 부분열 일치 = 코드 포인트 부분열 일치(UTF-8 은 자기 동기화).
        return utf8.firstRange(of: needle.utf8) != nil
    }

    func scalarHasSuffix(_ suffix: String) -> Bool {
        unicodeScalars.reversed().starts(with: suffix.unicodeScalars.reversed())
    }

    func scalarHasPrefix(_ prefix: String) -> Bool {
        unicodeScalars.starts(with: prefix.unicodeScalars)
    }

    /// Python len().
    var scalarCount: Int { unicodeScalars.count }

    func scalarDropLast(_ n: Int) -> String {
        String(String.UnicodeScalarView(unicodeScalars.dropLast(n)))
    }

    func scalarPrefix(_ n: Int) -> String {
        String(String.UnicodeScalarView(unicodeScalars.prefix(n)))
    }

    /// Python str.strip(chars).
    func strip(_ chars: Set<Unicode.Scalar>) -> String {
        let s = unicodeScalars
        guard let a = s.firstIndex(where: { !chars.contains($0) }) else { return "" }
        let b = s.lastIndex(where: { !chars.contains($0) })!
        return String(String.UnicodeScalarView(s[a...b]))
    }

    /// Python str.strip() / Kotlin trim().
    var trimmed: String { trimmingCharacters(in: .whitespacesAndNewlines) }

    /// Kotlin substringBeforeLast('.').
    func beforeLast(_ c: Character) -> String {
        guard let i = lastIndex(of: c) else { return self }
        return String(self[..<i])
    }
}

/// Python int(s) for a run of digits — 유니코드 숫자(１６)도 읽는다(\d 가 그것도 잡으므로).
func pint(_ s: String) -> Int? {
    let t = s.trimmed
    if t.isEmpty { return nil }
    var neg = false
    var body = Substring.UnicodeScalarView(t.unicodeScalars)
    if let f = body.first, f == "-" || f == "+" {
        neg = f == "-"
        body = body.dropFirst()
    }
    if body.isEmpty { return nil }
    var n = 0
    for u in body {
        guard u.properties.numericType == .decimal, let d = u.properties.numericValue else { return nil }
        let (m, o1) = n.multipliedReportingOverflow(by: 10)
        let (a, o2) = m.addingReportingOverflow(Int(d))
        if o1 || o2 { return nil }
        n = a
    }
    return neg ? -n : n
}

// MARK: - JSON 값

/// JSONSerialization 이 주는 Any 를 종류별로 — NSNumber 는 bool · 정수 · 실수를 가려낸다
/// (`as? Int` 는 true 도 1 로 받아 버린다).
enum JV {
    case null, bool(Bool), int(Int), double(Double), string(String), array([Any]), object([String: Any]), other

    init(_ v: Any?) {
        guard let v = v, !(v is NSNull) else { self = .null; return }
        if let s = v as? String { self = .string(s); return }
        if let n = v as? NSNumber {
            if CFGetTypeID(n) == CFBooleanGetTypeID() { self = .bool(n.boolValue); return }
            if CFNumberIsFloatType(n) { self = .double(n.doubleValue); return }
            self = .int(n.intValue); return
        }
        if let a = v as? [Any] { self = .array(a); return }
        if let o = v as? [String: Any] { self = .object(o); return }
        self = .other
    }
}

/// Python int(x) — 정수 · 실수(버림) · bool · 숫자 문자열. 그 밖은 nil.
func pyInt(_ v: Any?) -> Int? {
    switch JV(v) {
    case .bool(let b): return b ? 1 : 0
    case .int(let i): return i
    case .double(let d): return d.isFinite && abs(d) < 9e18 ? Int(d) : nil
    case .string(let s): return Int(s.trimmed)
    default: return nil
    }
}

/// Python 참거짓.
func pyTruthy(_ v: Any?) -> Bool {
    switch JV(v) {
    case .null: return false
    case .bool(let b): return b
    case .int(let i): return i != 0
    case .double(let d): return d != 0
    case .string(let s): return !s.isEmpty
    case .array(let a): return !a.isEmpty
    case .object(let o): return !o.isEmpty
    case .other: return true
    }
}

/// Kotlin 의 값.toString() (org.json) — 설정값을 글자로 읽을 때.
func jsonText(_ v: Any?) -> String {
    switch JV(v) {
    case .null: return "null"
    case .bool(let b): return b ? "true" : "false"
    case .int(let i): return String(i)
    case .double(let d): return d == d.rounded() && abs(d) < 1e15 ? String(Int(d)) : String(d)
    case .string(let s): return s
    case .array, .object, .other:
        if let v = v, JSONSerialization.isValidJSONObject(v),
           let d = try? JSONSerialization.data(withJSONObject: v), let s = String(data: d, encoding: .utf8) {
            return s
        }
        return "\(v ?? "")"
    }
}

public enum JSON {
    /// 문자열 → 값(객체 · 배열 · 조각 모두). 깨졌으면 nil.
    public static func parse(_ s: String) -> Any? {
        guard let d = s.data(using: .utf8) else { return nil }
        return parse(d)
    }

    public static func parse(_ d: Data) -> Any? {
        try? JSONSerialization.jsonObject(with: d, options: [.fragmentsAllowed])
    }

    public static func string(_ v: Any, pretty: Bool = false) -> String {
        var opt: JSONSerialization.WritingOptions = [.fragmentsAllowed, .withoutEscapingSlashes]
        if pretty { opt.insert(.prettyPrinted); opt.insert(.sortedKeys) }
        guard let d = try? JSONSerialization.data(withJSONObject: v, options: opt) else { return "null" }
        return String(data: d, encoding: .utf8) ?? "null"
    }

    /// org.json similar() — 순서 없는 객체 비교, 숫자는 값으로.
    public static func equal(_ a: Any?, _ b: Any?) -> Bool {
        switch (JV(a), JV(b)) {
        case (.null, .null): return true
        case let (.bool(x), .bool(y)): return x == y
        case let (.string(x), .string(y)): return x == y
        case let (.int(x), .int(y)): return x == y
        case let (.int(x), .double(y)), let (.double(y), .int(x)): return Double(x) == y
        case let (.double(x), .double(y)): return x == y
        case let (.array(x), .array(y)):
            return x.count == y.count && zip(x, y).allSatisfy { equal($0, $1) }
        case let (.object(x), .object(y)):
            return Set(x.keys) == Set(y.keys) && x.allSatisfy { k, v in equal(v, y[k]) }
        default: return false
        }
    }
}
