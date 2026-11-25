import Foundation

/// bibleclip/text_utils.py 이식 (한글 자모 조립 + 절 본문 정리) — TextUtils.kt 와 같다.
public final class TextUtils {
    private let t: Tables
    private let choIndex: [String: Int]
    private let jungIndex: [String: Int]
    private let jongIndex: [String: Int]

    public init(_ tables: Tables) {
        t = tables
        // indexOf = 첫 자리 — 같은 값이 두 번 있으면 앞의 것.
        func index(_ l: [String]) -> [String: Int] {
            var m: [String: Int] = [:]
            for (i, s) in l.enumerated() where m[s] == nil { m[s] = i }
            return m
        }
        choIndex = index(tables.choseong)
        jungIndex = index(tables.jungseong)
        jongIndex = index(tables.jongseong)
    }

    private func isCho(_ j: String) -> Bool { choIndex[j] != nil }
    private func isJung(_ j: String) -> Bool { jungIndex[j] != nil }

    public func assembleHangul(_ jamo: [String]) -> String {
        var out = ""
        var i = 0
        while i < jamo.count {
            let j = jamo[i]
            if isCho(j) && i + 1 < jamo.count && isJung(jamo[i + 1]) {
                let cho = choIndex[j]!
                i += 1
                var jungChar = jamo[i]
                if i + 1 < jamo.count && isJung(jamo[i + 1]),
                   let c = t.complexJungseong[Tables.pairKey(jungChar, jamo[i + 1])] {
                    jungChar = c
                    i += 1
                }
                let jung = jungIndex[jungChar] ?? -1
                var jong = 0
                if i + 1 < jamo.count && isCho(jamo[i + 1]) {
                    let potential = jamo[i + 1]
                    if i + 2 < jamo.count && isJung(jamo[i + 2]) {
                        // 다음 자모가 새 음절을 시작한다
                    } else if jongIndex[potential] != nil {
                        let cplx = (i + 2 < jamo.count && isCho(jamo[i + 2]))
                            ? t.complexJongseong[Tables.pairKey(potential, jamo[i + 2])] : nil
                        if let cplx = cplx {
                            if i + 3 < jamo.count && isJung(jamo[i + 3]) {
                                jong = jongIndex[potential]!
                                i += 1
                            } else {
                                jong = jongIndex[cplx] ?? -1
                                i += 2
                            }
                        } else {
                            jong = jongIndex[potential]!
                            i += 1
                        }
                    }
                }
                let code = 0xAC00 + cho * 21 * 28 + jung * 28 + jong
                if let u = Unicode.Scalar(UInt32(max(0, code))) { out.unicodeScalars.append(u) }
            } else {
                out += j
            }
            i += 1
        }
        return out
    }

    /// 'dy' → '요' — 모든 글자가 두벌식 표에 있을 때만, 아니면 nil ('' → '').
    public func convertQwertyToHangul(_ text: String) -> String? {
        var jamo: [String] = []
        for u in text.unicodeScalars {
            guard let j = t.qwertyToHangul[u] else { return nil }
            jamo.append(j)
        }
        return assembleHangul(jamo)
    }

    public func cleanText(_ text: String?) -> String {
        guard let text = text, !text.isEmpty else { return "" }
        var s = TextUtils.strongs.replace(text, "")
        s = TextUtils.footnote.replace(s, "")
        s = TextUtils.title.replace(s, "")
        s = TextUtils.tag.replace(s, "")
        s = TextUtils.bracketTitle.replace(s, "")
        return TextUtils.spaces.replace(s, " ").trimmed
    }

    private static let strongs = Rx(#"<S>\d+</S>"#)
    private static let footnote = Rx(#"<f>[^<]*</f>"#)
    private static let title = Rx(#"<n>\[?[^\]<]*\]?</n>"#)
    private static let tag = Rx(#"<[^>]+/?>"#)
    private static let bracketTitle = Rx(#"\[[가-힣a-zA-Z0-9\s,.:]+\]\s*"#)
    private static let spaces = Rx(#"\s+"#)
}
