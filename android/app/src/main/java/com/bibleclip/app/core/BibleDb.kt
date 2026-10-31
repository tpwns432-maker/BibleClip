package com.bibleclip.app.core

/**
 * One MyBible-format bible (.SQLite3: info / books / verses tables) — port of
 * bibleclip/data/bible_db.py's read API. The SQL lives here; subclasses only
 * run queries (Android: android.database.sqlite, JVM tests: JDBC), so both
 * read the same file the same way.
 */
abstract class BibleDb(val name: String, private val text: TextUtils) {

    /** Rows of [sql] with positional [args]; each row a list of column values. */
    protected abstract fun query(sql: String, vararg args: Any): List<List<Any?>>

    abstract fun close()

    val info: Map<String, String> by lazy {
        query("SELECT name, value FROM info").associate { (k, v) -> k.toString() to (v?.toString() ?: "") }
    }

    val description: String get() = info["description"] ?: name
    val language: String get() = info["language"] ?: "ko"
    val displayName: String get() = "$description [$name]"
    val hasStrongs: Boolean get() = info["strong_numbers"].orEmpty().trim().lowercase() == "true"

    /** (book_number, short, long) in canonical order. */
    val bookList: List<Triple<Int, String, String>> by lazy {
        query("SELECT book_number, short_name, long_name FROM books ORDER BY book_number").map { r ->
            Triple(num(r[0]), r[1]?.toString() ?: "", r[2]?.toString() ?: "")
        }
    }

    val books: Map<Int, Pair<String, String>> by lazy {
        bookList.associate { (bn, s, l) -> bn to (s to l) }
    }

    fun getChapters(book: Int): List<Int> =
        query("SELECT DISTINCT chapter FROM verses WHERE book_number=? ORDER BY chapter", book)
            .map { num(it[0]) }

    /** [(verse, cleaned text)] for one chapter. */
    fun getVerses(book: Int, chapter: Int): List<Pair<Int, String>> =
        query("SELECT verse, text FROM verses WHERE book_number=? AND chapter=? ORDER BY verse", book, chapter)
            .map { num(it[0]) to text.cleanText(it[1]?.toString()) }

    /** Cleaned text of one verse, '' when missing. */
    fun getVerseText(book: Int, chapter: Int, verse: Int): String =
        query("SELECT text FROM verses WHERE book_number=? AND chapter=? AND verse=?", book, chapter, verse)
            .firstOrNull()?.let { text.cleanText(it[0]?.toString()) } ?: ""

    /** MyBible stores numbers as NUMERIC — a driver may hand back Long, Double or String. */
    private fun num(v: Any?): Int = when (v) {
        is Number -> v.toInt()
        else -> v.toString().toDouble().toInt()
    }

    companion object {
        /** Version name = file name without extension ('KJV+.SQLite3' → 'KJV+'). */
        fun nameOf(fileName: String): String = fileName.substringBeforeLast('.')
    }
}
