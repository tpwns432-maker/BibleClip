package com.bibleclip.app

import android.database.Cursor
import android.database.sqlite.SQLiteDatabase
import com.bibleclip.app.core.BibleDb
import com.bibleclip.app.core.TextUtils
import java.io.File

/** [BibleDb] over Android's SQLite, opened read-only. */
class AndroidBibleDb(file: File, text: TextUtils) : BibleDb(nameOf(file.name), text) {
    // No-op error handler: Android's default one DELETES a database file it finds
    // corrupt — that would be a bible the user added. A bad file should just fail.
    private val db = SQLiteDatabase.openDatabase(file.path, null, SQLiteDatabase.OPEN_READONLY) { }

    override fun query(sql: String, vararg args: Any): List<List<Any?>> =
        db.rawQuery(sql, args.map { it.toString() }.toTypedArray()).use { c ->
            val out = ArrayList<List<Any?>>(c.count)
            while (c.moveToNext()) out += List(c.columnCount) { value(c, it) }
            out
        }

    private fun value(c: Cursor, i: Int): Any? = when (c.getType(i)) {
        Cursor.FIELD_TYPE_NULL -> null
        Cursor.FIELD_TYPE_INTEGER -> c.getLong(i)
        Cursor.FIELD_TYPE_FLOAT -> c.getDouble(i)
        else -> c.getString(i)
    }

    override fun close() = db.close()
}
