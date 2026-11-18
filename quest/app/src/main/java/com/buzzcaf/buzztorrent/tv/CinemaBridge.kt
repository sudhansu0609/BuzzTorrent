package com.buzzcaf.buzztorrent.tv

import android.content.Context
import android.webkit.JavascriptInterface
import org.json.JSONObject

/**
 * window.BuzzTV for the BuzzTorrent page on the VR cinema's web screen (🔍 Browse), so you can
 * search and press ▶ Play without leaving the room: films play in the cinema itself. The page
 * feature-detects the rest, so what a VR room can't do (another player app, voice search,
 * launching TV apps) is simply left out. It lives in the TV app's package to reuse TvDownloads
 * as it is, and answers only while [shown] is the paired PC's page.
 */
class CinemaBridge(
    private val ctx: Context,
    private val shown: () -> String,
    private val onPlay: (String) -> Unit,
    private val onWeb: (String) -> Unit,
    private val onServer: (String) -> Unit,
) {
  private val prefs = ctx.getSharedPreferences("buzztv", Context.MODE_PRIVATE)
  private val downloads by lazy { TvDownloads(ctx) }

  /** The PC paired in the browse panel, or null. */
  fun server(): String? = prefs.getString("server", null)

  private fun ours(): Boolean {
    val s = server() ?: return false
    val u = shown()
    return u == s || u.startsWith("$s/")
  }

  @JavascriptInterface fun installedApps() = "[]"

  @JavascriptInterface fun openService(appsJson: String?, name: String?, query: String?) = "none"

  @JavascriptInterface fun canGlobalSearch() = false

  @JavascriptInterface fun globalSearch(query: String?) = "none"

  @JavascriptInterface fun canVoice() = false

  @JavascriptInterface fun voiceSearch(lang: String?) = "none"

  /** An https link from the page opens on the same screen. */
  @JavascriptInterface
  fun openWeb(url: String?): String {
    if (!ours() || url == null || !url.startsWith("https://")) return "none"
    onWeb(url)
    return "ok"
  }

  @JavascriptInterface
  fun playNative(payload: String?): String {
    if (!ours() || payload == null || payload.length > 2_000_000) return "none"
    onPlay(payload)
    return "ok"
  }

  // ---- downloads to the headset (the same ones the browse panel shows)
  @JavascriptInterface fun storage(): String = if (ours()) downloads.storage().toString() else "[]"

  @JavascriptInterface
  fun downloadToTv(json: String?): String {
    if (!ours()) return "not allowed"
    return try {
      downloads.start(JSONObject(json ?: ""))
    } catch (e: Exception) {
      "Couldn't start the download"
    }
  }

  @JavascriptInterface fun listDownloads(): String = if (ours()) downloads.list().toString() else "[]"

  @JavascriptInterface
  fun deleteDownload(id: String?) {
    if (ours()) id?.toLongOrNull()?.let { downloads.delete(it) }
  }

  @JavascriptInterface
  fun playDownload(id: String?): String {
    if (!ours()) return "none"
    val payload = id?.toLongOrNull()?.let { downloads.playPayload(it) } ?: return "none"
    onPlay(payload)
    return "ok"
  }

  @JavascriptInterface
  fun appVersion(): String =
      runCatching { ctx.packageManager.getPackageInfo(ctx.packageName, 0).versionName ?: "" }.getOrDefault("")

  @JavascriptInterface fun savedServer(): String = if (ours()) server() ?: "" else ""

  /** Pairing with another PC happens in the browse panel, not here. */
  @JavascriptInterface fun resetServer() {}

  // ---- PC ⇄ Mac: switch between the computers paired in the browse panel
  @JavascriptInterface fun computers(): String = if (ours()) Computers.json(prefs) else "{}"

  @JavascriptInterface
  fun switchTo(url: String?): String {
    if (!ours() || url == null || !Computers.known(prefs, url)) return "bad"
    val info = Computers.hello(url) ?: return "offline"
    Computers.remember(prefs, url, info)
    prefs.edit().putString("server", url).apply()
    onServer(url)
    return "ok"
  }
}
