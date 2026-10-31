package com.bibleclip.app.core

import java.util.regex.Pattern

/**
 * Python-compatible regex: \d \s \w match Unicode like Python 3's `re`.
 * Android's ICU regex is already Unicode-aware and rejects the flag, so fall
 * back to a plain compile there.
 */
internal fun rx(pattern: String): Regex = try {
    Pattern.compile(pattern, Pattern.UNICODE_CHARACTER_CLASS).toRegex()
} catch (e: IllegalArgumentException) {
    Regex(pattern)
}

/** Port of bibleclip/text_utils.py (hangul assembly + verse text cleaning). */
class TextUtils(private val t: Tables) {

    private fun isCho(j: String) = j in t.choseong
    private fun isJung(j: String) = j in t.jungseong

    fun assembleHangul(jamo: List<String>): String {
        val out = StringBuilder()
        var i = 0
        while (i < jamo.size) {
            val j = jamo[i]
            if (isCho(j) && i + 1 < jamo.size && isJung(jamo[i + 1])) {
                val cho = t.choseong.indexOf(j)
                i += 1
                var jungChar = jamo[i]
                if (i + 1 < jamo.size && isJung(jamo[i + 1])) {
                    val pair = jungChar to jamo[i + 1]
                    t.complexJungseong[pair]?.let {
                        jungChar = it
                        i += 1
                    }
                }
                val jung = t.jungseong.indexOf(jungChar)
                var jong = 0
                if (i + 1 < jamo.size && isCho(jamo[i + 1])) {
                    val potential = jamo[i + 1]
                    if (i + 2 < jamo.size && isJung(jamo[i + 2])) {
                        // next jamo starts a new syllable
                    } else if (potential in t.jongseong) {
                        val cplx = if (i + 2 < jamo.size && isCho(jamo[i + 2]))
                            t.complexJongseong[potential to jamo[i + 2]] else null
                        if (cplx != null) {
                            if (i + 3 < jamo.size && isJung(jamo[i + 3])) {
                                jong = t.jongseong.indexOf(potential)
                                i += 1
                            } else {
                                jong = t.jongseong.indexOf(cplx)
                                i += 2
                            }
                        } else {
                            jong = t.jongseong.indexOf(potential)
                            i += 1
                        }
                    }
                }
                out.append((0xAC00 + cho * 21 * 28 + jung * 28 + jong).toChar())
            } else {
                out.append(j)
            }
            i += 1
        }
        return out.toString()
    }

    /** 'dy' → '요' when every char is on the 두벌식 map, else null ('' → ''). */
    fun convertQwertyToHangul(text: String): String? {
        if (!text.all { it in t.qwertyToHangul }) return null
        return assembleHangul(text.map { t.qwertyToHangul.getValue(it) })
    }

    fun cleanText(text: String?): String {
        if (text.isNullOrEmpty()) return ""
        var s = STRONGS.replace(text, "")
        s = FOOTNOTE.replace(s, "")
        s = TITLE.replace(s, "")
        s = TAG.replace(s, "")
        s = BRACKET_TITLE.replace(s, "")
        return SPACES.replace(s, " ").trim()
    }

    companion object {
        private val STRONGS = rx("""<S>\d+</S>""")
        private val FOOTNOTE = rx("""<f>[^<]*</f>""")
        private val TITLE = rx("""<n>\[?[^\]<]*\]?</n>""")
        private val TAG = rx("""<[^>]+/?>""")
        private val BRACKET_TITLE = rx("""\[[가-힣a-zA-Z0-9\s,.:]+\]\s*""")
        private val SPACES = rx("""\s+""")
    }
}
