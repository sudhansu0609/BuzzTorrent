package com.buzzcaf.buzztorrent.vr

import android.content.Context
import android.content.SharedPreferences
import android.graphics.Bitmap
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.os.SystemClock
import android.util.Log
import android.view.InputDevice
import android.view.KeyCharacterMap
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection
import android.webkit.ConsoleMessage
import android.webkit.CookieManager
import android.webkit.PermissionRequest
import android.webkit.WebChromeClient
import android.webkit.WebResourceRequest
import android.webkit.WebSettings
import android.webkit.WebView
import android.webkit.WebViewClient
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject

/**
 * A web browser on the cinema screen: YouTube, Prime Video, Netflix or any site, clicked with the
 * controller's pointer. The page itself is one panel (on the screen); its bar (back, address,
 * sites) and a big on-screen keyboard are two more, near the viewer, made by [bar] and [keyboard].
 *
 * The page asks for the desktop site (a Chrome on Linux user agent): on a screen this size it reads
 * better than the phone site, and Prime Video and Netflix only play in a desktop browser.
 */
class WebScreen(
    private val prefs: SharedPreferences,
    private val button: (Context, String, () -> Unit) -> TextView,
    private val label: (Context, Float, Int) -> TextView,
    /** The BuzzTorrent page (🎬 Movies) rather than the open web: a phone-style browser, a one-row
     *  bar, and the keyboard types straight into the page's search box. */
    private val tvPage: Boolean = false,
) {
  var web: WebView? = null
  private var page: FrameLayout? = null
  private var full: View? = null                          // a video gone full screen
  private var fullDone: WebChromeClient.CustomViewCallback? = null
  private var address: TextView? = null
  private var typingAddress = false
  private val typed = StringBuilder()
  private var shift = false
  private val letterKeys = ArrayList<TextView>()
  private var pending: String? = null                      // a page asked for before the panel exists

  /** Shows or hides the keyboard panel (the activity owns the panels). */
  var onKeyboard: (Boolean) -> Unit = {}
  /** "Back to films" (the start page's tile, or the bar's button). */
  var onFilms: () -> Unit = {}
  /** A line for the viewer in the bar's message area. */
  var onMessage: (String) -> Unit = {}
  /** window.BuzzTV for our own page (CinemaBridge); added before the first page loads. */
  var bridge: Any? = null
  /** The address on screen, for the bridge to check (it's called off the UI thread). */
  @Volatile var shownUrl = ""
    private set

  // ------------------------------------------------------------------ the page
  fun pageView(ctx: Context): View {
    val w = Browser(ctx)
    w.settings.apply {
      javaScriptEnabled = true
      domStorageEnabled = true
      mediaPlaybackRequiresUserGesture = false
      setSupportMultipleWindows(false)                    // "open in new tab" opens here
      javaScriptCanOpenWindowsAutomatically = false
      if (!tvPage) {
        // The open web: a desktop browser (Prime Video and Netflix only play in one)
        useWideViewPort = true
        loadWithOverviewMode = true
        setSupportZoom(true)
        builtInZoomControls = true
        displayZoomControls = false
        userAgentString = desktopAgent(WebSettings.getDefaultUserAgent(ctx))
      }
      // Our page keeps the Quest's own user agent, so it lays out as in the browse panel
    }
    w.setBackgroundColor(Color.BLACK)
    CookieManager.getInstance().apply {
      setAcceptCookie(true)
      setAcceptThirdPartyCookies(w, true)                 // sign-in pages need them
    }
    w.webViewClient =
        object : WebViewClient() {
          override fun shouldOverrideUrlLoading(view: WebView, req: WebResourceRequest): Boolean {
            // Links that would open a phone app (intent:, market:, vnd.youtube:) go nowhere here
            val scheme = req.url.scheme ?: return true
            if (scheme == "buzz" && req.url.host == "films") view.post { onFilms() }
            return scheme != "http" && scheme != "https"
          }

          override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
            shownUrl = url
            if (!typingAddress) address?.text = url
          }

          override fun doUpdateVisitedHistory(view: WebView, url: String, isReload: Boolean) {
            shownUrl = url                                   // also in-page (history API) moves
          }

          override fun onPageFinished(view: WebView, url: String) {
            if (!typingAddress) address?.text = url
            if (tvPage) view.evaluateJavascript(TRACK_INPUT_JS, null)
            else if (url.startsWith("http")) prefs.edit().putString("webUrl", url).apply()
          }
        }
    w.webChromeClient =
        object : WebChromeClient() {
          override fun onShowCustomView(view: View, callback: CustomViewCallback) {
            exitFullScreen()
            full = view
            fullDone = callback
            page?.addView(view, FrameLayout.LayoutParams(-1, -1))
          }

          override fun onHideCustomView() {
            full?.let { page?.removeView(it) }
            full = null
            fullDone = null
          }

          override fun onPermissionRequest(request: PermissionRequest) {
            // Only the DRM key system that Prime Video and Netflix need; never camera or microphone
            val ok = request.resources.filter { it == PermissionRequest.RESOURCE_PROTECTED_MEDIA_ID }
            if (ok.isEmpty()) request.deny() else request.grant(ok.toTypedArray())
          }

          override fun onConsoleMessage(m: ConsoleMessage): Boolean {
            if (m.message().startsWith("buzz:")) Log.i(TAG, m.message())   // our own test pages only
            return true
          }
        }
    bridge?.let { w.addJavascriptInterface(it, "BuzzTV") }
    web = w
    page = FrameLayout(ctx).apply {
      setBackgroundColor(Color.BLACK)
      addView(w, FrameLayout.LayoutParams(-1, -1))
    }
    (pending ?: if (tvPage) null else (prefs.getString("webUrl", null) ?: HOME))?.let { open(it) }
    pending = null
    return page!!
  }

  /** Opens a web address, a bare site name (youtube.com) or, failing that, a Google search. */
  fun open(text: String) {
    val w = web ?: run { pending = text; return }
    exitFullScreen()
    val t = text.trim()
    val url = when {
      t == HOME -> HOME
      t.startsWith("http://") || t.startsWith("https://") -> t
      t.contains('.') && !t.contains(' ') -> "https://$t"
      else -> "https://www.google.com/search?q=" + android.net.Uri.encode(t)
    }
    // Set before loading: a page's script can call the bridge before onPageStarted arrives
    shownUrl = if (url == HOME) "https://buzztorrent.home/" else url
    if (url == HOME) w.loadDataWithBaseURL("https://buzztorrent.home/", homePage(), "text/html", "utf-8", null)
    else w.loadUrl(url)
    address?.text = url
  }

  fun back() {
    if (full != null) return exitFullScreen()
    web?.let { if (it.canGoBack()) it.goBack() }
  }

  private fun exitFullScreen() {
    fullDone?.onCustomViewHidden()
    full?.let { page?.removeView(it) }
    full = null
    fullDone = null
  }

  /** Scrolls the page under the middle of the screen, like a mouse wheel (+ = up). */
  fun scroll(ticks: Float) {
    val w = web ?: return
    val t = SystemClock.uptimeMillis()
    val props = MotionEvent.PointerProperties().apply { id = 0; toolType = MotionEvent.TOOL_TYPE_MOUSE }
    val at = MotionEvent.PointerCoords().apply {
      x = w.width / 2f
      y = w.height / 2f
      setAxisValue(MotionEvent.AXIS_VSCROLL, ticks)
    }
    val e = MotionEvent.obtain(t, t, MotionEvent.ACTION_SCROLL, 1, arrayOf(props), arrayOf(at), 0, 0, 1f, 1f, 0, 0,
        InputDevice.SOURCE_MOUSE, 0)
    w.dispatchGenericMotionEvent(e)
    e.recycle()
  }

  /** Leaving the browser: stop any video or sound, freeze the page. */
  fun pause() {
    web?.evaluateJavascript("document.querySelectorAll('video,audio').forEach(function(v){v.pause()})", null)
    web?.onPause()
  }

  fun resume() {
    web?.onResume()
  }

  fun destroy() {
    web?.destroy()
    web = null
  }

  // ------------------------------------------------------------------- the bar
  /** Back / forward / reload / home, the address, quick sites, then the activity's own [extras]. */
  fun bar(ctx: Context, extras: List<View>, message: TextView): View {
    val dp = ctx.resources.displayMetrics.density
    val root = LinearLayout(ctx).apply {
      orientation = LinearLayout.VERTICAL
      setPadding((20 * dp).toInt(), (14 * dp).toInt(), (20 * dp).toInt(), (14 * dp).toInt())
      background = GradientDrawable().apply {
        setColor(0xE6121620.toInt())
        cornerRadius = 24 * dp
      }
    }
    if (tvPage) {                                         // the page on the screen is the menu: one row
      val row = LinearLayout(ctx).apply { gravity = android.view.Gravity.CENTER }
      row.addView(button(ctx, "◀ Back") { back() })
      row.addView(button(ctx, "⌨ Type") { startTyping(address = false) })
      extras.forEach { row.addView(it) }
      root.addView(row)
      root.addView(message)
      return root
    }
    val nav = LinearLayout(ctx).apply { gravity = android.view.Gravity.CENTER_VERTICAL }
    nav.addView(button(ctx, "◀") { back() })
    nav.addView(button(ctx, "▶") { web?.let { if (it.canGoForward()) it.goForward() } })
    nav.addView(button(ctx, "⟳") { web?.reload() })
    nav.addView(button(ctx, "⌂") { open(HOME) })
    address = label(ctx, 15f, Color.WHITE).apply {
      text = "Web"
      setPadding((14 * dp).toInt(), (8 * dp).toInt(), (14 * dp).toInt(), (8 * dp).toInt())
      background = GradientDrawable().apply {
        setColor(0xFF0B0E15.toInt())
        setStroke((1 * dp).toInt(), 0xFF3A4358.toInt())
        cornerRadius = 20 * dp
      }
      setOnClickListener { startTyping(address = true) }
    }
    nav.addView(address, LinearLayout.LayoutParams(0, -2, 1f).apply { setMargins((6 * dp).toInt(), 0, (6 * dp).toInt(), 0) })
    nav.addView(button(ctx, "⌨ Type") { startTyping(address = false) })
    root.addView(nav)
    val sites = LinearLayout(ctx).apply { gravity = android.view.Gravity.CENTER; setPadding(0, (10 * dp).toInt(), 0, 0) }
    for ((name, url) in SITES.take(6)) sites.addView(button(ctx, name) { open(url) })
    root.addView(sites)
    val more = LinearLayout(ctx).apply { gravity = android.view.Gravity.CENTER; setPadding(0, (10 * dp).toInt(), 0, 0) }
    extras.forEach { more.addView(it) }
    root.addView(more)
    root.addView(label(ctx, 13f, 0xFF7D869B.toInt()).apply {
      text = "Point and pull the trigger to click, hold and drag to scroll · Right stick ▲▼: scroll, ◀▶: turn · B/Y: hide this bar"
      gravity = android.view.Gravity.CENTER
      setPadding(0, (8 * dp).toInt(), 0, 0)
    })
    root.addView(message)
    return root
  }

  // -------------------------------------------------------------- the keyboard
  /**
   * Types into the address (after you click it) or into the page: click a search box on the page
   * first, then ⌨ Type.
   */
  private fun startTyping(address: Boolean) {
    typingAddress = address
    typed.setLength(0)
    if (address) this.address?.text = "▌"
    else web?.requestFocus()
    if (tvPage) web?.evaluateJavascript(inputJs("el.focus();"), null)
    onKeyboard(true)
    onMessage(when {
      address -> "Type a web address or what to search for, then ↵"
      tvPage -> "Type what to search for, then ↵"
      else -> "Typing into the page: click its search box first"
    })
  }

  private fun stopTyping() {
    if (typingAddress) address?.text = web?.url ?: ""
    typingAddress = false
    onKeyboard(false)
  }

  fun keyboard(ctx: Context): View {
    val dp = ctx.resources.displayMetrics.density
    val root = LinearLayout(ctx).apply {
      orientation = LinearLayout.VERTICAL
      setPadding((14 * dp).toInt(), (12 * dp).toInt(), (14 * dp).toInt(), (12 * dp).toInt())
      background = GradientDrawable().apply {
        setColor(0xF0121620.toInt())
        cornerRadius = 24 * dp
      }
    }
    fun key(text: String, weight: Float = 1f, onClick: () -> Unit) =
        label(ctx, 20f, Color.WHITE).apply {
          this.text = text
          gravity = android.view.Gravity.CENTER
          setPadding(0, (10 * dp).toInt(), 0, (10 * dp).toInt())
          background = GradientDrawable().apply {
            setColor(0xFF2A3142.toInt())
            cornerRadius = 12 * dp
          }
          setOnClickListener { onClick() }
          layoutParams = LinearLayout.LayoutParams(0, -2, weight).apply {
            setMargins((3 * dp).toInt(), (3 * dp).toInt(), (3 * dp).toInt(), (3 * dp).toInt())
          }
        }
    for (row in KEY_ROWS) {
      val line = LinearLayout(ctx)
      for (k in row) {
        val v = when (k) {
          "⌫" -> key(k, 1.4f) { backspace() }
          "↵" -> key(k, 1.6f) { enter() }
          "⇧" -> key(k, 1.4f) { shift = !shift; relabel() }
          ".com" -> key(k, 1.6f) { type(".com") }
          else -> key(k) { type(if (shift) k.uppercase() else k); if (shift) { shift = false; relabel() } }.also {
            if (k.length == 1 && k[0].isLetter()) letterKeys += it
          }
        }
        line.addView(v)
      }
      root.addView(line)
    }
    val bottom = LinearLayout(ctx)
    bottom.addView(key("Space", 6f) { type(" ") })
    bottom.addView(key("Hide ⌨", 2f) { stopTyping() })
    root.addView(bottom)
    return root
  }

  private fun relabel() = letterKeys.forEach { it.text = if (shift) it.text.toString().uppercase() else it.text.toString().lowercase() }

  private fun type(s: String) {
    if (typingAddress) {
      typed.append(s)
      address?.text = "$typed▌"
      return
    }
    val w = web ?: return
    if (tvPage) return w.evaluateJavascript(inputJs("el.value+=${JSONObject.quote(s)};$INPUT_EVENT"), null)
    KEYS.getEvents(s.toCharArray())?.forEach { w.dispatchKeyEvent(it) }
  }

  private fun backspace() {
    if (typingAddress) {
      if (typed.isNotEmpty()) typed.setLength(typed.length - 1)
      address?.text = "$typed▌"
      return
    }
    if (tvPage) return web?.evaluateJavascript(inputJs("el.value=el.value.slice(0,-1);$INPUT_EVENT"), null) ?: Unit
    press(KeyEvent.KEYCODE_DEL)
  }

  private fun enter() {
    if (typingAddress) {
      val t = typed.toString()
      typingAddress = false
      onKeyboard(false)
      if (t.isNotBlank()) open(t) else address?.text = web?.url ?: ""
      return
    }
    if (tvPage) {                                         // search, and the keyboard goes away
      web?.evaluateJavascript(inputJs(
          "if(el.form&&el.form.requestSubmit)el.form.requestSubmit();" +
              "else el.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',keyCode:13,bubbles:true}));"), null)
      onKeyboard(false)
      return
    }
    press(KeyEvent.KEYCODE_ENTER)
  }

  private fun press(code: Int) {
    val w = web ?: return
    val t = SystemClock.uptimeMillis()
    w.dispatchKeyEvent(KeyEvent(t, t, KeyEvent.ACTION_DOWN, code, 0))
    w.dispatchKeyEvent(KeyEvent(t, t, KeyEvent.ACTION_UP, code, 0))
  }

  /** The page's WebView; when a text box on the page takes focus, the keyboard comes up. */
  private inner class Browser(ctx: Context) : WebView(ctx) {
    override fun onCreateInputConnection(outAttrs: EditorInfo): InputConnection? {
      val ic = super.onCreateInputConnection(outAttrs)
      if (ic != null && !typingAddress) post { onKeyboard(true) }
      return ic
    }
  }

  companion object {
    const val TAG = "BuzzWeb"
    const val HOME = "home"
    /** Our page: remembers the text box last clicked, for the keyboard to type into. */
    const val TRACK_INPUT_JS =
        "(function(){if(window.__buzzKb)return;window.__buzzKb=1;document.addEventListener('focusin',function(e){" +
            "var t=e.target;if(t&&(t.tagName=='INPUT'||t.tagName=='TEXTAREA'))window.__buzzIn=t;},true);})()"
    const val INPUT_EVENT = "el.dispatchEvent(new Event('input',{bubbles:true}));"
    /** [body] run on that text box (or the page's search box), as `el`. */
    fun inputJs(body: String) =
        "(function(){var el=window.__buzzIn||document.getElementById('q');if(!el)return;$body})()"
    val KEYS: KeyCharacterMap = KeyCharacterMap.load(KeyCharacterMap.VIRTUAL_KEYBOARD)
    val SITES = listOf(
        "YouTube" to "https://www.youtube.com",
        "Prime Video" to "https://www.primevideo.com",
        "Netflix" to "https://www.netflix.com",
        "Twitch" to "https://www.twitch.tv",
        "Vimeo" to "https://vimeo.com",
        "Google" to "https://www.google.com",
        "Disney+" to "https://www.disneyplus.com",
        "Internet Archive" to "https://archive.org/details/movies",
    )
    val KEY_ROWS = listOf(
        listOf("1", "2", "3", "4", "5", "6", "7", "8", "9", "0", "-", "⌫"),
        listOf("q", "w", "e", "r", "t", "y", "u", "i", "o", "p", "/", ":"),
        listOf("a", "s", "d", "f", "g", "h", "j", "k", "l", ".", "@", "↵"),
        listOf("⇧", "z", "x", "c", "v", "b", "n", "m", ",", "_", "?", ".com"),
    )

    /** The phone WebView's agent made to look like desktop Chrome, keeping its real version. */
    fun desktopAgent(phone: String): String {
      val chrome = Regex("Chrome/[\\d.]+").find(phone)?.value ?: "Chrome/124.0.0.0"
      return "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) $chrome Safari/537.36"
    }

    /** Start page: big tiles for the sites, easy to hit with the pointer on the big screen. */
    fun homePage(): String {
      val tiles = SITES.joinToString("") { (name, url) -> "<a href=\"$url\">$name</a>" } +
          "<a class=\"films\" href=\"buzz://films\">🎬 Back to films</a>"
      return """<!doctype html><html><head><meta name="viewport" content="width=device-width">
        <style>
        body{margin:0;background:#07090e;color:#e8ecf4;font-family:sans-serif;display:flex;flex-direction:column;
             align-items:center;justify-content:center;height:100vh}
        h1{font-weight:600;font-size:44px;margin:0 0 8px} p{color:#8b94a8;font-size:20px;margin:0 0 40px}
        .g{display:grid;grid-template-columns:repeat(4,260px);gap:22px}
        a{display:flex;align-items:center;justify-content:center;height:130px;border-radius:22px;background:#1a2030;
          color:#fff;text-decoration:none;font-size:28px;font-weight:600;border:2px solid #2c3550}
        a:active{background:#2c3550} .films{grid-column:span 4;height:90px;background:#3a2a10;border-color:#6b4c1a}
        </style></head><body><h1>Web</h1><p>Pick a site, or click the address bar on the bar in front of you to type one. B or Y shows or hides that bar.</p>
        <div class="g">$tiles</div></body></html>"""
    }
  }
}
