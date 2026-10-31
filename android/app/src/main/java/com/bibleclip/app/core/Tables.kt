package com.bibleclip.app.core

import org.json.JSONObject

/** One canonical book: MyBible number + Korean short/long name (KOREAN_BOOK_MAP value). */
data class Book(val num: Int, val short: String, val long: String)

/**
 * Static tables from bibleclip/constants.py and Library.DEFAULT_SETTINGS.
 *
 * tests/make_golden.py writes them to assets/core/tables.json — never edit that
 * file or copy its contents into Kotlin; change constants.py and re-run the script.
 */
class Tables(json: String) {
    val koreanBookMap: Map<String, Book>
    val englishBookMap: Map<String, Int>
    val qwertyToHangul: Map<Char, String>
    val choseong: List<String>
    val jungseong: List<String>
    val jongseong: List<String>
    val complexJungseong: Map<Pair<String, String>, String>
    val complexJongseong: Map<Pair<String, String>, String>
    val englishVersions: Set<String>
    val defaultSettings: JSONObject

    init {
        val o = JSONObject(json)
        val kb = o.getJSONObject("korean_book_map")
        koreanBookMap = kb.keys().asSequence().associateWith { k ->
            val a = kb.getJSONArray(k)
            Book(a.getInt(0), a.getString(1), a.getString(2))
        }
        val eb = o.getJSONObject("english_book_map")
        englishBookMap = eb.keys().asSequence().associateWith { eb.getInt(it) }
        val q = o.getJSONObject("qwerty_to_hangul")
        qwertyToHangul = q.keys().asSequence().associate { it[0] to q.getString(it) }
        choseong = strings(o, "choseong")
        jungseong = strings(o, "jungseong")
        jongseong = strings(o, "jongseong")
        complexJungseong = triples(o, "complex_jungseong")
        complexJongseong = triples(o, "complex_jongseong")
        englishVersions = strings(o, "english_versions").toSet()
        defaultSettings = o.getJSONObject("default_settings")
    }

    /** {book_num: Book} — every alias of a book maps to the same Book (Engine._canon). */
    val canon: Map<Int, Book> by lazy { koreanBookMap.values.associateBy { it.num } }

    private fun strings(o: JSONObject, key: String): List<String> {
        val a = o.getJSONArray(key)
        return List(a.length()) { a.getString(it) }
    }

    private fun triples(o: JSONObject, key: String): Map<Pair<String, String>, String> {
        val a = o.getJSONArray(key)
        return (0 until a.length()).associate {
            val t = a.getJSONArray(it)
            (t.getString(0) to t.getString(1)) to t.getString(2)
        }
    }

    companion object {
        const val ASSET = "core/tables.json"
    }
}
