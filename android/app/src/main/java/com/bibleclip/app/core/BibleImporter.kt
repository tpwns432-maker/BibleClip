package com.bibleclip.app.core

import java.io.File
import java.io.IOException
import java.io.InputStream
import java.io.OutputStream
import java.nio.charset.Charset
import java.util.zip.ZipInputStream

/** A picked file: its display name and a way to read it (a SAF Uri on Android). */
class ImportSource(val name: String, val open: () -> InputStream)

/** One file that wasn't added: code = exists | invalid | empty_zip | read_error | copy_error. */
data class ImportError(val file: String, val code: String)

/**
 * [＋ 성경 파일 추가…] — port of Library.import_bible_files (desktop v1.2.1).
 *
 * Copies bible DB files, or the DBs inside .zip files, into [dest] after the
 * same checks: it must open as a bible (info/books/verses, with verses) and its
 * name must not clash, case-insensitively, with [taken] or a file already in
 * [dest]. Zip members are taken by their bare filename, so nothing lands outside
 * [dest]. [openDb] opens a candidate file for the check; [tmp] is scratch space.
 */
class BibleImporter(
    private val dest: File,
    private val tmp: File,
    private val openDb: (File) -> BibleDb,
) {
    /** Returns the file names copied into [dest] and the ones refused. */
    fun import(sources: List<ImportSource>, taken: Set<String>): Pair<List<String>, List<ImportError>> {
        dest.mkdirs()
        val names = taken.map { it.lowercase() }.toMutableSet()
        dest.listFiles()?.forEach { names += it.name.substringBeforeLast('.').lowercase() }
        val errors = mutableListOf<ImportError>()
        val added = mutableListOf<String>()
        val work = File(tmp, "bibleclip_add_${System.nanoTime()}").apply { mkdirs() }
        try {
            val cands = mutableListOf<Pair<String, File>>()
            for (src in sources) {
                if (src.name.lowercase().endsWith(".zip")) {
                    val found = try {
                        extractBibles(src, work)
                    } catch (e: Exception) {
                        errors += ImportError(src.name, "read_error")
                        continue
                    }
                    if (found.isEmpty()) errors += ImportError(src.name, "empty_zip")
                    cands += found
                } else {
                    val f = File(File(work, "f${cands.size}_${System.nanoTime()}").apply { mkdirs() }, "in")
                    try {
                        src.open().use { input -> f.outputStream().use { copyCapped(input, it) } }
                    } catch (e: Exception) {
                        errors += ImportError(src.name, "read_error")
                        continue
                    }
                    cands += src.name to f
                }
            }
            for ((fname, file) in cands) {
                val key = fname.substringBeforeLast('.').lowercase()
                if (key in names) {
                    errors += ImportError(fname, "exists")
                    continue
                }
                if (!fname.lowercase().endsWith(BIBLE_EXTS) || !isBible(file)) {
                    errors += ImportError(fname, "invalid")
                    continue
                }
                try {
                    file.copyTo(File(dest, fname), overwrite = false)
                } catch (e: Exception) {
                    errors += ImportError(fname, "copy_error")
                    continue
                }
                names += key
                added += fname
            }
        } finally {
            work.deleteRecursively()
        }
        return added to errors
    }

    private fun isBible(f: File): Boolean = try {
        val db = openDb(f)
        try { db.looksLikeBible() } finally { db.close() }
    } catch (e: Exception) {
        false
    }

    /** The bible DB members of a zip, each extracted into its own folder. Entries
     *  without the zip UTF-8 flag are read as cp949 (Korean zips from Windows). */
    private fun extractBibles(src: ImportSource, work: File): List<Pair<String, File>> {
        val out = mutableListOf<Pair<String, File>>()
        src.open().use { raw ->
            ZipInputStream(raw.buffered(), LEGACY_ZIP_CHARSET).use { zip ->
                var n = 0
                var entries = 0
                while (true) {
                    val e = zip.nextEntry ?: break
                    entries++
                    if (e.isDirectory || e.name.startsWith("__MACOSX/")) continue
                    val base = e.name.replace('\\', '/').substringAfterLast('/')
                    if (base.isEmpty() || base.startsWith(".") || ':' in base ||
                        !base.lowercase().endsWith(BIBLE_EXTS) || e.size > MAX_BIBLE_BYTES) continue
                    val f = File(File(work, "z${n++}").apply { mkdirs() }, base)
                    try {
                        f.outputStream().use { copyCapped(zip, it) }
                    } catch (tooBig: TooBig) {
                        f.delete()
                        continue
                    }
                    out += base to f
                }
                // Not a zip at all (the stream reader just finds no entries) — the
                // desktop's zipfile raises here, so report it the same: read_error.
                if (entries == 0) throw IOException("not a zip archive")
            }
        }
        return out
    }

    private class TooBig : IOException()

    /** Copy, refusing anything over [MAX_BIBLE_BYTES] (one bible is ~5–50MB; caps a zip bomb). */
    private fun copyCapped(input: InputStream, output: OutputStream) {
        val buf = ByteArray(64 * 1024)
        var total = 0L
        while (true) {
            val r = input.read(buf)
            if (r < 0) break
            total += r
            if (total > MAX_BIBLE_BYTES) throw TooBig()
            output.write(buf, 0, r)
        }
    }

    companion object {
        private val BIBLE_EXTS = arrayOf(".sqlite3", ".sqlite", ".db")
        private fun String.endsWith(suffixes: Array<String>) = suffixes.any { endsWith(it) }
        const val MAX_BIBLE_BYTES = 512L * 1024 * 1024

        /** cp949 under whichever name this runtime knows it by. */
        private val LEGACY_ZIP_CHARSET: Charset = listOf("MS949", "x-windows-949", "windows-949", "EUC-KR")
            .firstNotNullOfOrNull { runCatching { Charset.forName(it) }.getOrNull() } ?: Charsets.UTF_8
    }
}
