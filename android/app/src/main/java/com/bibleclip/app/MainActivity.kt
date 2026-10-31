package com.bibleclip.app

import android.annotation.SuppressLint
import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.content.pm.ApplicationInfo
import android.net.Uri
import android.os.Bundle
import android.webkit.WebResourceRequest
import android.webkit.WebResourceResponse
import android.webkit.WebView
import androidx.webkit.WebViewAssetLoader
import androidx.webkit.WebViewClientCompat
import java.io.ByteArrayInputStream

/**
 * Hosts the desktop web UI (assets/web, copied from the repo's web/ at build time)
 * in a WebView. Pages are served from https://appassets.androidplatform.net so
 * fetch() and storage behave like a normal origin; assets/android/bridge.js is
 * injected ahead of the page scripts to provide window.pywebview.api.
 */
class MainActivity : Activity() {

    private lateinit var web: WebView

    @SuppressLint("SetJavaScriptEnabled")
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE != 0) {
            WebView.setWebContentsDebuggingEnabled(true)
        }
        val app = application as BibleClipApp
        web = WebView(this)
        setContentView(web)
        web.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
        }

        val assetsHandler = WebViewAssetLoader.AssetsPathHandler(this)
        val loader = WebViewAssetLoader.Builder()
            .addPathHandler("/assets/") { path ->
                if (path == INDEX) injectBridge() else assetsHandler.handle(path)
            }
            .build()

        web.webViewClient = object : WebViewClientCompat() {
            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? =
                loader.shouldInterceptRequest(request.url)

            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                if (request.url.host == WebViewAssetLoader.DEFAULT_DOMAIN) return false
                // External links (GitHub, releases) open in the browser.
                startActivity(Intent(Intent.ACTION_VIEW, request.url))
                return true
            }
        }
        web.addJavascriptInterface(Bridge(app, web, ::pickBibleFiles), "BibleClipNative")
        if (savedInstanceState == null) web.loadUrl(START_URL) else web.restoreState(savedInstanceState)
    }

    /** web/index.html with the phone stylesheet after its own (so it wins),
     *  bridge.js before its first script and mobile.js after its last. */
    private fun injectBridge(): WebResourceResponse {
        var html = assets.open(INDEX).bufferedReader().use { it.readText() }
        html = insertBefore(html, "</head>", "<link rel=\"stylesheet\" href=\"../android/mobile.css\">\n")
        html = insertBefore(html, "<script", "<script src=\"../android/bridge.js\"></script>\n")
        html = insertBefore(html, "</body>", "<script src=\"../android/mobile.js\"></script>\n")
        return WebResourceResponse("text/html", "utf-8", ByteArrayInputStream(html.toByteArray()))
    }

    private fun insertBefore(html: String, marker: String, tag: String): String {
        val at = html.indexOf(marker)
        return if (at >= 0) html.substring(0, at) + tag + html.substring(at) else html + tag
    }

    private var pickDone: ((List<Uri>) -> Unit)? = null

    /** System file picker for [＋ 성경 파일 추가…] — any type: .SQLite3 has no MIME
     *  type of its own, so filtering would hide the very files we want. */
    private fun pickBibleFiles(done: (List<Uri>) -> Unit) {
        pickDone?.invoke(emptyList())
        pickDone = done
        val intent = Intent(Intent.ACTION_OPEN_DOCUMENT)
            .addCategory(Intent.CATEGORY_OPENABLE)
            .setType("*/*")
            .putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true)
        try {
            @Suppress("DEPRECATION")
            startActivityForResult(intent, REQ_PICK_BIBLES)
        } catch (e: ActivityNotFoundException) {
            pickDone = null
            done(emptyList())
        }
    }

    @Deprecated("Deprecated in Java")
    override fun onActivityResult(requestCode: Int, resultCode: Int, data: Intent?) {
        if (requestCode != REQ_PICK_BIBLES) {
            @Suppress("DEPRECATION")
            super.onActivityResult(requestCode, resultCode, data)
            return
        }
        val done = pickDone ?: return
        pickDone = null
        val uris = mutableListOf<Uri>()
        if (resultCode == RESULT_OK && data != null) {
            val clip = data.clipData
            if (clip != null) for (i in 0 until clip.itemCount) uris += clip.getItemAt(i).uri
            else data.data?.let { uris += it }
        }
        done(uris)
    }

    override fun onSaveInstanceState(outState: Bundle) {
        super.onSaveInstanceState(outState)
        web.saveState(outState)
    }

    override fun onDestroy() {
        pickDone?.invoke(emptyList())   // never leave the bridge worker waiting
        pickDone = null
        web.destroy()
        super.onDestroy()
    }

    companion object {
        private const val INDEX = "web/index.html"
        private const val REQ_PICK_BIBLES = 41
        private val START_URL = Uri.Builder().scheme("https").authority(WebViewAssetLoader.DEFAULT_DOMAIN)
            .path("/assets/$INDEX").build().toString()
    }
}
