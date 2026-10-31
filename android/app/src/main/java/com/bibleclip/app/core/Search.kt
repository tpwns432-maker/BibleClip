package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject
import kotlin.math.ln

/**
 * Port of bibleclip/korean.py — the ONE tokenizer shared by the index and the
 * query, so both normalize the same way: tags out, split on spaces, edge
 * punctuation off, one trailing 조사 off (longest first), stopwords dropped.
 */
object Korean {
    private val PARTICLES = listOf(
        "으로서", "으로써", "에게서", "에서", "에게", "으로", "이라",
        "은", "는", "이", "가", "을", "를", "의", "에", "와", "과", "도", "로", "만",
    ).sortedByDescending { it.length }
    private val STOPWORDS = setOf("그", "또", "또한", "및", "곧", "그리고", "그러나", "하지만", "그것", "이것", "저것")
    private const val EDGE_PUNCT = " \t\r\n.,;:!?'\"()[]{}「」『』《》〈〉·…“”‘’~—"
    private val TAG = rx("<[^>]+>")
    private val SPACES = rx("""\s+""")

    fun stripParticle(token: String): String {
        for (p in PARTICLES) if (token.endsWith(p) && token.length > p.length) return token.dropLast(p.length)
        return token
    }

    fun tokenize(text: String?): List<String> {
        if (text.isNullOrEmpty()) return emptyList()
        val out = mutableListOf<String>()
        for (raw in SPACES.split(TAG.replace(text, " "))) {
            var tok = raw.trim { it in EDGE_PUNCT }
            if (tok.isEmpty()) continue
            tok = stripParticle(tok)
            if (tok.isEmpty() || tok in STOPWORDS) continue
            out += tok
        }
        return out
    }
}

/**
 * Port of bibleclip/data/synonyms.py — 고어↔현대어 search expansion
 * (web/data/bible_synonyms.json, {map: {word: [[alt, confidence], ...]}}).
 * A missing or broken file is an empty dictionary: search still works, unexpanded.
 */
class Synonyms(json: String?) {
    private val map: Map<String, List<Pair<String, Double>>> = try {
        val m = JSONObject(json ?: "{}").optJSONObject("map") ?: JSONObject()
        m.keys().asSequence().associateWith { k ->
            val arr = m.optJSONArray(k) ?: JSONArray()
            (0 until arr.length()).mapNotNull { i ->
                when (val e = arr.get(i)) {
                    is JSONArray -> if (e.length() >= 2) e.optString(0) to e.optDouble(1) else null
                    is String -> e to 1.0
                    else -> null
                }
            }
        }.filterValues { it.isNotEmpty() }
    } catch (e: Exception) {
        emptyMap()
    }

    /** [(alt, confidence)] in file order, at most [limit]. */
    fun expand(token: String, limit: Int = MAX_EXPAND): List<Pair<String, Double>> =
        if (token.isEmpty()) emptyList() else map[token].orEmpty().take(limit)

    /** {token: [alts]} for the tokens that have any — for highlighting. */
    fun expandAll(tokens: List<String>, limit: Int = MAX_EXPAND): LinkedHashMap<String, List<String>> {
        val out = LinkedHashMap<String, List<String>>()
        for (t in tokens) {
            val alts = expand(t, limit).map { it.first }
            if (alts.isNotEmpty()) out[t] = alts
        }
        return out
    }

    companion object {
        const val MAX_EXPAND = 3
        const val ASSET = "web/data/bible_synonyms.json"
    }
}

/** One search hit: book/chapter/verse + cleaned text. */
data class Hit(val book: Int, val chapter: Int, val verse: Int, val text: String)

/**
 * Port of BibleDB.search (bibleclip/data/bible_db.py) for one version:
 *   1. BM25 over a 조사-stripped inverted index, with synonym expansion
 *      (alternatives weighted by their confidence, best per query token);
 *   2. no hit → spacing-insensitive exact substring;
 *   3. still none → trigram overlap ≥ 0.7 (typo tolerance).
 * The desktop's step between 1 and 2 (smart_search) can never find what BM25
 * missed — BM25's term sets are a superset of it — so it's left out. Kiwi
 * morphology is off, as in the shipped desktop build. Pinned by
 * tests/golden/search.json.
 */
class VerseSearch(private val db: BibleDb, private val text: TextUtils) {

    private class Verse(val key: Long, val book: Int, val chapter: Int, val verse: Int,
                        val clean: String, val tokens: List<String>) {
        val despaced: String by lazy { despace(clean) }
    }

    private val verses: List<Verse> by lazy {
        db.allVerses().map { (b, c, v, raw) ->
            val clean = text.cleanText(raw)
            Verse(key(b, c, v), b, c, v, clean, Korean.tokenize(clean))
        }
    }
    private val byKey: Map<Long, Verse> by lazy { verses.associateBy { it.key } }

    /** 원형토큰 → verse keys (the BM25 / smart-search index). */
    private val inverted: Map<String, Set<Long>> by lazy {
        val idx = HashMap<String, MutableSet<Long>>()
        for (v in verses) for (t in v.tokens) idx.getOrPut(t) { HashSet() }.add(v.key)
        idx
    }

    /** (N, avgdl) for BM25 length normalization. */
    private val stats: Pair<Int, Double> by lazy {
        val n = verses.size.coerceAtLeast(1)
        val total = verses.sumOf { it.tokens.size }
        val avg = total.toDouble() / n
        n to (if (avg == 0.0) 1.0 else avg)
    }

    /** Build the index now (call off the main thread) so the first search is instant. */
    fun warm() {
        inverted.size
        stats.first
    }

    fun search(keyword: String?, mode: String = "and", limit: Int = 300, synonyms: Synonyms? = null,
               fuzzyThreshold: Double = 0.7): List<Hit> {
        val kw = (keyword ?: "").trim()
        if (kw.isEmpty()) return emptyList()
        try {
            val bm = bm25(kw, mode, limit, synonyms)
            if (bm.isNotEmpty()) return bm
        } catch (e: Exception) {
            // fall through to the plain passes, like the desktop
        }
        val qd = despace(kw)
        if (qd.isEmpty()) return emptyList()
        val exact = verses.filter { qd in it.despaced }
        if (exact.isNotEmpty()) return exact.take(limit).map { Hit(it.book, it.chapter, it.verse, it.clean) }
        val qtri = trigrams(qd)
        if (qtri.isEmpty()) return emptyList()
        val scored = mutableListOf<Pair<Double, Verse>>()
        for (v in verses) {
            val tri = trigrams(v.despaced)
            if (tri.isEmpty()) continue
            val inter = qtri.count { it in tri }
            if (inter == 0) continue
            val score = inter.toDouble() / qtri.size
            if (score >= fuzzyThreshold) scored += score to v
        }
        return scored.sortedWith(compareBy({ -it.first }, { it.second.key }))
            .take(limit).map { (_, v) -> Hit(v.book, v.chapter, v.verse, v.clean) }
    }

    private fun termKeys(term: String): Set<Long> {
        val out = HashSet<Long>()
        for ((k, keys) in inverted) if (term in k) out += keys
        return out
    }

    private class Member(val term: String, val weight: Double, val keys: Set<Long>, val idf: Double)

    private fun bm25(keyword: String, mode: String, limit: Int, syn: Synonyms?): List<Hit> {
        val (n, avgdl) = stats
        val tokens = Korean.tokenize(keyword)
        if (tokens.isEmpty()) return emptyList()

        val groups = mutableListOf<List<Member>>()
        for (t in tokens) {
            val members = mutableListOf(t to 1.0)
            if (syn != null) {
                val span = SYN_W_MAX - SYN_W_MIN
                for ((alt, c) in syn.expand(t)) {
                    val conf = if (c < 0.0) 0.0 else if (c > 1.0) 1.0 else c
                    members += alt to (SYN_W_MIN + span * conf)
                }
            }
            val info = members.mapNotNull { (term, w) ->
                val keys = termKeys(term)
                if (keys.isEmpty()) null
                else Member(term, w, keys, ln(1.0 + (n - keys.size + 0.5) / (keys.size + 0.5)))
            }
            if (info.isNotEmpty()) groups += info
        }
        if (groups.isEmpty()) return emptyList()

        val gsets = groups.map { g -> g.flatMapTo(HashSet()) { it.keys } }
        val cands: Set<Long> = if (mode == "or") gsets.flatMapTo(HashSet()) { it }
        else gsets.drop(1).fold(HashSet(gsets[0])) { acc, s -> acc.apply { retainAll(s) } }
        if (cands.isEmpty()) return emptyList()

        val scored = mutableListOf<Pair<Double, Long>>()
        for (key in cands) {
            val toks = byKey[key]?.tokens.orEmpty()
            val dl = if (toks.isEmpty()) 1 else toks.size
            val norm = K1 * (1.0 - B + B * dl / avgdl)
            var total = 0.0
            val firsts = mutableListOf<Int>()
            for (g in groups) {
                var best = 0.0
                var bestPos: Int? = null
                for (m in g) {
                    if (key !in m.keys) continue
                    var tf = 0
                    var pos: Int? = null
                    toks.forEachIndexed { i, tk ->
                        if (m.term in tk) {
                            tf += 1
                            if (pos == null) pos = i
                        }
                    }
                    if (tf == 0) continue
                    val sc = m.weight * m.idf * tf * (K1 + 1.0) / (tf + norm)
                    if (sc > best) {
                        best = sc
                        bestPos = pos
                    }
                }
                if (best != 0.0) {
                    total += best
                    bestPos?.let { firsts += it }
                }
            }
            if (total <= 0.0) continue
            if (firsts.size >= 2) {
                val span = firsts.max() - firsts.min()
                total += PROX_WEIGHT * maxOf(0.0, 1.0 - span.toDouble() / dl)
            }
            scored += total to key
        }
        return scored.sortedWith(compareBy({ -it.first }, { it.second }))
            .take(limit).map { (_, k) ->
                val v = byKey.getValue(k)
                Hit(v.book, v.chapter, v.verse, db.getVerseText(v.book, v.chapter, v.verse))
            }
    }

    companion object {
        const val K1 = 1.5
        const val B = 0.75
        const val SYN_W_MIN = 0.15
        const val SYN_W_MAX = 0.75
        const val PROX_WEIGHT = 1.2

        private val SPACES = rx("""\s+""")
        fun despace(s: String): String = SPACES.replace(s, "")

        /** 3-character shingles (the whole string when shorter). */
        fun trigrams(s: String): Set<String> = when {
            s.isEmpty() -> emptySet()
            s.length < 3 -> setOf(s)
            else -> (0..s.length - 3).mapTo(HashSet()) { s.substring(it, it + 3) }
        }

        /** (book, chapter, verse) as one sortable number — orders like the tuple. */
        fun key(b: Int, c: Int, v: Int): Long = b * 1_000_000L + c * 1_000L + v
    }
}
