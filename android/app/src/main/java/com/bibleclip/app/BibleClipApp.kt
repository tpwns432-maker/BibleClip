package com.bibleclip.app

import android.app.Application
import android.util.Log
import com.bibleclip.app.core.BibleDb
import com.bibleclip.app.core.BibleImporter
import com.bibleclip.app.core.ImportError
import com.bibleclip.app.core.ImportSource
import com.bibleclip.app.core.Library
import com.bibleclip.app.core.Settings
import com.bibleclip.app.core.Tables
import org.json.JSONObject
import java.io.File

/**
 * Owns the one [Library] the WebView bridge and the selection converter share.
 *
 * Data lives in filesDir (same names as the desktop data folder):
 *   bible_versions/   bundled KRV·KJV+ copied from assets + versions the user adds
 *   bibleclip_settings.json, bible_versions/aliases_override.json
 */
class BibleClipApp : Application() {

    val bibleDir: File get() = File(filesDir, "bible_versions")
    private val settingsFile: File get() = File(filesDir, "bibleclip_settings.json")
    private val aliasFile: File get() = File(bibleDir, "aliases_override.json")

    /** Built on first use (off the main thread where possible — it opens every bible). */
    val library: Library by lazy { load() }

    private fun load(): Library {
        val t0 = System.nanoTime()
        installBundledBibles()
        val tables = Tables(assets.open(Tables.ASSET).bufferedReader().use { it.readText() })
        val saved = readJson(settingsFile)
        val settings = Settings.of(tables.defaultSettings, saved)
        // An existing settings file without tour_done = someone already using the app.
        if (saved != null && !saved.has("tour_done")) settings["tour_done"] = true
        val lib = Library(tables, settings) { readJson(aliasFile) ?: JSONObject() }
        scanBibles(lib)
        lib.validateSettings()
        Log.i(TAG, "library: ${lib.dbs.keys} in ${(System.nanoTime() - t0) / 1_000_000} ms")
        return lib
    }

    /** Load every bible file in bibleDir not loaded yet; returns the new names. */
    @Synchronized
    fun scanBibles(lib: Library = library): List<String> {
        val added = mutableListOf<String>()
        bibleDir.listFiles()
            ?.filter { it.name.lowercase().run { endsWith(".sqlite3") || endsWith(".sqlite") || endsWith(".db") } }
            ?.sortedBy { it.name }
            ?.forEach { f ->
                if (BibleDb.nameOf(f.name) in lib.dbs) return@forEach
                try {
                    if (lib.add(AndroidBibleDb(f, lib.text))) added += BibleDb.nameOf(f.name)
                } catch (e: Exception) {
                    Log.w(TAG, "skip ${f.name}: $e")
                }
            }
        return added
    }

    /** [＋ 성경 파일 추가…]: copy the picked files (checked like the desktop's) into
     *  bibleDir and load them. Returns (names loaded, files refused). */
    @Synchronized
    fun importBibles(sources: List<ImportSource>): Pair<List<String>, List<ImportError>> {
        val lib = library
        val importer = BibleImporter(bibleDir, cacheDir) { AndroidBibleDb(it, lib.text) }
        val (_, errors) = importer.import(sources, lib.dbs.keys)
        return scanBibles(lib) to errors
    }

    /** Copy the bundled bibles out of the APK (SQLite needs a real file) — on first
     *  run and after each app update; files the user added are untouched. */
    private fun installBundledBibles() {
        bibleDir.mkdirs()
        val stamp = File(bibleDir, ".bundled")
        @Suppress("DEPRECATION")
        val installed = packageManager.getPackageInfo(packageName, 0).lastUpdateTime.toString()
        if (stamp.exists() && stamp.readText() == installed) return
        for (name in assets.list(BUNDLED_DIR).orEmpty()) {
            val tmp = File(bibleDir, "$name.part")
            assets.open("$BUNDLED_DIR/$name").use { src -> tmp.outputStream().use { src.copyTo(it) } }
            tmp.renameTo(File(bibleDir, name))
        }
        stamp.writeText(installed)
    }

    @Synchronized
    fun saveSettings() {
        val tmp = File(filesDir, "bibleclip_settings.json.part")
        tmp.writeText(library.settings.json.toString(2))
        tmp.renameTo(settingsFile)
    }

    private fun readJson(f: File): JSONObject? = try {
        if (f.exists()) JSONObject(f.readText()) else null
    } catch (e: Exception) {
        Log.w(TAG, "bad ${f.name}: $e")
        null
    }

    companion object {
        const val TAG = "BibleClip"
        private const val BUNDLED_DIR = "bible_versions"
    }
}
