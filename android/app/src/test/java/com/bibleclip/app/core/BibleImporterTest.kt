package com.bibleclip.app.core

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Rule
import org.junit.Test
import org.junit.rules.TemporaryFolder
import java.io.ByteArrayOutputStream
import java.io.File
import java.util.zip.ZipEntry
import java.util.zip.ZipOutputStream

/** [＋ 성경 파일 추가…] checks — the same cases tests/test_core.py import_bibles_check runs on desktop. */
class BibleImporterTest {
    @get:Rule val tmp = TemporaryFolder()

    private val root = File(System.getProperty("bibleclip.repoRoot") ?: "..")
    private val tables = Tables(File(root, "android/app/src/main/assets/${Tables.ASSET}").readText())
    private val text = TextUtils(tables)
    private val krv = File(root, "bible_versions/KRV.SQLite3")

    private fun importer(dest: File) = BibleImporter(dest, tmp.newFolder()) { JdbcBibleDb(it, text) }
    private fun file(name: String, bytes: ByteArray) = ImportSource(name) { bytes.inputStream() }
    private fun zip(vararg entries: Pair<String, ByteArray>): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { z ->
            entries.forEach { (n, b) -> z.putNextEntry(ZipEntry(n)); z.write(b); z.closeEntry() }
        }
        return out.toByteArray()
    }

    @Test
    fun addsBibleRefusesClashAndJunk() {
        val dest = tmp.newFolder("bible_versions")
        val (added, errors) = importer(dest).import(
            listOf(
                file("MyBible.SQLite3", krv.readBytes()),
                file("KRV.SQLite3", krv.readBytes()),          // clashes with a loaded version
                file("notes.SQLite3", "not a database".toByteArray()),
                file("photo.jpg", krv.readBytes()),            // a bible, but not a bible file name
            ),
            taken = setOf("KRV"),
        )
        assertEquals(listOf("MyBible.SQLite3"), added)
        assertEquals(
            listOf(ImportError("KRV.SQLite3", "exists"), ImportError("notes.SQLite3", "invalid"),
                ImportError("photo.jpg", "invalid")),
            errors,
        )
        assertTrue(File(dest, "MyBible.SQLite3").length() == krv.length())
        // Case-insensitive clash with a file already in the folder.
        val (again, errs2) = importer(dest).import(listOf(file("mybible.sqlite3", krv.readBytes())), emptySet())
        assertEquals(emptyList<String>(), again)
        assertEquals(listOf(ImportError("mybible.sqlite3", "exists")), errs2)
    }

    @Test
    fun zipTakesBareNamesOnly() {
        val dest = tmp.newFolder("bible_versions")
        val z = zip(
            "folder/Inner.SQLite3" to krv.readBytes(),
            "../Escape.SQLite3" to krv.readBytes(),           // zip-slip: lands as bare Escape.SQLite3
            "__MACOSX/folder/._Inner.SQLite3" to ByteArray(10),
            "readme.txt" to "hi".toByteArray(),
        )
        val (added, errors) = importer(dest).import(listOf(file("pack.zip", z)), emptySet())
        assertEquals(listOf("Inner.SQLite3", "Escape.SQLite3"), added)
        assertEquals(emptyList<ImportError>(), errors)
        assertFalse(File(dest.parentFile, "Escape.SQLite3").exists())
        assertEquals(setOf("Inner.SQLite3", "Escape.SQLite3"), dest.list()!!.toSet())
    }

    @Test
    fun zipErrors() {
        val dest = tmp.newFolder("bible_versions")
        val (added, errors) = importer(dest).import(
            listOf(file("empty.zip", zip("readme.txt" to "hi".toByteArray())), file("broken.zip", "PK junk".toByteArray())),
            emptySet(),
        )
        assertEquals(emptyList<String>(), added)
        assertEquals(listOf(ImportError("empty.zip", "empty_zip"), ImportError("broken.zip", "read_error")), errors)
    }
}
