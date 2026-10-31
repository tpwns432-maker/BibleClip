package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.assertEquals
import org.junit.Test
import java.io.File
import java.sql.DriverManager

/** JVM stand-in for the Android SQLite driver: same .SQLite3 file, same SQL. */
class JdbcBibleDb(file: File, text: TextUtils) : BibleDb(nameOf(file.name), text) {
    private val conn = DriverManager.getConnection("jdbc:sqlite:${file.absolutePath}")

    override fun query(sql: String, vararg args: Any): List<List<Any?>> =
        conn.prepareStatement(sql).use { st ->
            args.forEachIndexed { i, a -> st.setObject(i + 1, a) }
            st.executeQuery().use { rs ->
                val n = rs.metaData.columnCount
                generateSequence { if (rs.next()) List(n) { rs.getObject(it + 1) } else null }.toList()
            }
        }

    override fun close() = conn.close()
}

/**
 * The Kotlin port against the tests/golden JSON files written by the Python engine
 * (tests/make_golden.py). A failure here means the two engines disagree.
 */
class GoldenTest {
    private val root = File(System.getProperty("bibleclip.repoRoot") ?: "..")
    private fun golden(name: String) = JSONObject(File(root, "tests/golden/$name").readText())

    private val tables = Tables(File(root, "android/app/src/main/assets/${Tables.ASSET}").readText())

    private fun library(overrides: JSONObject = JSONObject(), order: JSONArray = JSONArray()): Library {
        val saved = JSONObject(overrides.toString()).put("output_order", order)
        val lib = Library(tables, Settings.of(tables.defaultSettings, saved))
        for (v in listOf("KRV", "KJV+")) lib.add(JdbcBibleDb(File(root, "bible_versions/$v.SQLite3"), lib.text))
        return lib
    }

    private fun refsJson(refs: List<Ref>): String = JSONArray(refs.map { r ->
        JSONArray(listOf(r.book.num, r.book.short, r.book.long, r.chapter, JSONArray(r.verses)))
    }).toString()

    @Test
    fun aliasMapMatches() {
        val want = golden("engine.json").getJSONObject("aliases")
        val got = library().bookAliases()
        assertEquals(want.keys().asSequence().toSortedSet(), got.keys.toSortedSet())
        for (k in want.keys()) assertEquals("alias $k", want.getInt(k), got[k])
    }

    @Test
    fun referencesMatch() {
        val g = golden("engine.json")
        val lib = library()
        val failures = mutableListOf<String>()
        for ((key, aliases) in listOf("with_aliases" to lib.bookAliases(), "without_aliases" to null)) {
            val cases = g.getJSONArray(key)
            for (i in 0 until cases.length()) {
                val c = cases.getJSONObject(i)
                val got = refsJson(lib.engine.parseReference(c.getString("in"), aliases))
                val want = c.getJSONArray("out").toString()
                if (got != want) failures += "$key '${c.getString("in")}': want $want got $got"
            }
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    @Test
    fun textHelpersMatch() {
        val g = golden("text.json")
        val text = TextUtils(tables)
        val clean = g.getJSONArray("clean_text")
        for (i in 0 until clean.length()) {
            val c = clean.getJSONObject(i)
            assertEquals(c.getString("in"), c.getString("out"), text.cleanText(c.getString("in")))
        }
        val qwerty = g.getJSONArray("qwerty")
        for (i in 0 until qwerty.length()) {
            val c = qwerty.getJSONObject(i)
            val want = if (c.isNull("out")) null else c.getString("out")
            assertEquals(c.getString("in"), want, text.convertQwertyToHangul(c.getString("in")))
        }
    }

    @Test
    fun outputsMatch() {
        val cases = golden("format.json").getJSONArray("cases")
        val failures = mutableListOf<String>()
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val lib = library(c.getJSONObject("settings"), c.getJSONArray("order"))
            val got = outputJson(lib.buildOutput(c.getString("in")))
            val want = if (c.isNull("out")) null else c.getJSONObject("out")
            val same = if (want == null) got == null else got != null && want.similar(got)
            if (!same) failures += "${c.getString("label")}:\n  want $want\n  got  $got"
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    @Test
    fun tokenizerMatches() {
        val cases = golden("search.json").getJSONArray("tokenize")
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            assertEquals(c.getString("in"), c.getJSONArray("out").toString(),
                JSONArray(Korean.tokenize(c.getString("in"))).toString())
        }
    }

    @Test
    fun searchMatches() {
        val syn = Synonyms(File(root, "web/data/bible_synonyms.json").readText())
        val cases = golden("search.json").getJSONArray("cases")
        val failures = mutableListOf<String>()
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val inp = c.getJSONObject("in")
            val lib = library(JSONObject().put("search_synonyms", inp.getBoolean("synonyms"))
                .put("viewer_versions", JSONArray(listOf("KRV"))))
            lib.synonyms = syn
            val r = lib.searchReply(inp.getString("q"), if (inp.isNull("version")) null else inp.getString("version"),
                200, inp.getString("mode"))
            val hits = r.getJSONArray("hits")
            val got = JSONObject(r.toString()).apply {
                remove("hits")
                put("hit_count", hits.length())
                put("hit_refs", JSONArray((0 until minOf(60, hits.length())).map { j ->
                    hits.getJSONObject(j).let { h -> JSONArray(listOf(h.getInt("book"), h.getInt("chapter"), h.getInt("verse"))) }
                }))
                put("hit_heads", JSONArray((0 until minOf(3, hits.length())).map { hits.getJSONObject(it) }))
            }
            val want = c.getJSONObject("out")
            if (!want.similar(got)) failures += "$inp:\n  want $want\n  got  $got"
        }
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    /** The Python build_output dict, as JSON. */
    private fun outputJson(o: Output?): JSONObject? = when (o) {
        null -> null
        is Output.Keyword -> JSONObject().put("kind", "keyword").put("keyword", o.keyword)
        is Output.Reference -> JSONObject()
            .put("kind", "reference").put("book_num", o.bookNum).put("chapter", o.chapter)
            .put("verses", JSONArray(o.verses)).put("short_name", o.shortName)
            .put("text", o.text).put("n_parts", o.nParts)
    }
}
