package com.bibleclip.app

import android.app.Activity
import android.content.ClipData
import android.content.ClipboardManager
import android.content.Intent
import android.os.Bundle
import android.widget.Toast
import com.bibleclip.app.core.Output
import java.util.concurrent.Executors

/**
 * 글자 선택 메뉴 → "BibleClip 구절" — the Android stand-in for the desktop
 * clipboard monitor. The selected reference ("요 3:16") becomes the formatted
 * verse text, in place when the field is editable, else on the clipboard.
 * No UI of its own: works off the main thread, answers, closes.
 */
class ProcessTextActivity : Activity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        val selected = intent.getCharSequenceExtra(Intent.EXTRA_PROCESS_TEXT)?.toString().orEmpty()
        val readOnly = intent.getBooleanExtra(Intent.EXTRA_PROCESS_TEXT_READONLY, false)
        val app = application as BibleClipApp
        worker.execute {
            val result = try {
                app.library.buildOutput(selected)
            } catch (e: Exception) {
                null
            }
            runOnUiThread { finishWith(result, readOnly) }
        }
    }

    private fun finishWith(result: Output?, readOnly: Boolean) {
        when (result) {
            is Output.Reference -> {
                if (readOnly) {
                    val cm = getSystemService(ClipboardManager::class.java)
                    cm.setPrimaryClip(ClipData.newPlainText("BibleClip", result.text))
                    toast(getString(R.string.toast_copied, result.shortName, result.chapter))
                } else {
                    setResult(RESULT_OK, Intent().putExtra(Intent.EXTRA_PROCESS_TEXT, result.text))
                }
            }
            is Output.Keyword -> toast(getString(R.string.toast_keyword))
            null -> toast(getString(R.string.toast_no_reference))
        }
        finish()
    }

    private fun toast(msg: String) = Toast.makeText(applicationContext, msg, Toast.LENGTH_SHORT).show()

    companion object {
        private val worker = Executors.newSingleThreadExecutor()
    }
}
