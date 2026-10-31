package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject
import org.json.JSONTokener
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.File

/**
 * 노트 · 형광펜 · 장바구니 against tests/golden/userdata.json: the Python stores
 * ran the same op script; every return value, the file left on disk, and how a
 * broken file loads must match.
 */
class UserDataTest {
    @get:Rule val tmp = TemporaryFolder()

    private val root = File(System.getProperty("bibleclip.repoRoot") ?: "..")
    private val golden = JSONObject(File(root, "tests/golden/userdata.json").readText())
    private val now = golden.getString("now")

    private fun same(want: Any?, got: Any?): Boolean = when {
        want == null || want == JSONObject.NULL -> got == null || got == JSONObject.NULL
        want is JSONObject -> got is JSONObject && want.similar(got)
        want is JSONArray -> got is JSONArray && want.similar(got)
        want is Number && got is Number -> want.toDouble() == got.toDouble()
        else -> want == got
    }

    private fun i(op: JSONArray, k: Int) = pyInt(op.opt(k))!!

    private fun replay(section: String, file: File, run: (JSONArray) -> Any?) {
        val g = golden.getJSONObject(section)
        val ops = g.getJSONArray("ops")
        val want = g.getJSONArray("results")
        val failures = mutableListOf<String>()
        for (k in 0 until ops.length()) {
            val got = run(ops.getJSONArray(k))
            if (!same(want.opt(k), got)) failures += "$section #$k ${ops.get(k)}:\n  want ${want.opt(k)}\n  got  $got"
        }
        val onDisk = JSONTokener(file.readText()).nextValue()
        if (!same(g.get("final"), onDisk)) failures += "$section file:\n  want ${g.get("final")}\n  got  $onDisk"
        assertEquals(failures.joinToString("\n"), 0, failures.size)
    }

    @Test
    fun notes() {
        val f = File(tmp.root, "user_notes.json")
        val s = Notes(f) { now }
        replay("notes", f) { op ->
            when (op.getString(0)) {
                "set" -> s.set(i(op, 1), i(op, 2), i(op, 3), op.getString(4))
                "get" -> s.get(i(op, 1), i(op, 2), i(op, 3))
                "delete" -> s.delete(i(op, 1), i(op, 2), i(op, 3))
                "for_chapter" -> s.forChapter(i(op, 1), i(op, 2))
                "all" -> s.all()
                else -> error("op ${op.getString(0)}")
            }
        }
    }

    @Test
    fun highlights() {
        val f = File(tmp.root, "user_highlights.json")
        val s = Highlights(f) { now }
        replay("highlights", f) { op ->
            when (op.getString(0)) {
                "set_verse" -> s.setVerse(i(op, 1), i(op, 2), i(op, 3), op.getString(4), op.getJSONArray(5))
                "get" -> s.get(i(op, 1), i(op, 2), i(op, 3), op.getString(4))
                "clear_verse" -> s.clearVerse(i(op, 1), i(op, 2), i(op, 3), op.getString(4))
                "for_chapter" -> s.forChapter(i(op, 1), i(op, 2), op.getString(3))
                "all" -> s.all()
                else -> error("op ${op.getString(0)}")
            }
        }
    }

    @Test
    fun cart() {
        val f = File(tmp.root, "sermon_cart.json")
        val s = Cart(f)
        replay("cart", f) { op ->
            when (op.getString(0)) {
                "replace" -> s.replace(op.getJSONArray(1))
                "all" -> s.all()
                else -> error("op ${op.getString(0)}")
            }
        }
    }

    @Test
    fun brokenFilesLoadSoft() {
        val loads = golden.getJSONArray("loads")
        for (k in 0 until loads.length()) {
            val c = loads.getJSONObject(k)
            val f = File(tmp.newFolder(), "data.json").apply { writeText(c.getString("file")) }
            val got: Any = when (c.getString("store")) {
                "notes" -> Notes(f) { now }.data
                "highlights" -> Highlights(f) { now }.data
                else -> Cart(f).items
            }
            assertTrue("${c.getString("store")} ${c.getString("file")}: got $got", same(c.get("loaded"), got))
        }
    }
}
