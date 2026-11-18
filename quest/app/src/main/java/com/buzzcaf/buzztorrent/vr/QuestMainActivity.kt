package com.buzzcaf.buzztorrent.vr

import android.content.Intent
import android.webkit.JavascriptInterface
import android.webkit.WebView
import com.buzzcaf.buzztorrent.tv.MainActivity
import com.buzzcaf.buzztorrent.tv.PlayerActivity

/** Browse on the Quest: the TV app's screen as a flat panel; ▶ Play opens the VR cinema. */
class QuestMainActivity : MainActivity() {
  override fun playerIntent(payload: String): Intent =
      cinemaIntent().putExtra(PlayerActivity.EXTRA, payload)

  private fun cinemaIntent(): Intent =
      Intent(this, CinemaActivity::class.java)
          .setAction(Intent.ACTION_MAIN)
          .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)

  override fun addBridges(web: WebView) {
    web.addJavascriptInterface(VrBridge(), "BuzzVR")
  }

  /** The page's "🥽 VR rooms" button: the cinema with no video, to look around and pick a room. */
  inner class VrBridge {
    @JavascriptInterface
    fun openCinema(): String {
      if (!showingOurPage()) return "none"
      runOnUiThread { startActivity(cinemaIntent()) }
      return "ok"
    }
  }
}
