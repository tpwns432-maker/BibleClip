package com.bibleclip.app.core

/**
 * Port of bibleclip/core/formatter.py — one version's verses → output text,
 * per the user's format settings. Pinned by tests/golden/format.json.
 */
class Formatter(private val s: Settings) {

    fun formatVersionOutput(db: BibleDb, bookNum: Int, chapter: Int, verses: List<Int>,
                            verseData: List<Pair<Int, String>>): String {
        // Each version uses its OWN book names (KRV 룻기 / ESV Ruth).
        val (dbShort, dbLong) = db.books[bookNum] ?: ("?" to "?")
        val bookDisplay = if (useLong()) dbLong else dbShort

        val verseList = if (verses.isNotEmpty()) formatVerseList(verses, s.str("range_symbol", "-")) else ""
        val ref = if (s.str("chapter_verse_format", "") == "korean") {
            if (verseList.isNotEmpty()) "$bookDisplay ${chapter}장 ${verseList}절" else "$bookDisplay ${chapter}장"
        } else {
            if (verseList.isNotEmpty()) "$bookDisplay $chapter:$verseList" else "$bookDisplay $chapter"
        }

        val header = if (s.truthy("show_version_header", true)) "[${db.name}]" else ""
        val body = buildBody(verseData, chapter)

        // FEAT-02 user template replaces the standard assembly when enabled.
        val tmpl = s.str("custom_format_template", "")
        if (s.truthy("custom_format_enabled") && tmpl.isNotBlank()) {
            return applyTemplate(tmpl, dbLong, dbShort, chapter, verseList, body, db.name)
        }

        if (s.truthy("hide_reference")) {
            return if (header.isNotEmpty()) "$header\n$body" else body
        }

        val refDisplay = when (s.str("bracket_style", "none")) {
            "[]" -> "[$ref]"
            "()" -> "($ref)"
            else -> ref
        }
        val sep = s.str("ref_body_separator", " ")
        return if (s.str("ref_position", "before") == "before") {
            if (header.isNotEmpty()) "$header $refDisplay$sep$body" else "$refDisplay$sep$body"
        } else {
            if (header.isNotEmpty()) "$header $body$sep$refDisplay" else "$body$sep$refDisplay"
        }
    }

    /** FEAT-05: first two versions in ONE block via {content}/{content2} etc. */
    fun formatParallel(bookNum: Int, chapter: Int,
                       col1: Pair<BibleDb, List<Pair<Int, String>>>,
                       col2: Pair<BibleDb, List<Pair<Int, String>>>): String {
        val (db1, vd1) = col1
        val (db2, vd2) = col2
        val (short1, long1) = db1.books[bookNum] ?: ("?" to "?")
        val verses1 = vd1.map { it.first }
        val verseList = if (verses1.isNotEmpty()) formatVerseList(verses1, s.str("range_symbol", "-")) else ""
        return applyTemplate(s.str("custom_format_template", ""), long1, short1, chapter, verseList,
            buildBody(vd1, chapter), db1.name, buildBody(vd2, chapter), db2.name)
    }

    private fun buildBody(verseData: List<Pair<Int, String>>, chapter: Int): String {
        if (s.str("output_mode", "") == "newline" && verseData.size > 1) {
            val cv = s.truthy("newline_show_cv")
            return verseData.joinToString("\n") { (v, t) -> if (cv) "$chapter:$v $t" else "$v $t" }
        }
        // inline — ' // ' across non-consecutive verse groups (1-2,4-6).
        val out = StringBuilder()
        var prev: Int? = null
        for ((v, t) in verseData) {
            if (prev != null) out.append(if (v != prev + 1) " // " else " ")
            out.append(t)
            prev = v
        }
        return out.toString()
    }

    private fun useLong() = s.str("book_name", "short").startsWith("long")

    companion object {
        private val TAG = rx("""\{(\w+)\}""")

        /** Unknown {tags} stay verbatim so a typo is visible. */
        fun applyTemplate(tmpl: String, bookFull: String, bookShort: String, chapter: Int,
                          verseList: String, content: String, version: String,
                          content2: String = "", version2: String = ""): String {
            val repl = mapOf(
                "book_full" to bookFull, "book_short" to bookShort,
                "chap" to chapter.toString(), "verse" to verseList,
                "content" to content, "version" to version,
                "content2" to content2, "version2" to version2,
            )
            return TAG.replace(tmpl) { m -> repl[m.groupValues[1]] ?: m.value }
        }

        /** [16,17,18,20] → "16-18,20". */
        fun formatVerseList(verses: List<Int>, rangeSym: String = "-"): String {
            if (verses.isEmpty()) return ""
            val ranges = mutableListOf<String>()
            var start = verses[0]
            var end = verses[0]
            for (v in verses.drop(1)) {
                if (v == end + 1) {
                    end = v
                } else {
                    ranges += if (start != end) "$start$rangeSym$end" else "$start"
                    start = v
                    end = v
                }
            }
            ranges += if (start != end) "$start$rangeSym$end" else "$start"
            return ranges.joinToString(",")
        }
    }
}
