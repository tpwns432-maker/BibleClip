import Foundation

/// 읽어 낸 참조: 정경 책 + 장 + 절들(빈 목록 = 장 전체).
public struct Ref: Equatable {
    public let book: Book
    public let chapter: Int
    public let verses: [Int]
}

/// bibleclip/core/engine.py 이식 — 한/영 참조 글자 → Ref. Engine.kt 와 같다.
/// tests/golden/engine.json 이 동작을 고정한다. Python 엔진을 먼저 고치고 골든을 다시 뽑은 뒤
/// 같은 수정을 여기(그리고 Kotlin)에 옮긴다.
public final class Engine {
    private let t: Tables
    private let text: TextUtils

    public init(_ tables: Tables, _ text: TextUtils) {
        t = tables
        self.text = text
    }

    /// [input] 의 첫 참조. [extraBooks] = {정규화한 이름: 책 번호} 별칭 (Library.bookAliases).
    public func parseReference(_ input: String, _ extraBooks: [String: Int]? = nil) -> [Ref] {
        let s = input.trimmed
        if s.isEmpty { return [] }

        if let m = Engine.leadingAlias.find(s), let canon = lookupAliasToken(m.g(1)!, extraBooks),
           let ch = pint(m.g(2)!) {
            return [Ref(book: canon, chapter: ch, verses: Engine.parseVerses(m.g(3) ?? m.g(4)))]
        }
        if let m = Engine.koreanStyle.find(s) {
            let vs = m.g(3)
            if let book = lookupBook(m.g(1)!, vs != nil, extraBooks), let ch = pint(m.g(2)!) {
                return [Ref(book: book, chapter: ch, verses: Engine.parseVerses(vs))]
            }
        }
        if let m = Engine.verse.find(s) {
            let vs = m.g(3) ?? m.g(4)
            if let book = lookupBook(m.g(1)!, m.g(3) != nil, extraBooks), let ch = pint(m.g(2)!) {
                return [Ref(book: book, chapter: ch, verses: Engine.parseVerses(vs))]
            }
        }
        if let m = Engine.english.find(s) {
            if let book = lookupEnglishBook(m.g(1)!.trimmed, extraBooks), let ch = pint(m.g(2)!) {
                return [Ref(book: book, chapter: ch, verses: Engine.parseVerses(m.g(3)))]
            }
        }
        return []
    }

    public func canon(_ bookNum: Int) -> Book? { t.canon[bookNum] }

    private func lookupBook(_ bookStr: String, _ hasVerseSeparator: Bool, _ extraBooks: [String: Int]?) -> Book? {
        if let b = t.koreanBookMap[bookStr] { return b }
        let converted = text.convertQwertyToHangul(bookStr)
        if let c = converted, let b = t.koreanBookMap[c] { return b }
        // 사용자 별칭 + 넣어 둔 역본마다의 책 이름으로 한 번 더.
        if let extra = extraBooks {
            var bn = extra[Engine.normBook(bookStr)]
            if bn == nil, let c = converted { bn = extra[Engine.normBook(c)] }
            if let bn = bn { return canon(bn) }
        }
        return nil
    }

    private func lookupEnglishBook(_ bookStr: String, _ extraBooks: [String: Int]?) -> Book? {
        let key = Engine.normBook(bookStr)
        guard let bn = t.englishBookMap[key] ?? extraBooks?[key] else { return nil }
        return canon(bn)
    }

    private func lookupAliasToken(_ token: String, _ extraBooks: [String: Int]?) -> Book? {
        let key = Engine.normBook(token)
        if key.isEmpty { return nil }
        guard let bn = extraBooks?[key] ?? t.englishBookMap[key] else { return nil }
        return canon(bn)
    }

    private static let verses = #"(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)"#

    // 책 이름: 글자, 숫자는 뒤에 글자가 더 올 때만(요2서) — 끝의 숫자는 장으로 남겨야 한다
    // ("요15:4" 는 요 15:4 이지 요1 5:4 가 아니다).
    private static let verse = Rx(
        #"([가-힣a-zA-Z]+(?:\d[가-힣a-zA-Z]+)*)\s*(\d+)\s*(?:장\s*)?"# +
            #"(?:[:：]\s*"# + verses + #"|(?:편\s*)?(\d+)\s*절)?(?:\s*절)?"#
    )
    private static let koreanStyle = Rx(
        #"([가-힣]+(?:\d[가-힣]+)*)\s*(\d+)\s*장"# +
            #"(?:\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)\s*절?)?"#
    )
    private static let english = Rx(
        #"(\d?\s*[a-zA-Z]+)\s+(\d+)(?:[:]\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,]\s*\d+(?:\s*[-~]\s*\d+)?)*))?"#
    )
    // 숫자로 시작하는 별칭(1요, 1Jn): 별칭/영어 표로만 푼다.
    private static let leadingAlias = Rx(
        #"(\d{1,3}\s*[가-힣a-zA-Z]+)\s*(\d+)\s*(?:장\s*)?"# +
            #"(?:[:：]\s*"# + verses + #"|(?:편\s*)?(\d+)\s*절)?(?:\s*절)?"#
    )
    private static let verseSplit = Rx("[,，]")
    private static let rangeSplit = Rx("[-~]")

    /// "16,18-20" → [16, 18, 19, 20] (정렬, 중복 없음).
    public static func parseVerses(_ verseStr: String?) -> [Int] {
        guard let vs = verseStr, !vs.isEmpty else { return [] }
        var out = Set<Int>()
        for part in verseSplit.split(vs.replacingOccurrences(of: " ", with: "")) {
            if part.contains("-") || part.contains("~") {
                let bounds = rangeSplit.split(part)
                if bounds.count == 2, let a = pint(bounds[0]), let b = pint(bounds[1]), a <= b {
                    for v in a...b { out.insert(v) }
                }
            } else if let v = pint(part) {
                out.insert(v)
            }
        }
        return out.sorted()
    }

    /// 별칭 키: 소문자, 빈칸 · 점 없음 ('1 Ths.' → '1ths').
    public static func normBook(_ s: String?) -> String {
        (s ?? "").trimmed.lowercased().replacingOccurrences(of: " ", with: "").replacingOccurrences(of: ".", with: "")
    }
}
