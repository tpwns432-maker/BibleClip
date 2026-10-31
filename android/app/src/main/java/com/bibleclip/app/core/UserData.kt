package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.time.LocalDateTime
import java.time.format.DateTimeFormatter
import java.time.temporal.ChronoUnit

/*
 * 노트 · 형광펜 · 장바구니 — ports of bibleclip/notes.py, highlights.py and cart.py.
 * Same files, same JSON (userdata/user_notes.json · user_highlights.json ·
 * sermon_cart.json), so a desktop file means the same thing here. Write-through;
 * every read/write is fail-soft (a missing or broken file = empty store).
 * Behaviour pinned by tests/golden/userdata.json.
 */

/** Python's int(x) for the JSON values the stores see: ints, floats (truncate), bools, numeric strings. */
internal fun pyInt(v: Any?): Int? = when (v) {
    null, JSONObject.NULL -> null
    is Boolean -> if (v) 1 else 0
    is Int -> v
    is Long -> v.toInt()
    is Number -> v.toDouble().toInt()
    is String -> v.trim().toIntOrNull()
    else -> null
}

/** Local time as "YYYY-MM-DDTHH:MM:SS" (datetime.now().isoformat(timespec='seconds')). */
fun isoNow(): String = LocalDateTime.now().truncatedTo(ChronoUnit.SECONDS)
    .format(DateTimeFormatter.ISO_LOCAL_DATE_TIME)

/** A JSON file that reads fail-soft and writes atomically. */
internal class JsonFile(private val file: File) {
    fun read(): Any? = try {
        if (file.exists()) org.json.JSONTokener(file.readText()).nextValue() else null
    } catch (e: Exception) {
        null
    }

    fun write(value: Any): Boolean = try {
        file.parentFile?.mkdirs()
        val tmp = File(file.path + ".part")
        tmp.writeText(if (value is JSONObject) value.toString(2) else (value as JSONArray).toString(2))
        tmp.renameTo(file) || run { file.delete(); tmp.renameTo(file) }
    } catch (e: Exception) {
        false
    }
}

/** Verse-anchored meditation notes: {"book:chapter:verse": {text, ts}}. */
class Notes(file: File, private val now: () -> String = ::isoNow) {
    private val store = JsonFile(file)
    val data: JSONObject = (store.read() as? JSONObject) ?: JSONObject()

    private fun key(b: Int, c: Int, v: Int) = "$b:$c:$v"

    @Synchronized fun get(b: Int, c: Int, v: Int): JSONObject? = data.optJSONObject(key(b, c, v))

    /** Create/update; empty text deletes. Returns the stored note or null. */
    @Synchronized fun set(b: Int, c: Int, v: Int, text: String?): JSONObject? {
        val k = key(b, c, v)
        val t = (text ?: "").trim()
        if (t.isEmpty()) {
            data.remove(k)
            store.write(data)
            return null
        }
        val entry = JSONObject().put("text", t).put("ts", now())
        data.put(k, entry)
        store.write(data)
        return entry
    }

    @Synchronized fun delete(b: Int, c: Int, v: Int): Boolean {
        data.remove(key(b, c, v))
        store.write(data)
        return true
    }

    /** Every note in bible order: [{book, chapter, verse, text, ts}]. */
    @Synchronized fun all(): JSONArray {
        val out = mutableListOf<Pair<Triple<Int, Int, Int>, JSONObject>>()
        for (k in data.keys()) {
            val p = k.split(":")
            if (p.size != 3) continue
            val (b, c, v) = p.map { it.toIntOrNull() ?: -1 }.takeIf { l -> l.none { it < 0 } } ?: continue
            val n = data.optJSONObject(k) ?: JSONObject()
            out += Triple(b, c, v) to JSONObject().put("book", b).put("chapter", c).put("verse", v)
                .put("text", n.optString("text", "")).put("ts", n.optString("ts", ""))
        }
        return JSONArray(out.sortedWith(compareBy({ it.first.first }, { it.first.second }, { it.first.third }))
            .map { it.second })
    }

    /** {verse: text} for one chapter — drives the 📄 badges. */
    @Synchronized fun forChapter(b: Int, c: Int): JSONObject {
        val prefix = "$b:$c:"
        val out = JSONObject()
        for (k in data.keys()) {
            if (!k.startsWith(prefix)) continue
            val v = k.split(":").getOrNull(2)?.toIntOrNull() ?: continue
            out.put(v.toString(), data.optJSONObject(k)?.optString("text", "") ?: "")
        }
        return out
    }
}

/** 형광펜: {"book:chapter:verse:version": [{s, e, t, c, ts}]}, ranges sorted and non-overlapping. */
class Highlights(file: File, private val now: () -> String = ::isoNow) {
    private val store = JsonFile(file)
    val data: JSONObject = JSONObject().also { d ->
        (store.read() as? JSONObject)?.let { raw ->
            for (k in raw.keys()) (raw.opt(k) as? JSONArray)?.let { d.put(k, it) }
        }
    }

    private fun key(b: Int, c: Int, v: Int, ver: String) = "$b:$c:$v:$ver"

    /** Sanitize: drop junk, sort, trim overlaps (earlier range wins), cap at [MAX_RANGES]. */
    fun norm(ranges: JSONArray?): JSONArray {
        class R(var s: Int, val e: Int, var t: String, val c: String, val ts: String)
        val clean = mutableListOf<R>()
        for (i in 0 until (ranges?.length() ?: 0)) {
            val r = ranges!!.opt(i) as? JSONObject ?: continue
            val s = pyInt(r.opt("s")) ?: continue
            val e = pyInt(r.opt("e")) ?: continue
            if (s < 0 || e <= s) continue
            val c = (r.opt("c") as? String)?.takeIf { it in COLORS } ?: COLORS[0]
            val t = (r.opt("t") as? String)?.let { codePointPrefix(it, MAX_SNIPPET) } ?: ""
            val ts = (r.opt("ts") as? String)?.takeIf { it.isNotEmpty() } ?: now()
            clean += R(s, e, t, c, ts)
        }
        val out = mutableListOf<R>()
        for (r in clean.sortedWith(compareBy({ it.s }, { it.e }))) {
            if (out.isNotEmpty() && r.s < out.last().e) {
                r.s = out.last().e
                if (r.e <= r.s) continue
                r.t = ""
            }
            out += r
            if (out.size >= MAX_RANGES) break
        }
        return JSONArray(out.map {
            JSONObject().put("s", it.s).put("e", it.e).put("t", it.t).put("c", it.c).put("ts", it.ts)
        })
    }

    @Synchronized fun get(b: Int, c: Int, v: Int, ver: String): JSONArray =
        data.optJSONArray(key(b, c, v, ver)) ?: JSONArray()

    /** Replace one verse+version's ranges; empty deletes. Returns the stored list. */
    @Synchronized fun setVerse(b: Int, c: Int, v: Int, ver: String, ranges: JSONArray?): JSONArray {
        val k = key(b, c, v, ver)
        val stored = norm(ranges)
        if (stored.length() > 0) data.put(k, stored) else data.remove(k)
        store.write(data)
        return stored
    }

    @Synchronized fun clearVerse(b: Int, c: Int, v: Int, ver: String): Boolean {
        data.remove(key(b, c, v, ver))
        store.write(data)
        return true
    }

    /** {verse: [ranges]} for one chapter in one version. */
    @Synchronized fun forChapter(b: Int, c: Int, ver: String): JSONObject {
        val prefix = "$b:$c:"
        val out = JSONObject()
        for (k in data.keys()) {
            if (!k.startsWith(prefix)) continue
            val p = k.split(":", limit = 4)   // the version may itself contain ':'
            if (p.size != 4 || p[3] != ver) continue
            val v = p[2].toIntOrNull() ?: continue
            out.put(v.toString(), data.get(k))
        }
        return out
    }

    /** Every highlight in bible order: [{book, chapter, verse, version, s, e, t, c, ts}]. */
    @Synchronized fun all(): JSONArray {
        class H(val b: Int, val c: Int, val v: Int, val ver: String, val s: Int, val o: JSONObject)
        val out = mutableListOf<H>()
        for (k in data.keys()) {
            val p = k.split(":", limit = 4)
            if (p.size != 4) continue
            val b = p[0].toIntOrNull() ?: continue
            val c = p[1].toIntOrNull() ?: continue
            val v = p[2].toIntOrNull() ?: continue
            val ranges = data.optJSONArray(k) ?: continue
            for (i in 0 until ranges.length()) {
                val r = ranges.optJSONObject(i) ?: continue
                out += H(b, c, v, p[3], r.optInt("s"), JSONObject()
                    .put("book", b).put("chapter", c).put("verse", v).put("version", p[3])
                    .put("s", r.opt("s")).put("e", r.opt("e")).put("t", r.optString("t", ""))
                    .put("c", r.optString("c", COLORS[0])).put("ts", r.optString("ts", "")))
            }
        }
        return JSONArray(out.sortedWith(compareBy({ it.b }, { it.c }, { it.v }, { it.ver }, { it.s })).map { it.o })
    }

    companion object {
        val COLORS = listOf("y", "g", "b", "p")
        const val MAX_RANGES = 64
        const val MAX_SNIPPET = 400

        private fun codePointPrefix(s: String, n: Int): String =
            if (s.codePointCount(0, s.length) <= n) s else s.substring(0, s.offsetByCodePoints(0, n))
    }
}

/** 설교 장바구니: [{book_num, chapter, verses, short_name}], replaced whole on every change. */
class Cart(file: File) {
    private val store = JsonFile(file)
    var items: JSONArray = (store.read() as? JSONArray)?.let { sanitize(it) } ?: JSONArray()
        private set

    @Synchronized fun all(): JSONArray = JSONArray(items.toString())

    @Synchronized fun replace(raw: JSONArray?): JSONArray {
        items = sanitize(raw)
        store.write(items)
        return all()
    }

    companion object {
        /** Drop malformed items; same shape the front-end stores and reads. */
        fun sanitize(raw: JSONArray?): JSONArray {
            val out = JSONArray()
            for (i in 0 until (raw?.length() ?: 0)) {
                val it = raw!!.opt(i) as? JSONObject ?: continue
                // Python: it.get("book_num", it.get("book")) — a present-but-null book_num wins.
                val book = pyInt(if (it.has("book_num")) it.opt("book_num") else it.opt("book")) ?: continue
                val chapter = pyInt(it.opt("chapter")) ?: continue
                val verses = JSONArray()
                (it.opt("verses") as? JSONArray)?.let { vs ->
                    for (j in 0 until vs.length()) pyInt(vs.opt(j))?.let { v -> verses.put(v) }
                }
                val short = it.opt("short_name").let { s ->
                    if (s == null || s == JSONObject.NULL || s == "" || s == false || s == 0) "" else s.toString()
                }
                out.put(JSONObject().put("book_num", book).put("chapter", chapter)
                    .put("verses", verses).put("short_name", short))
            }
            return out
        }
    }
}
