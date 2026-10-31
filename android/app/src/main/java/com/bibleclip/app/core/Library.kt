package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject

/** Result of [Library.buildOutput] — same shape as the Python dict. */
sealed class Output {
    data class Keyword(val keyword: String) : Output()
    data class Reference(val bookNum: Int, val chapter: Int, val verses: List<Int>,
                         val shortName: String, val text: String, val nParts: Int) : Output()
}

/**
 * The UI-agnostic core: loaded versions + settings + reference → output text.
 * Port of the reading/formatting half of bibleclip/core/library.py.
 *
 * [aliasOverrides] supplies aliases_override.json ({alias: book number or name}).
 */
class Library(
    val tables: Tables,
    val settings: Settings,
    private val aliasOverrides: () -> JSONObject = { JSONObject() },
) {
    val text = TextUtils(tables)
    val engine = Engine(tables, text)
    val dbs = LinkedHashMap<String, BibleDb>()

    /** 유의어 사전 (web/data/bible_synonyms.json); null = no expansion. Set it
     *  directly, or give [synonymsLoader] to parse it on first use (keeps the
     *  325KB JSON off app start). */
    @get:Synchronized @set:Synchronized
    var synonyms: Synonyms? = null
        get() {
            if (field == null) synonymsLoader?.let { load -> synonymsLoader = null; field = load() }
            return field
        }
    var synonymsLoader: (() -> Synonyms?)? = null
    private val searches = HashMap<String, VerseSearch>()

    private var aliasKey: Set<String>? = null
    private var aliases: Map<String, Int> = emptyMap()

    /** Add a version; the first one with a name wins (like the desktop scan). */
    fun add(db: BibleDb): Boolean {
        if (db.name in dbs) return false
        dbs[db.name] = db
        return true
    }

    /**
     * Library.load_settings' validation, after the versions are loaded: empty
     * output/viewer lists fall back to a Korean version, the viewer order holds
     * every version, book_name collapses to long_ko/short_ko, font size 8–400.
     */
    fun validateSettings() {
        val versions = dbs.keys.toList()
        val fallback = listOfNotNull(listOf("KRV", "NRKV", "KNRSV").firstOrNull { it in dbs } ?: versions.firstOrNull())

        settings["output_order"] = JSONArray(settings.strings("output_order").filter { it in dbs }.ifEmpty { fallback })

        var viewer = settings.strings("viewer_versions").filter { it in dbs }
        if (viewer == listOf("KNRSV") && "KRV" in dbs) viewer = listOf("KRV")
        settings["viewer_versions"] = JSONArray(viewer.ifEmpty { fallback })

        val order = settings.strings("viewer_version_order").filter { it in dbs }.toMutableList()
        versions.filterNot { it in order }.forEach { order += it }
        settings["viewer_version_order"] = JSONArray(order)

        settings["book_name"] = if (settings.str("book_name", "short_ko").startsWith("long")) "long_ko" else "short_ko"
        val size = (settings["viewer_font_size"] as? Number)?.toInt()
            ?: settings.str("viewer_font_size", "11").toIntOrNull() ?: 11
        settings["viewer_font_size"] = size.coerceIn(8, 400)
    }

    /** The (lazily indexed) search engine for one loaded version. */
    @Synchronized
    fun searcher(version: String): VerseSearch? =
        dbs[version]?.let { db -> searches.getOrPut(version) { VerseSearch(db, text) } }

    /** Default search version: the primary one, else a Korean one, else the first (routes._search_version). */
    fun searchVersion(): String? =
        primaryVersion()?.takeIf { it in dbs }
            ?: listOf("KRV", "NRKV", "KNRSV").firstOrNull { it in dbs } ?: dbs.keys.firstOrNull()

    /**
     * The bridge's search reply — port of webui/routes/bible.py BibleRoutes.search:
     * {keyword, version, display, mode, matched_tokens, highlight_tokens, expanded, hits}.
     * matched_tokens = the 조사-stripped query (what highlighting looks for);
     * highlight_tokens adds the synonym alternatives that were searched too.
     */
    fun searchReply(keyword: String?, version: String?, limit: Int = 200, mode: String? = "and"): JSONObject {
        val kw = (keyword ?: "").trim().trimStart('#').trim()
        val m = if (mode?.lowercase() == "or") "or" else "and"
        val matched = Korean.tokenize(kw).ifEmpty { if (kw.isNotEmpty()) listOf(kw) else emptyList() }
        val reply = JSONObject().put("keyword", kw).put("mode", m).put("matched_tokens", JSONArray(matched))
        val ver = if (!version.isNullOrEmpty() && version in dbs) version else searchVersion()
        val db = if (kw.isEmpty()) null else ver?.let { dbs[it] }
        if (db == null) {
            return reply.put("version", if (kw.isEmpty()) JSONObject.NULL else ver ?: JSONObject.NULL)
                .put("display", "").put("highlight_tokens", JSONArray(matched))
                .put("expanded", JSONObject()).put("hits", JSONArray())
        }
        val expand = settings.truthy("search_synonyms", true)
        val syn = if (expand) synonyms else null
        val rows = searcher(ver!!)!!.search(kw, m, limit, syn)
        val expanded = syn?.expandAll(matched) ?: LinkedHashMap()
        val hl = matched.toMutableList()
        expanded.values.flatten().forEach { if (it !in hl) hl += it }
        return reply.put("version", ver).put("display", db.displayName)
            .put("highlight_tokens", JSONArray(hl))
            .put("expanded", JSONObject().also { o -> expanded.forEach { (k, v) -> o.put(k, JSONArray(v)) } })
            .put("hits", JSONArray(rows.map { h ->
                JSONObject().put("book", h.book).put("chapter", h.chapter).put("verse", h.verse)
                    .put("short", db.books[h.book]?.first ?: "?").put("text", h.text)
            }))
    }

    fun primaryVersion(): String? =
        settings.strings("viewer_versions").firstOrNull { it in dbs } ?: dbs.keys.firstOrNull()

    /** {normalized book name: book_num} from every loaded version + user overrides. */
    fun bookAliases(): Map<String, Int> {
        val names = dbs.keys.toSet()
        if (aliasKey != names) {
            val amap = LinkedHashMap<String, Int>()
            for (db in dbs.values) {
                for ((bn, short, long) in db.bookList) {
                    for (nm in listOf(short, long)) {
                        val k = Engine.normBook(nm)
                        if (k.isNotEmpty() && k != "?" && k !in amap) amap[k] = bn
                    }
                }
            }
            mergeAliasOverrides(amap)
            aliases = amap
            aliasKey = names
        }
        return aliases
    }

    /** Drop the alias cache (after aliases_override.json changed). */
    fun invalidateAliases() {
        aliasKey = null
    }

    private fun mergeAliasOverrides(amap: MutableMap<String, Int>) {
        val overrides = try { aliasOverrides() } catch (e: Exception) { return }
        for (raw in overrides.keys()) {
            if (raw.startsWith("_")) continue
            val key = Engine.normBook(raw)
            if (key.isEmpty()) continue
            val bn: Int? = when (val v = overrides.get(raw)) {
                is Boolean -> null
                is Int -> v
                is Long -> v.toInt()
                is String -> v.trim().let { s ->
                    if (s.isNotEmpty() && s.all { it.isDigit() }) s.toInt()
                    else Engine.normBook(s).let { amap[it] ?: tables.englishBookMap[it] }
                }
                else -> null
            }
            if (bn != null) amap[key] = bn
        }
    }

    fun parseReference(text: String): List<Ref> = engine.parseReference(text, bookAliases())

    /** Clipboard/selection text → Keyword ('#…'), Reference, or null. */
    fun buildOutput(input: String?): Output? {
        val s = (input ?: "").trim()
        if (s.isEmpty()) return null
        if (s.startsWith("#")) {
            val keyword = s.substring(1).trim()
            return if (keyword.isNotEmpty()) Output.Keyword(keyword) else null
        }
        val ref = parseReference(s).firstOrNull() ?: return null
        val (out, nParts) = formatReference(ref.book.num, ref.chapter, ref.verses)
        if (out.isEmpty()) return null
        val name = displayBookName(ref.book.num) ?: ref.book.short
        return Output.Reference(ref.book.num, ref.chapter, ref.verses, name, out, nParts)
    }

    /** Book label from the primary output version, honoring 정식/약칭. */
    fun displayBookName(bookNum: Int, order: List<String>? = null): String? {
        val o = order ?: settings.strings("output_order")
        val primary = o.firstOrNull() ?: primaryVersion()
        val (short, long) = dbs[primary]?.books?.get(bookNum) ?: return null
        val name = if (settings.str("book_name", "short").startsWith("long")) long else short
        return name.takeIf { it.isNotEmpty() && it != "?" }
    }

    /**
     * One reference across [order] (default: output_order). Empty [verses] = whole
     * chapter. Returns (text, n_parts); ("", 0) when nothing matched.
     */
    fun formatReference(bookNum: Int, chapter: Int, verses: List<Int>,
                        order: List<String>? = null): Pair<String, Int> {
        val o = order ?: settings.strings("output_order")
        if (o.isEmpty()) return "" to 0
        val fmt = Formatter(settings)
        val cols = mutableListOf<Pair<BibleDb, List<Pair<Int, String>>>>()
        for (ver in o) {
            val db = dbs[ver] ?: continue
            if (bookNum !in db.books) continue
            val data = (if (verses.isNotEmpty()) verses.map { it to db.getVerseText(bookNum, chapter, it) }
                        else db.getVerses(bookNum, chapter)).filter { it.second.isNotEmpty() }
            if (data.isNotEmpty()) cols += db to data
        }
        if (cols.isEmpty()) return "" to 0

        val tmpl = settings.str("custom_format_template", "")
        if (settings.truthy("custom_format_enabled") && tmpl.isNotBlank() &&
            ("{content2}" in tmpl || "{version2}" in tmpl) && cols.size >= 2) {
            return fmt.formatParallel(bookNum, chapter, cols[0], cols[1]) to 2
        }
        val parts = cols.map { (db, data) ->
            fmt.formatVersionOutput(db, bookNum, chapter, data.map { it.first }, data)
        }.filter { it.isNotEmpty() }
        if (parts.isEmpty()) return "" to 0
        return parts.joinToString("\n\n") to parts.size
    }
}
