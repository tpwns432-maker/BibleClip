package com.bibleclip.app.core

/** A parsed reference: canonical book + chapter + verses (empty = whole chapter). */
data class Ref(val book: Book, val chapter: Int, val verses: List<Int>)

/**
 * Port of bibleclip/core/engine.py — Korean/English reference text → Ref.
 * Behaviour is pinned by tests/golden/engine.json; change the Python engine
 * first, regenerate the golden files, then mirror the change here.
 */
class Engine(private val t: Tables, private val text: TextUtils) {

    /**
     * Parse the first reference in [input]. [extraBooks] is the
     * {normalized_name: book_num} alias map (Library.bookAliases).
     */
    fun parseReference(input: String, extraBooks: Map<String, Int>? = null): List<Ref> {
        val s = input.trim()
        if (s.isEmpty()) return emptyList()

        LEADING_ALIAS.find(s)?.let { m ->
            val canon = lookupAliasToken(m.g(1)!!, extraBooks)
            if (canon != null) {
                val vs = m.g(3) ?: m.g(4)
                return listOf(Ref(canon, m.g(2)!!.toInt(), if (vs != null) parseVerses(vs) else emptyList()))
            }
        }
        KOREAN_STYLE.find(s)?.let { m ->
            val vs = m.g(3)
            val book = lookupBook(m.g(1)!!, vs != null, extraBooks)
            if (book != null) {
                return listOf(Ref(book, m.g(2)!!.toInt(), if (vs != null) parseVerses(vs) else emptyList()))
            }
        }
        VERSE.find(s)?.let { m ->
            val vs = m.g(3) ?: m.g(4)
            val book = lookupBook(m.g(1)!!, m.g(3) != null, extraBooks)
            if (book != null) {
                return listOf(Ref(book, m.g(2)!!.toInt(), if (vs != null) parseVerses(vs) else emptyList()))
            }
        }
        ENGLISH.find(s)?.let { m ->
            val vs = m.g(3)
            val book = lookupEnglishBook(m.g(1)!!.trim(), extraBooks)
            if (book != null) {
                return listOf(Ref(book, m.g(2)!!.toInt(), if (vs != null) parseVerses(vs) else emptyList()))
            }
        }
        return emptyList()
    }

    fun canon(bookNum: Int): Book? = t.canon[bookNum]

    private fun lookupBook(bookStr: String, hasVerseSeparator: Boolean, extraBooks: Map<String, Int>?): Book? {
        t.koreanBookMap[bookStr]?.let { return it }
        val converted = text.convertQwertyToHangul(bookStr)
        if (converted != null) t.koreanBookMap[converted]?.let { return it }
        // Custom alias fallback: user aliases + every loaded version's own book names.
        if (extraBooks != null) {
            var bn = extraBooks[normBook(bookStr)]
            if (bn == null && converted != null) bn = extraBooks[normBook(converted)]
            if (bn != null) return canon(bn)
        }
        return null
    }

    private fun lookupEnglishBook(bookStr: String, extraBooks: Map<String, Int>?): Book? {
        val key = normBook(bookStr)
        val bn = t.englishBookMap[key] ?: extraBooks?.get(key)
        return bn?.let { canon(it) }
    }

    private fun lookupAliasToken(token: String, extraBooks: Map<String, Int>?): Book? {
        val key = normBook(token)
        if (key.isEmpty()) return null
        val bn = extraBooks?.get(key) ?: t.englishBookMap[key]
        return bn?.let { canon(it) }
    }

    companion object {
        private const val VERSES = """(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)"""

        // Book name: letters, a digit only when followed by more letters (요2서) —
        // a trailing digit must stay the chapter ("요15:4" is 요 15:4, not 요1 5:4).
        private val VERSE = rx(
            """([가-힣a-zA-Z]+(?:\d[가-힣a-zA-Z]+)*)\s*(\d+)\s*(?:장\s*)?""" +
                """(?:[:：]\s*$VERSES|(?:편\s*)?(\d+)\s*절)?(?:\s*절)?"""
        )
        private val KOREAN_STYLE = rx(
            """([가-힣]+(?:\d[가-힣]+)*)\s*(\d+)\s*장""" +
                """(?:\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,，]\s*\d+(?:\s*[-~]\s*\d+)?)*)\s*절?)?"""
        )
        private val ENGLISH = rx(
            """(\d?\s*[a-zA-Z]+)\s+(\d+)(?:[:]\s*(\d+(?:\s*[-~]\s*\d+)?(?:\s*[,]\s*\d+(?:\s*[-~]\s*\d+)?)*))?"""
        )
        // Leading-number aliases (1요, 1Jn): resolved through the alias/English map only.
        private val LEADING_ALIAS = rx(
            """(\d{1,3}\s*[가-힣a-zA-Z]+)\s*(\d+)\s*(?:장\s*)?""" +
                """(?:[:：]\s*$VERSES|(?:편\s*)?(\d+)\s*절)?(?:\s*절)?"""
        )
        private val VERSE_SPLIT = Regex("[,，]")
        private val RANGE_SPLIT = Regex("[-~]")

        /** "16,18-20" → [16, 18, 19, 20] (sorted, unique). */
        fun parseVerses(verseStr: String?): List<Int> {
            if (verseStr.isNullOrEmpty()) return emptyList()
            val out = sortedSetOf<Int>()
            for (part in verseStr.replace(" ", "").split(VERSE_SPLIT)) {
                if ('-' in part || '~' in part) {
                    val bounds = part.split(RANGE_SPLIT)
                    if (bounds.size == 2) {
                        val start = bounds[0].trim().toInt()
                        val end = bounds[1].trim().toInt()
                        for (v in start..end) out.add(v)
                    }
                } else {
                    out.add(part.trim().toInt())
                }
            }
            return out.toList()
        }

        /** Alias key: lowercase, no spaces or dots ('1 Ths.' → '1ths'). */
        fun normBook(s: String?): String =
            (s ?: "").trim().lowercase().replace(" ", "").replace(".", "")

        private fun MatchResult.g(i: Int): String? = groups[i]?.value
    }
}
