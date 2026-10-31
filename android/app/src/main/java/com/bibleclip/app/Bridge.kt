package com.bibleclip.app

import android.content.ClipData
import android.content.ClipboardManager
import android.net.Uri
import android.provider.OpenableColumns
import android.util.Log
import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.bibleclip.app.core.ImportSource
import com.bibleclip.app.core.Library
import com.bibleclip.app.core.Output
import org.json.JSONArray
import org.json.JSONObject
import java.util.concurrent.CountDownLatch
import java.util.concurrent.Executors

/** Opens the system file picker; [done] gets the picked files (empty = cancelled). */
fun interface FilePicker {
    fun pick(done: (List<Uri>) -> Unit)
}

/**
 * The Kotlin side of assets/android/bridge.js — same method names, arguments and
 * return shapes as the desktop's bibleclip/webui routes, so web/ needs no fork.
 *
 * 0단계(시험 제작): reading, reference, copy and settings methods. Anything else
 * answers null (logged once) and the page degrades the way it does headless.
 */
class Bridge(private val app: BibleClipApp, private val web: WebView, private val picker: FilePicker) {

    private val worker = Executors.newSingleThreadExecutor()
    private val unknown = mutableSetOf<String>()
    private val lib: Library get() = app.library

    @JavascriptInterface
    fun call(method: String, argsJson: String, id: Int) {
        worker.execute {
            val reply = try {
                "true, " + literal(dispatch(method, JSONArray(argsJson)))
            } catch (e: Exception) {
                Log.w(BibleClipApp.TAG, "bridge $method failed", e)
                "false, " + JSONObject.quote(e.toString())
            }
            web.post { web.evaluateJavascript("window.__bibleclipReply($id, $reply)", null) }
        }
    }

    private fun dispatch(m: String, a: JSONArray): Any? = when (m) {
        "get_initial" -> initial()
        "get_books" -> books(a.optString(0))
        "get_chapters" -> JSONArray(lib.dbs[a.optString(0)]?.getChapters(a.optInt(1)).orEmpty())
        "get_chapter" -> chapter(a.optString(0), a.optInt(1), a.optInt(2))
        "resolve_reference" -> lib.parseReference(a.optString(0)).firstOrNull()?.let { r ->
            JSONObject().put("book_num", r.book.num).put("short", r.book.short).put("long", r.book.long)
                .put("chapter", r.chapter).put("verses", JSONArray(r.verses))
        }
        "copy_reference" -> copyReference(a)
        "copy_text" -> a.optString(0).let { t ->
            if (t.isEmpty()) ok(false) else { clip(t); ok(true) }
        }
        "get_locale" -> locale(a.optString(0))
        "get_settings" -> JSONObject()
            .put("format", JSONObject().also { o -> FORMAT_KEYS.keys.forEach { o.put(it, lib.settings[it]) } })
            .put("output_order", JSONArray(lib.settings.strings("output_order")))
            .put("versions", versions())
        "get_preview" -> (lib.buildOutput("요 1:1-3") as? Output.Reference)?.text ?: ""
        "get_app_settings" -> JSONObject().also { o -> APP_KEYS.keys.forEach { o.put(it, lib.settings[it]) } }
        "set_setting" -> setChecked(a.optString(0), a.opt(1), FORMAT_KEYS)
        "set_app_setting" -> setChecked(a.optString(0), a.opt(1), APP_KEYS)
        "save_cards_layout" -> save("web_cards_layout", a.opt(0))
        "set_dark_mode" -> save("dark_mode", a.optBoolean(0))
        "set_font_size" -> (a.optInt(0, 11)).coerceIn(8, 400).also { save("viewer_font_size", it) }
        "set_viewer_versions" -> setViewer(names(a.optJSONArray(0)), keepOrder = false)
        "set_viewer_order" -> setViewer(names(a.optJSONArray(0)), keepOrder = true)
        "set_output_order" -> names(a.optJSONArray(0)).filter { it in lib.dbs }.distinct().let {
            save("output_order", JSONArray(it)); JSONArray(it)
        }
        "search" -> lib.searchReply(a.optString(0), if (a.isNull(1)) null else a.optString(1),
            if (a.isNull(2)) 200 else a.optInt(2, 200), if (a.isNull(3)) "and" else a.optString(3))
        "add_bible_files" -> addBibleFiles()
        "refresh_databases" -> JSONObject().put("added", JSONArray(app.scanBibles())).put("versions", versions())
        "note_position" -> {
            lib.settings["last_book_num"] = a.optInt(0)
            lib.settings["last_chapter"] = a.optInt(1)
            null
        }
        else -> {
            if (unknown.add(m)) Log.i(BibleClipApp.TAG, "bridge: not on Android yet: $m")
            null
        }
    }

    private fun initial(): JSONObject {
        val s = lib.settings
        val primary = lib.primaryVersion()
        val books = primary?.let { lib.dbs[it] }?.bookList.orEmpty()
        var lastBook = (s["last_book_num"] as? Number)?.toInt()
        var lastChapter = (s["last_chapter"] as? Number)?.toInt()
        if (books.none { it.first == lastBook }) {
            lastBook = books.firstOrNull()?.first
            lastChapter = null
        }
        if (lastBook != null && lastChapter == null) {
            lastChapter = primary?.let { lib.dbs[it]?.getChapters(lastBook)?.firstOrNull() } ?: 1
        }
        return JSONObject()
            .put("versions", versions())
            .put("primary", primary)
            .put("viewer", JSONArray(s.strings("viewer_versions")))
            .put("books", primary?.let { books(it) } ?: JSONArray())
            .put("last", JSONObject().put("version", primary).put("book", lastBook).put("chapter", lastChapter))
            .put("dark_mode", s.truthy("dark_mode"))
            .put("font_size", (s["viewer_font_size"] as? Number)?.toInt() ?: 11)
            .put("auto_update_check", false)
            .put("lex_lang", if (s.str("lex_lang", "ko") == "en") "en" else "ko")
            .put("ui_lang", s.str("ui_lang", "ko").ifEmpty { "ko" })
            .put("reading_font", s.str("reading_font", ""))
            .put("subtitle_preset", s.str("subtitle_preset", "green"))
            .put("lex", JSONObject().put("ko", false).put("en", false))
            .put("interlin_sources", JSONArray())
            .put("is_premium", true)
            .put("search_click_navigates", s.truthy("search_click_navigates"))
            .put("auto_copy_top_result", s.truthy("auto_copy_top_result"))
            .put("search_synonyms", s.truthy("search_synonyms", true))
            .put("view_mode", if (s.str("view_mode", "") == "split") "split" else "interleave")
            .put("web_cards_layout", s["web_cards_layout"])
            // The first-run tour walks the desktop (monitoring, F-keys) — not on a phone yet.
            .put("tour_done", true)
            .put("cart", JSONArray())
            .put("version", app.packageManager.getPackageInfo(app.packageName, 0).versionName)
    }

    private fun versions() = JSONArray(lib.dbs.map { (name, db) ->
        JSONObject().put("name", name).put("display", db.displayName)
            .put("lang", (db.info["language"] ?: "").trim().lowercase())
    })

    private fun books(version: String) = JSONArray(lib.dbs[version]?.bookList.orEmpty().map { (n, s, l) ->
        JSONObject().put("num", n).put("short", s).put("long", l)
    })

    private fun chapter(version: String, book: Int, chapter: Int): JSONObject {
        val db = lib.dbs[version]
        val (short, long) = db?.books?.get(book) ?: ("?" to "?")
        return JSONObject()
            .put("ref", JSONObject().put("version", version).put("book", book)
                .put("short", short).put("long", long).put("chapter", chapter))
            .put("verses", JSONArray(db?.getVerses(book, chapter).orEmpty().map { (n, t) ->
                JSONObject().put("n", n).put("text", t)
            }))
    }

    private fun copyReference(a: JSONArray): JSONObject {
        val book = a.optInt(0)
        val chapter = a.optInt(1)
        val verses = a.optJSONArray(2)?.let { v -> List(v.length()) { v.optInt(it) } }.orEmpty()
        val order = a.optJSONArray(3)?.let { names(it).filter { n -> n in lib.dbs } }?.ifEmpty { null }
        val (text, nParts) = lib.formatReference(book, chapter, verses, order)
        if (text.isEmpty()) return ok(false)
        clip(text)
        return ok(true).put("text", text).put("n_parts", nParts)
            .put("short_name", lib.displayBookName(book, order) ?: lib.engine.canon(book)?.short)
    }

    /** [＋ 성경 파일 추가…]: system picker → checked copy into bible_versions → loaded.
     *  Same reply as the desktop's add_bible_files, so web/ handles it unchanged. */
    private fun addBibleFiles(): JSONObject {
        val picked = CountDownLatch(1)
        var uris: List<Uri> = emptyList()
        web.post { picker.pick { uris = it; picked.countDown() } }
        picked.await()   // this bridge worker waits while the picker is up
        if (uris.isEmpty()) return ok(false).put("error", "cancelled")
        val sources = uris.map { u ->
            ImportSource(displayName(u)) {
                app.contentResolver.openInputStream(u) ?: throw java.io.IOException("cannot open $u")
            }
        }
        val (added, errors) = app.importBibles(sources)
        return ok(true)
            .put("added", JSONArray(added.map { n ->
                JSONObject().put("name", n).put("display", lib.dbs[n]?.displayName ?: n)
            }))
            .put("errors", JSONArray(errors.map { JSONObject().put("file", it.file).put("code", it.code) }))
            .put("versions", versions())
    }

    private fun displayName(u: Uri): String =
        app.contentResolver.query(u, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { c ->
            if (c.moveToFirst()) c.getString(0) else null
        } ?: u.lastPathSegment?.substringAfterLast('/') ?: "file"

    private fun locale(lang: String): JSONObject {
        if (!Regex("[a-z]{2,3}(?:-[A-Za-z]{2,4})?").matches(lang)) return JSONObject()
        return try {
            JSONObject(app.assets.open("web/locales/$lang.json").bufferedReader().use { it.readText() })
        } catch (e: Exception) {
            JSONObject()
        }
    }

    private fun setViewer(names: List<String>, keepOrder: Boolean): JSONArray {
        val s = lib.settings
        val current = JSONArray(s.strings("viewer_versions"))
        if (keepOrder) {
            val valid = names.filter { it in lib.dbs }
            if (valid.isEmpty()) return current
            s["viewer_versions"] = JSONArray(valid)
            s["viewer_version_order"] = JSONArray(valid + s.strings("viewer_version_order")
                .filter { it in lib.dbs && it !in valid })
            app.saveSettings()
            return JSONArray(valid)
        }
        val order = s.strings("viewer_version_order").ifEmpty { lib.dbs.keys.toList() }
        val ordered = order.filter { it in names && it in lib.dbs }.toMutableList()
        names.filter { it in lib.dbs && it !in ordered }.forEach { ordered += it }
        if (ordered.isEmpty()) return current
        save("viewer_versions", JSONArray(ordered))
        return JSONArray(ordered)
    }

    /** set_setting / set_app_setting: whitelisted keys; a set of allowed values or null = boolean. */
    private fun setChecked(key: String, value: Any?, spec: Map<String, Set<String>?>): JSONObject {
        if (key !in spec) return ok(false).put("error", "unknown key: $key")
        val allowed = spec[key]
        val v: Any? = when {
            key == "custom_format_template" -> (value?.takeUnless { it == JSONObject.NULL }?.toString() ?: "").take(500)
            key in FREE_KEYS -> value
            allowed == null -> com.bibleclip.app.core.Settings.truthy(value)
            value?.toString() in allowed -> value.toString()
            else -> return ok(false).put("error", "invalid value for $key: $value")
        }
        save(key, v)
        return ok(true).put("value", v)
    }

    private fun save(key: String, value: Any?): JSONObject {
        lib.settings[key] = value
        app.saveSettings()
        return ok(true)
    }

    private fun clip(text: String) = app.getSystemService(ClipboardManager::class.java)
        .setPrimaryClip(ClipData.newPlainText("BibleClip", text))

    private fun ok(v: Boolean) = JSONObject().put("ok", v)

    private fun names(a: JSONArray?): List<String> = a?.let { List(it.length()) { i -> it.optString(i) } }.orEmpty()

    /** A JSON value as a JS expression. */
    private fun literal(v: Any?): String = when (v) {
        null, JSONObject.NULL -> "null"
        is String -> JSONObject.quote(v)
        is JSONObject, is JSONArray, is Number, is Boolean -> v.toString()
        else -> JSONObject.wrap(v)?.toString() ?: "null"
    }

    companion object {
        /** The desktop's _FORMAT_KEYS (system.py); null = boolean. */
        private val FORMAT_KEYS: Map<String, Set<String>?> = mapOf(
            "book_name" to setOf("long_ko", "short_ko"),
            "chapter_verse_format" to setOf("colon", "korean"),
            "bracket_style" to setOf("none", "[]", "()"),
            "ref_position" to setOf("before", "after"),
            "range_symbol" to setOf("-", "~"),
            "ref_body_separator" to setOf(" - ", ": ", " "),
            "output_mode" to setOf("inline", "newline"),
            "newline_show_cv" to null,
            "show_version_header" to null,
            "hide_reference" to null,
            "custom_format_enabled" to null,
            "custom_format_template" to emptySet(),
        )

        /** The desktop's _APP_KEYS that mean something on Android. */
        private val APP_KEYS: Map<String, Set<String>?> = mapOf(
            "search_click_navigates" to null,
            "auto_copy_top_result" to null,
            "search_synonyms" to null,
            "tour_done" to null,
            "lex_lang" to setOf("ko", "en"),
            "ui_lang" to setOf("ko", "en"),
            "view_mode" to setOf("interleave", "split"),
            "reading_font" to emptySet(),
            "web_cards_layout" to emptySet(),
        )

        /** Stored as given (the desktop's 'str' / 'any' specs). */
        private val FREE_KEYS = setOf("custom_format_template", "reading_font", "web_cards_layout")
    }
}
