package com.bibleclip.app.core

import org.json.JSONArray
import org.json.JSONObject

/**
 * The desktop settings dict (bibleclip_settings.json) — same keys, same JSON, so
 * a desktop settings file means the same thing here. Reads follow Python's
 * `s.get(key, default)` + truthiness, which the formatter relies on.
 */
class Settings(val json: JSONObject) {

    operator fun get(key: String): Any? = json.opt(key).takeUnless { it == JSONObject.NULL }

    fun str(key: String, default: String): String = get(key)?.toString() ?: default

    /** Python truthiness of `s.get(key, default)`. */
    fun truthy(key: String, default: Boolean = false): Boolean =
        if (!json.has(key)) default else truthy(get(key))

    fun strings(key: String): List<String> {
        val a = get(key) as? JSONArray ?: return emptyList()
        return List(a.length()) { a.optString(it) }
    }

    operator fun set(key: String, value: Any?) {
        json.put(key, value ?: JSONObject.NULL)
    }

    companion object {
        /** Defaults (Library.DEFAULT_SETTINGS) overlaid with [saved]. */
        fun of(defaults: JSONObject, saved: JSONObject? = null): Settings {
            val o = JSONObject(defaults.toString())
            saved?.keys()?.forEach { k -> if (o.has(k)) o.put(k, saved.get(k)) }
            return Settings(o)
        }

        fun truthy(v: Any?): Boolean = when (v) {
            null, JSONObject.NULL -> false
            is Boolean -> v
            is String -> v.isNotEmpty()
            is Number -> v.toDouble() != 0.0
            is JSONArray -> v.length() > 0
            is JSONObject -> v.length() > 0
            else -> true
        }
    }
}
