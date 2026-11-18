package com.buzzcaf.buzztorrent.vr

import android.app.PendingIntent
import android.content.Intent
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.GradientDrawable
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.util.Log
import android.view.Gravity
import android.view.View
import android.widget.LinearLayout
import android.widget.SeekBar
import android.widget.TextView
import androidx.core.net.toUri
import androidx.media3.common.Effect
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.common.VideoSize
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.Brightness
import androidx.media3.effect.Contrast
import androidx.media3.effect.HslAdjustment
import com.buzzcaf.buzztorrent.tv.CinemaBridge
import com.buzzcaf.buzztorrent.tv.PlayerActivity
import com.buzzcaf.buzztorrent.tv.Playlist
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Lut
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Query
import com.meta.spatial.core.SystemBase
import com.meta.spatial.core.SpatialFeature
import com.meta.spatial.core.Vector3
import com.meta.spatial.isdk.IsdkSystem
import com.meta.spatial.runtime.ButtonBits
import com.meta.spatial.runtime.ReferenceSpace
import com.meta.spatial.toolkit.AppSystemActivity
import com.meta.spatial.toolkit.Box
import com.meta.spatial.toolkit.Controller
import com.meta.spatial.toolkit.DpDisplayOptions
import com.meta.spatial.toolkit.MediaPanelRenderOptions
import com.meta.spatial.toolkit.MediaPanelSettings
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Hittable
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.MeshCacheSweepSystem
import com.meta.spatial.toolkit.MeshCollision
import com.meta.spatial.toolkit.Panel
import com.meta.spatial.toolkit.PanelRegistration
import com.meta.spatial.toolkit.PanelStyleOptions
import com.meta.spatial.toolkit.PixelDisplayOptions
import com.meta.spatial.toolkit.QuadShapeOptions
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.SceneObjectSystem
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.UIPanelSettings
import com.meta.spatial.toolkit.VideoSurfacePanelRegistration
import com.meta.spatial.toolkit.ViewPanelRegistration
import com.meta.spatial.toolkit.Visible
import com.meta.spatial.vr.InputSystem
import com.meta.spatial.vr.LocomotionSystem
import com.meta.spatial.vr.VRFeature
import java.util.Locale
import kotlin.math.abs
import kotlin.math.pow

/**
 * Watch: a big screen in a virtual room, playing what the browse panel sent.
 *
 * Playback follows the TV player: every copy of a video comes sharpest first, a Wi-Fi check
 * picks the best one the connection can carry, it steps down by itself if it keeps buffering,
 * subtitles come from the PC's cue lists, and the position is saved on the PC every 15 s.
 */
class CinemaActivity : AppSystemActivity() {
  private lateinit var player: ExoPlayer
  private var pl: Playlist? = null
  private var item = 0
  private var version = 0
  private var sub = -1
  private var manualQuality = false
  private var resumed = false
  private var ready = false
  private var readyAt = 0L
  private val stalls = ArrayList<Long>()
  private var ticks = 0

  private val prefs by lazy { getSharedPreferences("buzzvr", MODE_PRIVATE) }
  private var room: Room = GrandHall
  private var sizeMul = 1f                  // screen width × the room's own
  private var seat = Vector3(0f)              // where you are on the stage (x, z) and your seat lift (y)
  private var anchor = Pose()                 // the room's spot: where you stood, facing the screen
  private var seatDirty = false
  private var walk: Walk? = null              // where you can stand in this room
  private var floorTarget = 0f                // floor height under you
  private var floorNow = 0f                   // ...eased, so steps and tiers don't jolt
  private var headHeight = 1.2f               // your real eye height when you recentred
  private var stagePose = Pose()
  private var marker: Entity? = null          // teleport: where you'll land
  private val arcDots = ArrayList<Entity>()   // ...and the arc to it
  private var aimTarget: Vector3? = null
  private var controlsShown = true
  private val frame = ArrayList<Entity>()     // black masking hugging the picture at any size
  private var videoAspect = 16f / 9f
  private var sceneReady = false

  private lateinit var stage: Entity
  private lateinit var rig: Entity            // where you face after Recenter: carries the control bar
  private lateinit var kit: Kit
  private var sky: Entity? = null
  private var screen: Entity? = null
  private var controls: Entity? = null
  private var subtitles: Entity? = null
  private val started = SystemClock.elapsedRealtime()

  // Control panel views (created when the panel is)
  private var titleView: TextView? = null
  private var timeView: TextView? = null
  private var messageView: TextView? = null
  private var seekBar: SeekBar? = null
  private var playBtn: TextView? = null
  private var ccBtn: TextView? = null
  private var qualityBtn: TextView? = null
  private var nextBtn: TextView? = null
  private var likeBtn: TextView? = null
  private val roomBtns = ArrayList<TextView>()   // on the film bar and the web bar
  private val roomTiles = ArrayList<Pair<Room, View>>()   // the room picker's tiles
  private var roomPicker: Entity? = null
  private var settings: Entity? = null      // ⚙ Settings: lights, picture, sound, seats
  private var sound: SoundModes? = null
  private val sizeBtns = ArrayList<TextView>()
  private var webMessage: TextView? = null

  // 🎬 Movies: the BuzzTorrent page (search, torrents, shows, downloads) on the screen, with its
  // own panel and bar; ▶ Play there plays here. Only this page gets the bridge, never the open web.
  private val pageBridge: CinemaBridge by lazy {
    CinemaBridge(this, { moviesScreen.shownUrl }, { json -> ui.post { play(json) } }, { url -> ui.post { openWeb(url) } },
        { server -> ui.post { moviesScreen.open("$server/tv") } })
  }
  private val moviesScreen: WebScreen by lazy {
    WebScreen(prefs, { c, t, f -> button(c, t, f) }, { c, s, col -> label(c, s, col) }, tvPage = true).apply {
      bridge = pageBridge
      onKeyboard = { shown ->
        if (shown) showRoomPicker(false)
        moviesKeys?.setComponent(Visible(shown && moviesMode && controlsShown))
      }
      onMessage = { flash(it) }
      onFilms = { closeMovies() }
    }
  }
  private var moviesMode = false
  private var moviesWhenReady = false
  private var moviesPanel: Entity? = null
  private var moviesBar: Entity? = null
  private var moviesKeys: Entity? = null
  private var moviesMessage: TextView? = null

  // 🌐 Web: a browser on the screen (YouTube, Prime Video, any site): made the first time it's opened
  private val webScreen: WebScreen by lazy {
    WebScreen(prefs, { c, t, f -> button(c, t, f) }, { c, s, col -> label(c, s, col) }).apply {
      onKeyboard = { shown ->
        if (shown) showRoomPicker(false)
        keys?.setComponent(Visible(shown && webMode && controlsShown))
      }
      onMessage = { flash(it) }
      onFilms = { closeWeb() }
    }
  }
  private var webMode = false
  private var webPanel: Entity? = null
  private var webBar: Entity? = null
  private var keys: Entity? = null
  private var subtitleView: TextView? = null
  private var dragging = false

  // Screen light: the film's average colour, smoothed, lights the room (Kit.glow)
  private var effectsOn = true
  private val glowTarget = floatArrayOf(IDLE_GLOW, IDLE_GLOW, IDLE_GLOW)
  private val glowNow = floatArrayOf(0f, 0f, 0f)
  private var samples = 0                     // colours measured (one in 50 is logged)
  private val glowStep =
      object : Runnable {
        override fun run() {
          if (sceneReady) {
            testGlow?.let { glowTarget.fill(it) }
            for (i in 0..2) {
              // About half a second to follow the film (a little quicker brightening): the colour
              // is measured ~5 times a second, and quicker than this the dimmed hall flickered
              val k = if (glowTarget[i] > glowNow[i]) 0.08f else 0.06f
              glowNow[i] += (glowTarget[i] - glowNow[i]) * k
            }
            kit.glow(glowNow[0], glowNow[1], glowNow[2])
            houseLights()
          }
          ui.postDelayed(this, 40)
        }
      }

  private val ui = Handler(Looper.getMainLooper())
  private val tick =
      object : Runnable {
        override fun run() {
          updateControls()
          drawSubtitle()
          if (sceneReady) room.tick((SystemClock.elapsedRealtime() - started) / 1000f)
          // A hidden bar (B / Y) comes back by itself when the film is paused or over
          if (sceneReady && !controlsShown && !webMode && !moviesMode &&
              (!player.playWhenReady || player.playbackState == Player.STATE_ENDED)) toggleControls()
          if (++ticks % 75 == 0 && player.isPlaying) saveProgress(false) // every 15 s
          if (seatDirty && ticks % 5 == 0) saveSeat()
          ui.postDelayed(this, 200)
        }
      }
  private val clearMessage = Runnable { messageView?.text = ""; webMessage?.text = "" }

  override fun registerFeatures(): List<SpatialFeature> = listOf(VRFeature(this))

  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    // "room" extra (adb shell am start ... --es room space) opens a room directly, for testing
    val wanted = intent?.getStringExtra("room") ?: prefs.getString("room", GrandHall.id)
    room = ROOMS.firstOrNull { it.id == wanted } ?: GrandHall
    sizeMul = prefs.getFloat("sizeMul", 1f).coerceIn(MIN_SIZE, MAX_SIZE)
    seat = Vector3(prefs.getFloat("seatX", 0f), prefs.getFloat("seatY", 0f), prefs.getFloat("seatZ", 0f))
    // FFmpeg renderers (when bundled) take over only what the Quest can't decode, e.g. AC3/DTS
    // sound; ordinary AAC stays on the Quest's own decoder. CinemaRenderers: sound with no window.
    @androidx.annotation.OptIn(UnstableApi::class)
    val renderers =
        CinemaRenderers(applicationContext)
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)
    CinemaRenderers.clearDefaultWindow()
    player = ExoPlayer.Builder(applicationContext, renderers).build()
    logAudio()
    sound = SoundModes(player.audioSessionId).also { it.apply(prefs.getInt("sound", SoundModes.STANDARD)) }
    enableScreenLight()
    player.addListener(
        object : Player.Listener {
          override fun onPlaybackStateChanged(state: Int) {
            when (state) {
              Player.STATE_BUFFERING -> if (ready) { show("Buffering…"); stalled() }
              Player.STATE_READY -> {
                if (!ready) { ready = true; readyAt = SystemClock.elapsedRealtime() }
                clearMessageSoon(0)
              }
              Player.STATE_ENDED -> {
                saveProgress(true)
                val p = pl ?: return
                if (item + 1 < p.items.size) start(item + 1) else close()
              }
              else -> {}
            }
          }

          override fun onPlayerError(error: PlaybackException) {
            val it = pl?.items?.get(item) ?: return
            val pos = player.currentPosition
            if (effectsOn && error.errorCode in FRAME_ERRORS) {
              // The colour sampler couldn't run on this video: play it without room lighting
              effectsOn = false
              disableScreenLight()
              flash("Room lighting is off for this video")
              play(item, version, pos)
              return
            }
            if (version + 1 < it.urls.size) {
              flash("${it.label(version)} can't play here. Trying ${it.label(version + 1)}…")
              play(item, version + 1, pos)
            } else {
              show("This video can't play on the Quest. Close and choose another copy.")
            }
          }

          override fun onVideoSizeChanged(videoSize: VideoSize) {
            if (videoSize.width > 0 && videoSize.height > 0) {
              videoAspect = videoSize.width * videoSize.pixelWidthHeightRatio / videoSize.height
              layoutScreen()
            }
          }
        })
    load(intent)
    ui.post(tick)
    ui.post(glowStep)
  }

  /** Which audio decoder and format each film gets, and any audio failure, in logcat. */
  @androidx.annotation.OptIn(UnstableApi::class)
  private fun logAudio() {
    player.addAnalyticsListener(
        object : androidx.media3.exoplayer.analytics.AnalyticsListener {
          override fun onAudioDecoderInitialized(
              t: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime, decoderName: String, initMs: Long, durationMs: Long,
          ) = Log.i(TAG, "audio decoder: $decoderName").let {}

          override fun onAudioInputFormatChanged(
              t: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime, format: androidx.media3.common.Format,
              reuse: androidx.media3.exoplayer.DecoderReuseEvaluation?,
          ) = Log.i(TAG, "audio format: ${format.sampleMimeType} ${format.channelCount} ch ${format.sampleRate} Hz").let {}

          override fun onAudioSinkError(t: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime, e: Exception) =
              Log.w(TAG, "audio sink error", e).let {}

          override fun onAudioCodecError(t: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime, e: Exception) =
              Log.w(TAG, "audio codec error", e).let {}

          override fun onAudioUnderrun(
              t: androidx.media3.exoplayer.analytics.AnalyticsListener.EventTime, bufferSize: Int, bufferSizeMs: Long, elapsedSinceLastFeedMs: Long,
          ) = Log.w(TAG, "audio underrun").let {}
        })
  }

  @androidx.annotation.OptIn(UnstableApi::class)
  private fun disableScreenLight() {
    player.setVideoEffects(emptyList())
  }

  /** The picture settings (⚙ Settings), applied to the film before the sampler sees it. */
  @androidx.annotation.OptIn(UnstableApi::class)
  private fun pictureEffects(): List<Effect> = buildList {
    val c = prefs.getInt("contrast", 0)
    val b = prefs.getInt("brightness", 0)
    val s = prefs.getInt("colour", 0)
    if (c != 0) add(Contrast(c * CONTRAST_STEP))
    if (b != 0) add(Brightness(b * BRIGHTNESS_STEP))
    if (s != 0) add(HslAdjustment.Builder().adjustSaturation(s * COLOUR_STEP).build())
  }

  @androidx.annotation.OptIn(UnstableApi::class)
  private fun enableScreenLight() {
    player.setVideoEffects(
        pictureEffects() +
        listOf(
            ScreenSampler { r, g, b ->
              // a typical frame averages ~0.25: lift it so the room reacts visibly
              glowTarget[0] = r * GLOW_GAIN
              glowTarget[1] = g * GLOW_GAIN
              glowTarget[2] = b * GLOW_GAIN
              if (samples++ % 50 == 0) {
                Log.i(TAG, String.format(Locale.ROOT, "screen colour %.3f %.3f %.3f, light %.4f", r, g, b, glowNow[1]))
              }
            }))
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    setIntent(intent)
    saveProgress(false)
    load(intent)
  }

  private fun load(intent: Intent?) {
    // Test hooks: adb shell am start -n com.buzzcaf.buzztorrent.vr/.CinemaActivity --es room grand
    // --ef lights 0.1 --ef glow 0.6 (house lights and screen light held there; lights 1, glow -1 or a film lets go)
    intent?.getStringExtra("room")?.let { id -> ROOMS.find { it.id == id }?.let { if (sceneReady) applyRoom(it) else room = it } }
    if (intent?.hasExtra("lights") == true) testLights = intent.getFloatExtra("lights", 1f).takeIf { it < 1f }
    if (intent?.hasExtra("glow") == true) testGlow = intent.getFloatExtra("glow", -1f).takeIf { it >= 0f }
    val json = intent?.getStringExtra(PlayerActivity.EXTRA)
    if (json == null) {                       // "🥽 VR rooms": look around, keep whatever is playing
      if (pl == null && testLights == null) {
        show("🎬 Movies: search films and shows to play here. 🌐 Web: YouTube and other sites. Room ▾ changes the room.")
        if (sceneReady) openMovies() else moviesWhenReady = true   // nothing to watch yet: the search page
      }
      return
    }
    play(json)
  }

  private var testLights: Float? = null
  private var testGlow: Float? = null

  /** Plays a payload from the browse panel or the 🎬 Movies page. */
  private fun play(json: String) {
    testLights = null
    testGlow = null
    pl = Playlist.parse(this, json)
    val p = pl
    if (p == null) {
      show("This video can't play here. Press ✕ Close and choose another copy.")
      return
    }
    manualQuality = false
    closeWeb()                                // a film picked in the browse panel or 🎬 Movies takes the screen back
    closeMovies()
    start(p.index)
  }

  // ---------------------------------------------------------------- the scene
  override fun onSceneReady() {
    super.onSceneReady()
    scene.setReferenceSpace(ReferenceSpace.LOCAL_FLOOR)
    systemManager.findSystem<LocomotionSystem>().enableLocomotion(false)
    stage = Entity.create(listOf(Transform(Pose())))
    rig = Entity.create(listOf(Transform(Pose())))
    kit = Kit(stage) { e -> systemManager.findSystem<SceneObjectSystem>().getSceneObject(e) }
    kit.glowOn = prefs.getBoolean("glowOn", true)
    systemManager.registerSystem(StickSystem())
    // The pointer reaches 5 m out of the box; the screen (and a web page on it) is 15 to 35 m away
    // (the Interaction SDK's pointer, which VRFeature uses; the simple controller's if that's in use)
    runCatching { systemManager.findSystem<IsdkSystem>().setScenePointerDistance(POINTER_REACH) }
    runCatching { systemManager.findSystem<InputSystem>().maxPointerDistance = POINTER_REACH }
    // The film can't be clicked: keep it from catching the pointer meant for the web page there
    screen = Entity.create(listOf(Panel(R.id.cinema_screen), Transform(Pose()), TransformParent(stage),
        Hittable(MeshCollision.NoCollision)))
    subtitles = Entity.create(listOf(Panel(R.id.cinema_subtitles), Transform(Pose()), TransformParent(stage)))
    controls = Entity.create(listOf(Panel(R.id.cinema_controls), Transform(Pose()), TransformParent(rig)))
    roomPicker = Entity.create(listOf(Panel(R.id.cinema_rooms), Transform(Pose()), TransformParent(rig), Visible(false)))
    settings = Entity.create(listOf(Panel(R.id.cinema_settings), Transform(Pose()), TransformParent(rig), Visible(false)))
    marker = glowBall(Vector3(0.62f, 0.03f, 0.62f), Color4(0.35f, 0.85f, 1f, 1f))
    repeat(ARC_DOTS) { arcDots += glowBall(Vector3(0.05f), Color4(0.6f, 0.9f, 1f, 1f)) }
    repeat(4) {
      frame +=
          Entity.create(
              listOf(
                  Mesh("mesh://box".toUri(), hittable = MeshCollision.NoCollision),
                  Box(Vector3(-0.5f), Vector3(0.5f)),
                  maskMaterial(1f),
                  Transform(Pose()),
                  TransformParent(stage),
              ))
    }
    sceneReady = true
    applyRoom(room, keepSeat = true)
    // Face the screen the way the viewer is looking once the headset reports where that is
    ui.postDelayed({ recenter() }, 500)
    // "web" extra (adb shell am start ... --es web https://...) opens the browser, for testing
    intent?.getStringExtra("web")?.let { openWeb(it) }
    if (moviesWhenReady) {
      moviesWhenReady = false
      if (pl == null) openMovies()
    }
  }

  // ---------------------------------------------------------------- 🎬 Movies
  /** The BuzzTorrent page on the screen in place of the film (which pauses): search and play. */
  private fun openMovies() {
    if (!sceneReady) return
    val server = pageBridge.server()
    if (server == null) {
      show("Pair with your PC first: ✕ Close, then set it up in the BuzzTorrent panel.")
      return
    }
    hideWeb()
    if (moviesPanel == null) {
      moviesPanel = Entity.create(listOf(Panel(R.id.cinema_movies), Transform(Pose()), TransformParent(stage)))
      moviesBar = Entity.create(listOf(Panel(R.id.cinema_moviesbar), Transform(Pose()), TransformParent(rig)))
      moviesKeys = Entity.create(listOf(Panel(R.id.cinema_movieskeys), Transform(Pose()), TransformParent(rig), Visible(false)))
    }
    if (!moviesScreen.shownUrl.startsWith("$server/")) moviesScreen.open("$server/tv")
    moviesMode = true
    if (player.isPlaying) { player.pause(); saveProgress(false) }
    moviesScreen.resume()
    moviesPanel?.setComponent(Visible(true))
    screen?.setComponent(Visible(false))
    showSubtitles(false)
    controls?.setComponent(Visible(false))
    showSettings(false)
    moviesBar?.setComponent(Visible(controlsShown))
    glowTarget.fill(MOVIES_GLOW)                    // a dark page: the room stays as it is
    layoutScreen()
  }

  private fun hideMovies() {
    if (!moviesMode) return
    moviesMode = false
    moviesScreen.pause()
    moviesPanel?.setComponent(Visible(false))
    moviesBar?.setComponent(Visible(false))
    moviesKeys?.setComponent(Visible(false))
  }

  /** Back to the film. */
  private fun closeMovies() {
    if (!moviesMode) return
    hideMovies()
    showFilm()
  }

  // ------------------------------------------------------------------- the web
  /** Swaps the film for the web browser on the same screen (the film pauses). */
  private fun openWeb(url: String? = null) {
    if (!sceneReady) return
    hideMovies()
    if (webPanel == null) {
      webPanel = Entity.create(listOf(Panel(R.id.cinema_web), Transform(Pose()), TransformParent(stage)))
      webBar = Entity.create(listOf(Panel(R.id.cinema_webbar), Transform(Pose()), TransformParent(rig)))
      keys = Entity.create(listOf(Panel(R.id.cinema_keys), Transform(Pose()), TransformParent(rig), Visible(false)))
    }
    webMode = true
    if (player.isPlaying) { player.pause(); saveProgress(false) }
    webScreen.resume()
    url?.let { webScreen.open(it) }
    webPanel?.setComponent(Visible(true))
    screen?.setComponent(Visible(false))
    showSubtitles(false)
    controls?.setComponent(Visible(false))
    showSettings(false)
    webBar?.setComponent(Visible(controlsShown))
    // A web page can't be read for its colours (and DRM video mustn't be): light the room evenly
    glowTarget.fill(WEB_GLOW)
    layoutScreen()
  }

  private fun hideWeb() {
    if (!webMode) return
    webMode = false
    webScreen.pause()
    webPanel?.setComponent(Visible(false))
    webBar?.setComponent(Visible(false))
    keys?.setComponent(Visible(false))
  }

  /** Back to the film. */
  private fun closeWeb() {
    if (!webMode) return
    hideWeb()
    showFilm()
  }

  private fun showFilm() {
    screen?.setComponent(Visible(true))                 // subtitles come back with their next line
    controls?.setComponent(Visible(controlsShown))
    glowTarget.fill(IDLE_GLOW)
    layoutScreen()
  }

  /** Turns the whole room so the screen is straight ahead of where the viewer looks now. */
  private fun recenter() {
    if (!sceneReady) return
    val head = scene.getViewerPose()
    anchor = Pose(Vector3(head.t.x, 0f, head.t.z), head.q.removePitchAndRoll())
    headHeight = head.t.y.coerceIn(0.8f, 1.9f)
    rig.setComponent(Transform(anchor))
    rigFollowing = false
    placeStage()
    layoutScreen()
  }

  private var rigFollowing = false            // the control bar is gliding back in front of you

  private fun finite(p: Pose) =
      floatArrayOf(p.t.x, p.t.y, p.t.z, p.q.x, p.q.y, p.q.z, p.q.w).all { it.isFinite() }

  private fun yawOf(v: Vector3) = Math.toDegrees(kotlin.math.atan2(v.x, v.z).toDouble()).toFloat()

  /**
   * Keeps the control bar where you can reach it: once you look more than FOLLOW_ANGLE away from
   * it, or step FOLLOW_DIST from where it was put, it glides back in front of you. It stays still
   * while you use it, so it never moves out from under the pointer.
   */
  private fun followHead(dt: Float) {
    val head = scene.getViewerPose()
    // No tracking (headset off, "finding position"): a zero or NaN pose must never reach the bar
    if (!finite(head) || head.q.dot(head.q) < 0.5f) return
    val goalQ = head.q.removePitchAndRoll()
    if (!finite(Pose(head.t, goalQ))) return
    val cur = rig.tryGetComponent<Transform>()?.transform ?: return
    if (!finite(cur)) {                                   // a bad pose got in somehow: put it right
      rig.setComponent(Transform(Pose(Vector3(head.t.x, 0f, head.t.z), goalQ)))
      rigFollowing = false
      return
    }
    var dYaw = (yawOf(goalQ * Vector3(0f, 0f, 1f)) - yawOf(cur.q * Vector3(0f, 0f, 1f))) % 360f
    if (dYaw > 180f) dYaw -= 360f else if (dYaw < -180f) dYaw += 360f
    val goalT = Vector3(head.t.x, 0f, head.t.z)
    val dist = (goalT - cur.t).length()
    if (!rigFollowing && (abs(dYaw) > FOLLOW_ANGLE || dist > FOLLOW_DIST)) rigFollowing = true
    if (!rigFollowing) return
    val k = minOf(1f, dt * 5f)
    rig.setComponent(Transform(Pose(cur.t + (goalT - cur.t) * k, cur.q.slerp(goalQ, k))))
    if (abs(dYaw) < 1.5f && dist < 0.03f) rigFollowing = false
  }

  /** Moving your seat moves the room the other way; the control bar stays with you. */
  private fun placeStage() {
    if (!sceneReady) return
    stagePose = Pose(anchor.t + anchor.q * (-Vector3(seat.x, floorNow + seat.y, seat.z)), anchor.q)
    stage.setComponent(Transform(stagePose))
  }

  /** Your head's forward and right on the stage floor (the way the left stick walks). */
  private fun headAxes(): Pair<Vector3, Vector3> {
    val head = scene.getViewerPose()
    val toStage = stagePose.q.inverse()
    fun flat(v: Vector3) = Vector3(v.x, 0f, v.z).let { if (it.length() < 1e-3f) Vector3(0f, 0f, 1f) else it.normalize() }
    return flat(toStage * (head.q * Vector3(0f, 0f, 1f))) to flat(toStage * head.right())
  }

  /**
   * Snap turn: the room swings round you by [degrees] (positive = you turn right), pivoting
   * where you actually are, so the walk map keeps following you.
   */
  private fun turn(degrees: Float) {
    val head = scene.getViewerPose()
    val here = stagePose.inverse() * head.t
    if (standable(here.x, here.z) != null) seat = Vector3(here.x, seat.y, here.z)
    anchor = Pose(Vector3(head.t.x, 0f, head.t.z), anchor.q)
    val fwd = (head.q * Vector3(0f, 0f, 1f)).let { Vector3(it.x, 0f, it.z).normalize() }
    val right = head.right().let { Vector3(it.x, 0f, it.z).normalize() }
    val a = Math.toRadians(degrees.toDouble())
    val target = (fwd * Math.cos(a).toFloat() + right * Math.sin(a).toFloat()).normalize()
    anchor = Pose(anchor.t, Quaternion.fromTwoVectors(target, fwd) * anchor.q)
    floorTarget = standable(seat.x, seat.z) ?: floorTarget
    seatDirty = true
    placeStage()
  }

  /** Floor height where you could stand at (x, z) on the stage, or null (wall, ledge, the screen). */
  private fun standable(x: Float, z: Float): Float? {
    if (z > room.screen.distance - 1.2f) return null
    val w = walk ?: return if (x in -25f..25f && z in -25f..25f) 0f else null
    return w.floor(x, z)
  }

  /** Walks by (dx, dz), sliding along walls; dy lifts or lowers your seat. */
  private fun moveSeat(dx: Float, dy: Float, dz: Float) {
    val here = standable(seat.x, seat.z) ?: floorTarget
    fun ok(x: Float, z: Float) = standable(x, z)?.let { abs(it - here) <= MAX_STEP } == true
    var x = seat.x
    var z = seat.z
    when {
      ok(x + dx, z + dz) -> { x += dx; z += dz }
      ok(x + dx, z) -> x += dx
      ok(x, z + dz) -> z += dz
    }
    seat = Vector3(x, (seat.y + dy).coerceIn(-1f, 2f), z)
    floorTarget = standable(x, z) ?: floorTarget
    seatDirty = true
    placeStage()
  }

  private fun glowBall(scale: Vector3, color: Color4): Entity =
      Entity.create(
          listOf(
              Mesh("mesh://sphere".toUri(), hittable = MeshCollision.NoCollision),
              Sphere(0.5f),
              Material().apply {
                baseColor = color
                unlit = true
              },
              Transform(Pose()),
              Scale(scale),
              TransformParent(stage),
              Visible(false),
          ))

  /**
   * Teleport, while A or X is held: throws an arc from that controller and shows where it lands
   * (somewhere you could stand); letting go takes you there.
   */
  private fun aim(hand: Pose) {
    val toStage = stagePose.inverse()
    var p = toStage * hand.t
    var v = (stagePose.q.inverse() * hand.forward()) * ARC_SPEED
    var hit: Vector3? = null
    val path = ArrayList<Vector3>()
    for (step in 0 until 200) {
      val next = p + v * ARC_STEP
      v = Vector3(v.x, v.y - 9.8f * ARC_STEP, v.z)
      if (step % 4 == 3) path += next
      val f = standable(next.x, next.z)
      if (f != null && next.y <= f) {
        hit = Vector3(next.x, f, next.z)
        break
      }
      if (next.y < floorNow - 10f) break
      p = next
    }
    aimTarget = hit
    marker?.let { m ->
      m.setComponent(Visible(hit != null))
      if (hit != null) m.setComponent(Transform(Pose(hit + Vector3(0f, 0.02f, 0f))))
    }
    arcDots.forEachIndexed { i, d ->
      val at = path.getOrNull(i)
      d.setComponent(Visible(at != null))
      if (at != null) d.setComponent(Transform(Pose(at)))
    }
  }

  private fun jump() {
    marker?.setComponent(Visible(false))
    arcDots.forEach { it.setComponent(Visible(false)) }
    val t = aimTarget ?: return
    aimTarget = null
    seat = Vector3(t.x, seat.y, t.z)
    floorTarget = t.y
    floorNow = t.y
    seatDirty = true
    placeStage()
  }

  private fun toggleControls() {
    controlsShown = !controlsShown
    if (!controlsShown) { showRoomPicker(false); showSettings(false) }
    if (moviesMode) {
      moviesBar?.setComponent(Visible(controlsShown))
      if (!controlsShown) moviesKeys?.setComponent(Visible(false))
    } else if (webMode) {
      webBar?.setComponent(Visible(controlsShown))
      if (!controlsShown) keys?.setComponent(Visible(false))
    } else {
      controls?.setComponent(Visible(controlsShown))
    }
  }

  private fun resizeScreen(factor: Float) {
    sizeMul = (sizeMul * factor).coerceIn(MIN_SIZE, MAX_SIZE)
    seatDirty = true
    layoutScreen()
  }

  private fun saveSeat() {
    seatDirty = false
    prefs.edit().putFloat("sizeMul", sizeMul).putFloat("seatX", seat.x).putFloat("seatY", seat.y)
        .putFloat("seatZ", seat.z).apply()
  }

  /**
   * Controllers, every frame: left stick walks (not through walls; up and down steps), hold A or
   * X to aim a teleport and let go to jump there, right stick up/down makes the screen bigger or
   * smaller, right stick left/right lowers or raises your seat, B or Y hides the control bar.
   */
  private inner class StickSystem : SystemBase() {
    private var last = System.nanoTime()
    private var aiming = false
    private var before = 0                    // last frame's buttons, to catch presses
    private var rightMode = 0                 // the right stick's job until it's let go: STICK_TURN / STICK_SIZE
    private var rightHeld = 0f

    override fun execute() {
      val now = System.nanoTime()
      val dt = ((now - last) / 1e9f).coerceIn(0f, 0.1f)
      last = now
      if (!sceneReady) return
      if (abs(floorTarget - floorNow) > 0.001f) {
        floorNow += (floorTarget - floorNow) * minOf(1f, dt * 10f)
        placeStage()
      }
      var bits = 0
      var hand: Pose? = null
      for (e in Query.where { has(Controller.id) }.eval()) {
        val c = e.getComponent<Controller>()
        if (!c.isActive) continue
        bits = bits or c.buttonState
        if (c.buttonState and (ButtonBits.ButtonA or ButtonBits.ButtonX) != 0) {
          hand = e.tryGetComponent<Transform>()?.transform
        }
      }
      val pressed = bits and before.inv()
      before = bits
      if (pressed and (ButtonBits.ButtonB or ButtonBits.ButtonY) != 0) toggleControls()
      followHead(dt)
      val eye = stagePose.inverse() * scene.getViewerPose().t
      kit.glowPivot(eye)
      eyeNow()?.let { e -> if (nearEye?.let { (it - e).length() < 0.01f } != true) placeNear(e) }
      kit.animate((SystemClock.elapsedRealtime() - started) / 1000f, eye)
      // Right stick: one job per push. Sideways at any point = turning, and up/down is ignored
      // until you let go (a sideways flick that drifts up must not resize the screen); straight
      // up/down for a moment = screen size.
      val stick = bits and RIGHT_STICK
      if (stick == 0) {
        rightMode = 0
        rightHeld = 0f
      } else if (rightMode != STICK_TURN) {
        rightHeld += dt
        if (stick and SIDEWAYS != 0) rightMode = STICK_TURN
        else if (rightHeld > 0.15f) rightMode = STICK_SIZE
      }
      if (rightMode == STICK_TURN) {
        if (pressed and ButtonBits.ButtonThumbRR != 0) turn(SNAP_TURN)
        else if (pressed and ButtonBits.ButtonThumbRL != 0) turn(-SNAP_TURN)
      }
      val aimFrom = hand
      if (aimFrom != null) {
        aim(aimFrom)
        aiming = true
      } else if (aiming) {
        aiming = false
        jump()
      }
      if (bits == 0) return
      fun on(b: Int) = bits and b == b
      val step = 2.2f * dt
      var ahead = 0f
      var side = 0f
      if (on(ButtonBits.ButtonThumbLU)) ahead += step
      if (on(ButtonBits.ButtonThumbLD)) ahead -= step
      if (on(ButtonBits.ButtonThumbLR)) side += step
      if (on(ButtonBits.ButtonThumbLL)) side -= step
      if (ahead != 0f || side != 0f) {
        val (fwd, right) = headAxes()
        moveSeat(fwd.x * ahead + right.x * side, 0f, fwd.z * ahead + right.z * side)
      }
      if (rightMode == STICK_SIZE && (webMode || moviesMode)) {   // on a web page ▲▼ scrolls it instead
        val page = if (moviesMode) moviesScreen else webScreen
        if (on(ButtonBits.ButtonThumbRU)) ui.post { page.scroll(WEB_SCROLL * dt) }
        if (on(ButtonBits.ButtonThumbRD)) ui.post { page.scroll(-WEB_SCROLL * dt) }
      } else if (rightMode == STICK_SIZE) {
        if (on(ButtonBits.ButtonThumbRU)) resizeScreen(1f + 0.9f * dt)
        if (on(ButtonBits.ButtonThumbRD)) resizeScreen(1f / (1f + 0.9f * dt))
      }
    }
  }

  private fun applyRoom(r: Room, keepSeat: Boolean = false) {
    room = r
    prefs.edit().putString("room", r.id).apply()
    roomBtns.forEach { it.text = "Room: ${r.label}  ▾" }
    roomTiles.forEach { (tr, v) -> v.background = tileBackground(v.context, tr === r) }
    showRoomPicker(false)
    if (!sceneReady) return
    // A new room starts you in its best seat; stepping somewhere you can't stand does too
    walk = Walk.load(this, r.id)
    if (!keepSeat || standable(seat.x, seat.z) == null) seat = Vector3(0f, seat.y, 0f)
    floorTarget = standable(seat.x, seat.z) ?: 0f
    floorNow = floorTarget
    seatDirty = true
    kit.clear()
    sweepModels()
    // Build the new room once the old one's models have left memory: two big halls at once ran
    // the Quest out of memory (the IMAX hall after the Grand one was killed by Android)
    val gen = ++roomGen
    ui.postDelayed({
      if (gen == roomGen && sceneReady) {
        r.build(kit)
        layoutScreen()
      }
    }, ROOM_SWAP_MS)
    scene.enablePassthrough(r.passthrough)
    lightsNow = 1f
    lastLut.fill(-1f)
    fillSeats()
    scene.setLightingEnvironment(
        ambientColor = r.ambient,
        sunColor = Vector3(if (r === Space) 2.5f else 0.6f),
        sunDirection = -Vector3(1f, 2f, -1.5f),
        environmentIntensity = 0.15f,
    )
    sky?.destroy()
    sky = null
    if (r.sky != 0) {
      sky =
          Entity.create(
              listOf(
                  Mesh("mesh://skybox".toUri(), hittable = MeshCollision.NoCollision),
                  Material().apply {
                    baseTextureAndroidResourceId = r.sky
                    unlit = true
                  },
                  Transform(Pose()),
              ))
    }
    layoutScreen()
    placeStage()
  }

  private var roomGen = 0

  /** Drops the last room's models from the mesh cache, so the next room loads into free memory. */
  private fun sweepModels() {
    runCatching {
      val sweeper = systemManager.findSystem<MeshCacheSweepSystem>()
      val tokens = sweeper.meshManager.cachedMeshTokens().filter { "models/" in it }.toSet()
      if (tokens.isNotEmpty()) sweeper.scheduleSweep(tokens, 2)
    }.onFailure { Log.w(TAG, "mesh cache sweep failed: $it") }
  }

  // ---------------------------------------------------------------- house lights
  // The lights go down while the film plays and back up when it pauses. A virtual room's baked
  // surfaces darken (Kit.houseLights) and its screen-glow layer, which doesn't dim, lights it.
  // My room: passthrough can't be drawn on, but its colours can be remapped (a 16³ lookup table),
  // and the film's own colour spills onto your room the way a projector lights a dark living room.
  private var lightsNow = 1f
  private val lastLut = floatArrayOf(-1f, -1f, -1f)
  private var lightsBtn: TextView? = null
  // (label, My room's level, a virtual hall's level). A hall's level scales its light in linear
  // terms, which the eye sees as about level^(1/2.2): measured, 0.08 looked like a third of the lit
  // hall and 0.2 like half (hardly dimmed); 0.04 (a quarter) was still too bright to watch in.
  // 0.012 looks like an eighth, 0.004 like a twelfth: a dark hall lit by the film.
  // The ⚙ Settings level is how bright the room looks: Dark was 8 % (0.004), Dim 13 % (0.012).
  // My room's passthrough was 0.15 at Dark and 0.4 at Dim, and goes on up to 1.
  private var lightsPct = -1
  private var lastLightsTarget = -1f

  private fun lightsPct(): Int {
    if (lightsPct < 0) {
      if (!prefs.contains("lightsPct")) {       // the old Dim / Dark / On button's choice
        prefs.edit().putInt("lightsPct", intArrayOf(13, 8, 100).getOrElse(prefs.getInt("lights", 0)) { 13 }).apply()
      }
      lightsPct = prefs.getInt("lightsPct", 13).coerceIn(0, 100)
    }
    return lightsPct
  }

  private fun hallLevel(pct: Int) = (pct / 100f).pow(2.2f)

  private fun passthroughLevel(pct: Int): Float {
    val p = pct / 100f
    return when {
      p <= 0.08f -> p / 0.08f * 0.15f
      p <= 0.13f -> 0.15f + (p - 0.08f) / 0.05f * 0.25f
      else -> 0.4f + (p - 0.13f) / 0.87f * 0.6f
    }
  }

  /** Called with the glow step (25 times a second): fades the lights, re-maps passthrough when it changed. */
  private fun houseLights() {
    val pct = lightsPct()
    val target = testLights ?: if (!player.isPlaying || webMode || moviesMode) 1f else if (room.passthrough) passthroughLevel(pct) else hallLevel(pct)
    if (target != lastLightsTarget) {
      lastLightsTarget = target
      Log.i(TAG, "house lights -> $target in ${room.id} (playing=${player.isPlaying})")
    }
    lightsNow += (target - lightsNow) * 0.06f            // about 2 s, like house lights
    if (!room.passthrough) {
      val level = 1f - (1f - lightsNow) * room.houseDim
      kit.houseLights(level)
      shadeMask(level)
      return
    }
    shadeMask(1f)
    val spill = if (prefs.getBoolean("glowOn", true)) FILM_SPILL * (1f - lightsNow) else 0f
    val m = FloatArray(3) { lightsNow + glowNow[it] * spill }
    if ((0..2).all { abs(m[it] - lastLut[it]) < 0.01f }) return
    m.copyInto(lastLut)
    val lut = Lut(16)
    for (b in 0 until 16) for (g in 0 until 16) for (r in 0 until 16) {
      lut.setMapping(r, g, b, (r * 17 * m[0]).toInt().coerceIn(0, 255), (g * 17 * m[1]).toInt().coerceIn(0, 255),
          (b * 17 * m[2]).toInt().coerceIn(0, 255))
    }
    runCatching { scene.setPassthroughLUT(lut) }.onFailure { Log.w(TAG, "passthrough LUT: $it") }
  }

  // The masking and the subtitles, as laid out on the screen's plane: (centre, size)
  private var maskRects = emptyList<Pair<Vector3, Vector3>>()
  private var subRect: Pair<Vector3, Vector3>? = null
  private var nearEye: Vector3? = null

  /**
   * The masking stands MASK_AHEAD in front of the screen and the subtitles SUB_AHEAD, well clear
   * of the room's surfaces round the screen and of the glow layer just in front of those (the
   * depth buffer can't tell a few centimetres apart 15 m or more away: whichever won changed from
   * frame to frame and flashed). Each is shrunk towards your eyes ([eye], stage coordinates), so
   * it covers exactly what it would on the screen's plane. Called again when your head moves.
   */
  private fun placeNear(eye: Vector3) {
    val d = room.screen.distance
    fun put(e: Entity?, at: Pair<Vector3, Vector3>, ahead: Float) {
      val s = (d - ahead) / d
      e?.setComponent(Transform(Pose(eye + (at.first - eye) * s)))
      e?.setComponent(Scale(at.second * s))
    }
    frame.zip(maskRects).forEach { (e, r) -> put(e, r, MASK_AHEAD) }
    subRect?.let { put(subtitles, it, SUB_AHEAD) }
    nearEye = eye
  }

  /** Your eyes on the stage, or where they'd be in your seat while the headset gives no pose. */
  private fun eyeNow(): Vector3? {
    val head = scene.getViewerPose()
    if (!finite(head) || head.q.dot(head.q) < 0.5f) return null
    return (stagePose.inverse() * head.t).takeIf { it.x.isFinite() && it.y.isFinite() && it.z.isFinite() }
  }

  private fun seatEye() = Vector3(seat.x, floorNow + seat.y + headHeight, seat.z)

  private fun maskMaterial(level: Float) =
      Material().apply {
        baseColor = Color4(0.012f * level, 0.012f * level, 0.014f * level, 1f)
        unlit = true
      }

  private var maskShade = 1f

  /** The masking dims with the house lights, as the room's own velvet does. */
  private fun shadeMask(level: Float) {
    if (abs(level - maskShade) < 0.01f && (level < 1f || maskShade == 1f)) return
    maskShade = level
    frame.forEach { it.setComponent(maskMaterial(level)) }
  }

  /** Places the screen, subtitles and controls for the room and the chosen screen size. */
  private fun layoutScreen() {
    if (!sceneReady) return
    val spot = room.screen
    val width = spot.width * sizeMul
    val distance = spot.distance
    val aspect = if (webMode || moviesMode) 16f / 9f else videoAspect
    val height = width / aspect
    // On the room's own screen; bigger screens grow upwards from its line, never below its floor
    // (the hall's stage, or 15 cm off your floor). On a grounded screen films stand on its foot.
    val centerY = if (spot.grounded) spot.floor + height / 2
        else maxOf(spot.centerY + (height - spot.width / aspect) / 2 * 0.6f, spot.floor + height / 2)
    // The screen panels are 1 m × 0.5625 m; scale them to the width and the picture's own shape
    for (p in listOf(screen, webPanel, moviesPanel)) {
      p?.setComponent(Transform(Pose(Vector3(0f, centerY, distance))))
      p?.setComponent(Scale(Vector3(width, height / 0.5625f, 1f)))
    }
    // Masking: velvet black all round the picture, a border's width at least and out over the
    // room's own screen wherever the film leaves it bare (a wide film on a 16:9 screen, any film
    // on the 1.43:1 IMAX one), as a real cinema's masking closes in on the picture. The room's
    // dark screen surface showing there flashed against the surfaces just behind it.
    val border = maxOf(0.03f, width * 0.02f)
    val top = centerY + height / 2
    val bottom = centerY - height / 2
    val own = !room.bareScreen
    val mx = if (own) maxOf(spot.width / 2 + MASK_MARGIN, width / 2 + border) else width / 2 + border
    val mt = if (own) maxOf(spot.centerY + spot.height / 2 + MASK_MARGIN, top + border) else top + border
    // Standing on the screen's foot, the room's own velvet is the border below: masking reaching
    // past it would cut into the ledge in front
    val mb = if (own) minOf(spot.centerY - spot.height / 2 - MASK_MARGIN, if (spot.grounded) bottom else bottom - border)
        else bottom - border
    val lip = width * 0.0005f                     // a hair over the picture's edge: never a gap
    fun rect(x0: Float, x1: Float, y0: Float, y1: Float) =
        Vector3((x0 + x1) / 2, (y0 + y1) / 2, distance) to Vector3(x1 - x0, y1 - y0, 0.02f)
    maskRects = listOf(rect(-mx, mx, top - lip, mt), rect(-mx, mx, mb, bottom + lip),
        rect(-mx, -width / 2 + lip, bottom, top), rect(width / 2 - lip, mx, bottom, top))
    if (room.bareScreen) kit.placeScreen(Vector3(0f, centerY, distance), width, height, border)
    // Subtitles: a band just under the picture, or inside its foot where the floor or a stage in
    // front of the screen would hide them under it. SUB_AHEAD keeps them clear of the picture, as
    // the control bar in front of it is.
    val subWidth = width * 0.9f
    val subY = if (spot.subsInside) bottom + subWidth * 0.07f else bottom - subWidth * 0.07f
    subRect = Vector3(0f, subY, distance) to Vector3(subWidth, subWidth, 1f)
    placeNear(eyeNow() ?: nearEye ?: seatEye())
    // The bars are compositor layers: crisp, but anything in the room nearer to your eyes than they
    // are covers them. So they float at eye level, 60 cm away: seat backs and rails stay below and
    // farther off, and the walk map keeps walls away.
    for (bar in listOf(controls, webBar, moviesBar)) {
      bar?.setComponent(Transform(Pose(Vector3(0f, headHeight - BAR_DROP, BAR_DIST))))
      bar?.setComponent(Scale(Vector3(BAR_SCALE)))
    }
    // The Movies bar is one row (0.13 m tall), lower than the others so it doesn't cover the page
    // on the screen; its keyboard sits just above it
    moviesBar?.setComponent(Transform(Pose(Vector3(0f, headHeight - MOVIES_BAR_DROP, BAR_DIST))))
    moviesKeys?.setComponent(Transform(Pose(Vector3(0f, headHeight - MOVIES_BAR_DROP + 0.065f * BAR_SCALE + 0.2f * BAR_SCALE + 0.02f, BAR_DIST))))
    moviesKeys?.setComponent(Scale(Vector3(BAR_SCALE)))
    // The keyboard just above the web bar (below it, seat backs could cover it)
    keys?.setComponent(Transform(Pose(Vector3(0f, headHeight - BAR_DROP + 0.23f * BAR_SCALE + 0.2f * BAR_SCALE + 0.02f, BAR_DIST))))
    keys?.setComponent(Scale(Vector3(BAR_SCALE)))
    roomPicker?.setComponent(Transform(Pose(Vector3(0f, headHeight - BAR_DROP + 0.23f * BAR_SCALE + 0.22f * BAR_SCALE + 0.02f, BAR_DIST))))
    roomPicker?.setComponent(Scale(Vector3(BAR_SCALE)))
    settings?.setComponent(Transform(Pose(Vector3(0f, headHeight - BAR_DROP + 0.23f * BAR_SCALE + 0.25f * BAR_SCALE + 0.02f, BAR_DIST))))
    settings?.setComponent(Scale(Vector3(BAR_SCALE)))
    sizeBtns.forEach { it.text = String.format(Locale.ROOT, "Screen %.0f m", width) }
  }

  override fun registerPanels(): List<PanelRegistration> =
      listOf(
          VideoSurfacePanelRegistration(
              R.id.cinema_screen,
              // With its size, or the colour sampler's pipeline drops every frame (PanelSurfaceHolder)
              surfaceConsumer = { _, surface -> player.setVideoSurfaceHolder(PanelSurfaceHolder(surface, SCREEN_PX_W, SCREEN_PX_H)) },
              settingsCreator = {
                MediaPanelSettings(
                    shape = QuadShapeOptions(width = 1f, height = 0.5625f),
                    display = PixelDisplayOptions(width = SCREEN_PX_W, height = SCREEN_PX_H),
                    rendering = MediaPanelRenderOptions(),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_subtitles,
              { _, ctx ->
                TextView(ctx).apply {
                  textSize = 40f
                  setTextColor(Color.WHITE)
                  typeface = Typeface.DEFAULT_BOLD
                  gravity = Gravity.CENTER
                  setShadowLayer(8f, 0f, 3f, Color.BLACK)
                  subtitleView = this
                }
              },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1f, height = 0.14f),
                    display = DpDisplayOptions(1200f, 168f, 240),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_web,
              { _, ctx -> webScreen.pageView(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1f, height = 0.5625f),
                    display = DpDisplayOptions(1280f, 720f, 240),   // a 1080p desktop browser window
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_webbar,
              { _, ctx ->
                webMessage = label(ctx, 14f, 0xFFFFD27A.toInt()).apply { gravity = Gravity.CENTER; setPadding(0, dp(6f, ctx), 0, 0) }
                webScreen.bar(ctx, screenButtons(ctx) + button(ctx, "🎬 Movies") { openMovies() } + button(ctx, "▶ Back to film") { closeWeb() }, webMessage!!)
              },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.46f),
                    display = DpDisplayOptions(1280f, 368f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_movies,
              { _, ctx -> moviesScreen.pageView(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1f, height = 0.5625f),
                    display = DpDisplayOptions(1280f, 720f, 240),   // as wide as the browse panel
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_moviesbar,
              { _, ctx ->
                moviesMessage = label(ctx, 14f, 0xFFFFD27A.toInt()).apply { gravity = Gravity.CENTER; setPadding(0, dp(4f, ctx), 0, 0) }
                moviesScreen.bar(
                    ctx,
                    listOf(roomButton(ctx), button(ctx, "🌐 Web") { openWeb() }, button(ctx, "▶ Back to film") { closeMovies() },
                        button(ctx, "✕ Close") { close() }),
                    moviesMessage!!)
              },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.13f),
                    display = DpDisplayOptions(1280f, 104f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_movieskeys,
              { _, ctx -> moviesScreen.keyboard(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.4f),
                    display = DpDisplayOptions(1280f, 320f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_keys,
              { _, ctx -> webScreen.keyboard(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.4f),
                    display = DpDisplayOptions(1280f, 320f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_rooms,
              { _, ctx -> buildRoomPicker(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.44f),
                    display = DpDisplayOptions(1280f, 352f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_settings,
              { _, ctx -> buildSettings(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.5f),
                    display = DpDisplayOptions(1280f, 400f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
          ViewPanelRegistration(
              R.id.cinema_controls,
              { _, ctx -> buildControls(ctx) },
              {
                UIPanelSettings(
                    shape = QuadShapeOptions(width = 1.6f, height = 0.46f),
                    display = DpDisplayOptions(1280f, 368f, 320),
                    style = PanelStyleOptions(themeResourceId = R.style.PanelTransparent),
                )
              },
          ),
      )

  // ------------------------------------------------------------- control bar
  private fun dp(v: Float, ctx: android.content.Context) = (v * ctx.resources.displayMetrics.density).toInt()

  private fun label(ctx: android.content.Context, size: Float, color: Int, bold: Boolean = false) =
      TextView(ctx).apply {
        textSize = size
        setTextColor(color)
        if (bold) typeface = Typeface.DEFAULT_BOLD
        isSingleLine = true
      }

  private fun button(ctx: android.content.Context, text: String, onClick: () -> Unit) =
      label(ctx, 15f, Color.WHITE, true).apply {
        this.text = text
        gravity = Gravity.CENTER
        setPadding(dp(14f, ctx), dp(8f, ctx), dp(14f, ctx), dp(8f, ctx))
        background =
            GradientDrawable().apply {
              setColor(0xFF2A3142.toInt())
              cornerRadius = dp(20f, ctx).toFloat()
            }
        setOnClickListener { onClick() }
        layoutParams = LinearLayout.LayoutParams(-2, -2).apply { setMargins(dp(4f, ctx), 0, dp(4f, ctx), 0) }
      }

  /** Room, screen size and Recenter: on both the film bar and the web bar. */
  private fun roomButton(ctx: android.content.Context) =
      button(ctx, "Room: ${room.label}  ▾") { showRoomPicker(!roomPickerShown) }.also { roomBtns += it }

  private fun screenButtons(ctx: android.content.Context): List<View> {
    val roomBtn = roomButton(ctx)
    val sizeBtn = label(ctx, 15f, 0xFFB0B7C8.toInt()).apply { gravity = Gravity.CENTER; setPadding(dp(6f, ctx), 0, dp(6f, ctx), 0) }
    sizeBtns += sizeBtn
    return listOf(
        roomBtn,
        button(ctx, "Screen −") { resizeScreen(1 / 1.2f) },
        sizeBtn,
        button(ctx, "Screen +") { resizeScreen(1.2f) },
        button(ctx, "⟳ Recenter") { recenter() })
  }

  // ------------------------------------------------------------- room picker
  private var roomPickerShown = false

  /** The room list over the bar: every room by name, the current one ringed in gold. */
  private fun showRoomPicker(show: Boolean) {
    roomPickerShown = show && controlsShown
    roomPicker?.setComponent(Visible(roomPickerShown))
    if (roomPickerShown) showSettings(false)          // both sit just over the bar
    if (roomPickerShown) keys?.setComponent(Visible(false))   // the keyboard sits in the same spot
  }

  private fun tileBackground(ctx: android.content.Context, current: Boolean) =
      GradientDrawable().apply {
        setColor(if (current) 0xFF3A3220.toInt() else 0xFF2A3142.toInt())
        cornerRadius = dp(16f, ctx).toFloat()
        if (current) setStroke(dp(3f, ctx), 0xFFFFC531.toInt())
      }

  private fun buildRoomPicker(ctx: android.content.Context): View {
    val root =
        LinearLayout(ctx).apply {
          orientation = LinearLayout.VERTICAL
          setPadding(dp(16f, ctx), dp(10f, ctx), dp(16f, ctx), dp(12f, ctx))
          background =
              GradientDrawable().apply {
                setColor(0xF0121620.toInt())
                cornerRadius = dp(24f, ctx).toFloat()
              }
        }
    val head = LinearLayout(ctx).apply { gravity = Gravity.CENTER_VERTICAL }
    head.addView(label(ctx, 17f, Color.WHITE, true).apply { text = "Choose a room" }, LinearLayout.LayoutParams(0, -2, 1f))
    head.addView(button(ctx, "✕") { showRoomPicker(false) })
    root.addView(head)
    roomTiles.clear()
    ROOMS.chunked(ROOM_COLUMNS).forEach { line ->
      val row = LinearLayout(ctx)
      for (i in 0 until ROOM_COLUMNS) {
        val r = line.getOrNull(i)
        val tile =
            LinearLayout(ctx).apply {
              orientation = LinearLayout.VERTICAL
              gravity = Gravity.CENTER_VERTICAL
              setPadding(dp(14f, ctx), dp(6f, ctx), dp(10f, ctx), dp(6f, ctx))
            }
        if (r != null) {
          tile.addView(label(ctx, 16f, Color.WHITE, true).apply { text = r.label })
          tile.addView(label(ctx, 12f, 0xFFB0B7C8.toInt()).apply { text = r.about })
          tile.background = tileBackground(ctx, r === room)
          tile.setOnClickListener { applyRoom(r) }
          roomTiles += r to tile
        }
        row.addView(tile, LinearLayout.LayoutParams(0, dp(72f, ctx), 1f).apply { setMargins(dp(4f, ctx), dp(6f, ctx), dp(4f, ctx), 0) })
      }
      root.addView(row)
    }
    return root
  }

  // ---------------------------------------------------------------- ⚙ settings
  // Lights (how far they go down while the film plays), Picture (contrast, brightness, colour),
  // Sound (SoundModes) and Seat (the room's seats), over the bar where the room picker goes.
  private var settingsShown = false
  private var lightsValue: TextView? = null
  private val pictureValues = HashMap<String, TextView>()
  private val soundBtns = ArrayList<TextView>()
  private var seatRow: LinearLayout? = null

  private fun settingsLabel() = "⚙ Lights ${lightsPct()}%  ▾"

  private fun showSettings(show: Boolean) {
    settingsShown = show && controlsShown && !webMode && !moviesMode
    settings?.setComponent(Visible(settingsShown))
    if (settingsShown) showRoomPicker(false)
  }

  private fun chipBackground(ctx: android.content.Context, on: Boolean) =
      GradientDrawable().apply {
        setColor(if (on) 0xFF3A3220.toInt() else 0xFF2A3142.toInt())
        cornerRadius = dp(20f, ctx).toFloat()
        if (on) setStroke(dp(2f, ctx), 0xFFFFC531.toInt())
      }

  private fun settingsRow(ctx: android.content.Context, title: String) =
      LinearLayout(ctx).apply {
        gravity = Gravity.CENTER_VERTICAL
        setPadding(0, dp(10f, ctx), 0, 0)
        addView(label(ctx, 15f, 0xFFB0B7C8.toInt(), true).apply { text = title }, LinearLayout.LayoutParams(dp(110f, ctx), -2))
      }

  /** − value +, added to [row]: returns the value's label. */
  private fun stepper(ctx: android.content.Context, row: LinearLayout, value: String, step: (Int) -> Unit): TextView {
    row.addView(button(ctx, "−") { step(-1) })
    val v = label(ctx, 15f, Color.WHITE, true).apply { gravity = Gravity.CENTER; text = value }
    row.addView(v, LinearLayout.LayoutParams(dp(58f, ctx), -2))
    row.addView(button(ctx, "+") { step(1) })
    return v
  }

  private fun signed(v: Int) = if (v > 0) "+$v" else "$v"

  private fun buildSettings(ctx: android.content.Context): View {
    val root =
        LinearLayout(ctx).apply {
          orientation = LinearLayout.VERTICAL
          setPadding(dp(16f, ctx), dp(10f, ctx), dp(16f, ctx), dp(12f, ctx))
          background =
              GradientDrawable().apply {
                setColor(0xF0121620.toInt())
                cornerRadius = dp(24f, ctx).toFloat()
              }
        }
    val head = LinearLayout(ctx).apply { gravity = Gravity.CENTER_VERTICAL }
    head.addView(label(ctx, 17f, Color.WHITE, true).apply { text = "Settings" }, LinearLayout.LayoutParams(0, -2, 1f))
    head.addView(button(ctx, "✕") { showSettings(false) })
    root.addView(head)

    val lightsRow = settingsRow(ctx, "Lights")
    lightsValue = stepper(ctx, lightsRow, "${lightsPct()}%") { d ->
      val i = LIGHT_STEPS.indices.minBy { abs(LIGHT_STEPS[it] - lightsPct()) }
      setLights(LIGHT_STEPS[(i + d).coerceIn(0, LIGHT_STEPS.size - 1)])
    }
    for ((name, pct) in listOf("Dark" to 8, "Dim" to 13, "On" to 100)) lightsRow.addView(button(ctx, name) { setLights(pct) })
    lightsRow.addView(label(ctx, 13f, 0xFF7D869B.toInt()).apply { text = "  how bright the room stays while the film plays" })
    root.addView(lightsRow)

    val picture = settingsRow(ctx, "Picture")
    for ((key, name) in listOf("contrast" to "Contrast", "brightness" to "Brightness", "colour" to "Colour")) {
      picture.addView(label(ctx, 14f, Color.WHITE).apply { text = name; setPadding(dp(8f, ctx), 0, dp(2f, ctx), 0) })
      pictureValues[key] = stepper(ctx, picture, signed(prefs.getInt(key, 0))) { d -> stepPicture(key, d) }
    }
    picture.addView(button(ctx, "Reset") { for (key in pictureValues.keys) stepPicture(key, 0, reset = true) })
    root.addView(picture)

    val soundRow = settingsRow(ctx, "Sound")
    soundBtns.clear()
    SoundModes.NAMES.forEachIndexed { i, name -> soundBtns += button(ctx, name) { setSound(i) }.also { soundRow.addView(it) } }
    markSound()
    root.addView(soundRow)

    seatRow = settingsRow(ctx, "Seat")
    fillSeats()
    root.addView(seatRow)
    return root
  }

  private fun setLights(pct: Int) {
    lightsPct = pct
    prefs.edit().putInt("lightsPct", pct).apply()
    lightsValue?.text = "$pct%"
    lightsBtn?.text = settingsLabel()
  }

  /** Steps a picture setting by [d] (or back to 0) and applies the picture effects to the film. */
  private fun stepPicture(key: String, d: Int, reset: Boolean = false) {
    val v = if (reset) 0 else (prefs.getInt(key, 0) + d).coerceIn(-5, 5)
    prefs.edit().putInt(key, v).apply()
    pictureValues[key]?.text = signed(v)
    if (effectsOn) enableScreenLight() else flash("Picture settings can't be used with this video")
  }

  private fun setSound(mode: Int) {
    prefs.edit().putInt("sound", mode).apply()
    val ok = sound?.apply(mode) ?: false
    markSound()
    if (!ok) flash("Some of ${SoundModes.NAMES[mode]}'s effects aren't available on this headset")
  }

  private fun markSound() {
    val mode = prefs.getInt("sound", SoundModes.STANDARD)
    soundBtns.forEachIndexed { i, b -> b.background = chipBackground(b.context, i == mode) }
  }

  /** The room's seats on the Seat row (a new room has its own). */
  private fun fillSeats() {
    val row = seatRow ?: return
    while (row.childCount > 1) row.removeViewAt(1)
    room.seats.forEach { (name, at) -> row.addView(button(row.context, name) { goToSeat(name, at) }) }
  }

  /** Takes you to one of the room's seats: the walk map gives its floor; your seat lift stays. */
  private fun goToSeat(name: String, at: Vector3) {
    val f = standable(at.x, at.z) ?: return flash("Can't get to that seat in this room")
    seat = Vector3(at.x, seat.y, at.z)
    floorTarget = f
    floorNow = f
    seatDirty = true
    placeStage()
    layoutScreen()
    flash("Seat: $name")
  }

  private fun buildControls(ctx: android.content.Context): View {
    val root =
        LinearLayout(ctx).apply {
          orientation = LinearLayout.VERTICAL
          setPadding(dp(20f, ctx), dp(14f, ctx), dp(20f, ctx), dp(14f, ctx))
          background =
              GradientDrawable().apply {
                setColor(0xE6121620.toInt())
                cornerRadius = dp(24f, ctx).toFloat()
              }
        }
    val top = LinearLayout(ctx)
    titleView = label(ctx, 17f, Color.WHITE, true)
    timeView = label(ctx, 15f, 0xFFB0B7C8.toInt()).apply { gravity = Gravity.END }
    top.addView(titleView, LinearLayout.LayoutParams(0, -2, 3f))
    top.addView(timeView, LinearLayout.LayoutParams(0, -2, 1f))
    root.addView(top)
    seekBar =
        SeekBar(ctx).apply {
          max = 1000
          progressTintList = ColorStateList.valueOf(0xFFFFC531.toInt())
          thumbTintList = ColorStateList.valueOf(0xFFFFC531.toInt())
          setOnSeekBarChangeListener(
              object : SeekBar.OnSeekBarChangeListener {
                override fun onProgressChanged(b: SeekBar, p: Int, fromUser: Boolean) {
                  if (fromUser && player.duration > 0) {
                    timeView?.text = "${Playlist.time(player.duration * p / 1000)} / ${Playlist.time(player.duration)}"
                  }
                }

                override fun onStartTrackingTouch(b: SeekBar) {
                  dragging = true
                }

                override fun onStopTrackingTouch(b: SeekBar) {
                  dragging = false
                  if (player.duration > 0) player.seekTo(player.duration * b.progress / 1000)
                }
              })
        }
    root.addView(seekBar, LinearLayout.LayoutParams(-1, -2).apply { setMargins(0, dp(6f, ctx), 0, dp(6f, ctx)) })
    val row1 = LinearLayout(ctx).apply { gravity = Gravity.CENTER }
    row1.addView(button(ctx, "« 10s") { seekBy(-10_000) })
    playBtn = button(ctx, "❚❚  Pause") { togglePlay() }
    row1.addView(playBtn)
    row1.addView(button(ctx, "10s »") { seekBy(10_000) })
    ccBtn = button(ctx, "CC: Off") { cycleSubtitle() }
    row1.addView(ccBtn)
    qualityBtn = button(ctx, "Quality") { nextQuality() }
    row1.addView(qualityBtn)
    nextBtn = button(ctx, "Next ⏭") { pl?.let { if (item + 1 < it.items.size) { saveProgress(false); start(item + 1) } } }
    row1.addView(nextBtn)
    likeBtn = button(ctx, "♡ Like") { toggleLike() }
    row1.addView(likeBtn)
    row1.addView(button(ctx, "🎬 Movies") { openMovies() })
    row1.addView(button(ctx, "🌐 Web") { openWeb() })
    root.addView(row1)
    val row2 = LinearLayout(ctx).apply { gravity = Gravity.CENTER; setPadding(0, dp(10f, ctx), 0, 0) }
    screenButtons(ctx).forEach { row2.addView(it) }
    row2.addView(button(ctx, "✕ Close") { close() })
    root.addView(row2)
    val row3 = LinearLayout(ctx).apply { gravity = Gravity.CENTER; setPadding(0, dp(10f, ctx), 0, 0) }
    row3.addView(button(ctx, "Closer") { moveSeat(0f, 0f, 0.75f) })
    row3.addView(button(ctx, "Farther") { moveSeat(0f, 0f, -0.75f) })
    row3.addView(button(ctx, "Seat ▲") { moveSeat(0f, 0.15f, 0f) })
    row3.addView(button(ctx, "Seat ▼") { moveSeat(0f, -0.15f, 0f) })
    row3.addView(button(ctx, "Reset seat") {
      seat = Vector3(0f)
      sizeMul = 1f
      floorTarget = standable(0f, 0f) ?: 0f
      seatDirty = true
      placeStage()
      layoutScreen()
    })
    // Room glow: the room lit by the film. Off = the room stays as baked (also a check if it misbehaves)
    var glowBtn: TextView? = null
    fun glowLabel() = if (prefs.getBoolean("glowOn", true)) "Room glow: On" else "Room glow: Off"
    glowBtn = button(ctx, glowLabel()) {
      val on = !prefs.getBoolean("glowOn", true)
      prefs.edit().putBoolean("glowOn", on).apply()
      if (sceneReady) kit.glowOn = on
      glowBtn?.text = glowLabel()
    }
    row3.addView(glowBtn)
    lightsBtn = button(ctx, settingsLabel()) { showSettings(!settingsShown) }
    row3.addView(lightsBtn)
    root.addView(row3)
    root.addView(label(ctx, 13f, 0xFF7D869B.toInt()).apply {
      text = "Left stick: walk · Hold A/X, aim, let go: teleport · Right stick ◀▶: turn, ▲▼: screen size · B/Y: hide this bar"
      gravity = Gravity.CENTER
      setPadding(0, dp(8f, ctx), 0, 0)
    })
    messageView = label(ctx, 14f, 0xFFFFD27A.toInt()).apply { gravity = Gravity.CENTER; setPadding(0, dp(6f, ctx), 0, 0) }
    root.addView(messageView)
    return root
  }

  private fun updateControls() {
    val p = pl
    val it = p?.items?.getOrNull(item)
    titleView?.text = when {
      p == null -> "BuzzTorrent"
      p.items.size > 1 -> "${p.title} · ${it?.name}"
      else -> p.title
    }
    playBtn?.text = if (player.isPlaying) "❚❚  Pause" else "▶  Play"
    if (it != null) {
      ccBtn?.visibility = if (it.subs.isEmpty()) View.GONE else View.VISIBLE
      ccBtn?.text = if (sub >= 0) "CC: ${it.subs[sub].label}" else "CC: Off"
      qualityBtn?.visibility = if (it.urls.size > 1) View.VISIBLE else View.GONE
      qualityBtn?.text = "Quality: ${it.label(version)}${if (manualQuality) "" else " auto"}"
      nextBtn?.visibility = if (item + 1 < p.items.size) View.VISIBLE else View.GONE
    }
    if (!dragging) {
      val dur = player.duration
      val pos = player.currentPosition
      seekBar?.progress = if (dur > 0) (1000 * pos / dur).toInt() else 0
      timeView?.text = "${Playlist.time(pos)} / ${if (dur > 0) Playlist.time(dur) else "--:--"}"
    }
  }

  private fun show(msg: String) {
    ui.removeCallbacks(clearMessage)
    messageView?.text = msg
    webMessage?.text = msg
  }

  private fun flash(msg: String) {
    show(msg)
    clearMessageSoon(4000)
  }

  private fun clearMessageSoon(ms: Long) {
    ui.removeCallbacks(clearMessage)
    ui.postDelayed(clearMessage, ms)
  }

  // ---------------------------------------------------------------- playback
  /** Starts an item: picks the quality the Wi-Fi can carry, then plays. */
  private fun start(i: Int) {
    val p = pl ?: return
    item = i
    sub = -1
    val it = p.items[i]
    if (it.startSub >= 0 && it.startSub < it.subs.size) {
      sub = it.startSub
      val chosen = it.subs[sub]
      if (chosen.text == null && !chosen.loading) loadSub(chosen)
    }
    val resumeMs = if (!resumed && it.resume > 0) (it.resume * 1000).toLong() else 0L
    if (resumeMs > 0) flash("Resumed from ${Playlist.time(resumeMs)}. Drag the bar to go back")
    resumed = true
    if (manualQuality || it.urls.size < 2 || !it.urls[0].startsWith("https://")) {
      play(i, if (manualQuality) minOf(version, it.urls.size - 1) else 0, resumeMs)
      return
    }
    show("Checking your Wi-Fi speed…")
    Thread({
      val mbps = Playlist.measureMbps(it.urls[0])
      val chosen = it.pickFor(mbps)
      runOnUiThread {
        if (isFinishing) return@runOnUiThread
        play(i, chosen, resumeMs)
        if (mbps > 0) {
          flash(String.format(Locale.ROOT, "Wi-Fi ≈ %.0f Mbps · playing %s", mbps, it.label(chosen)) +
              if (chosen > 0) " (${it.label(0)} needs more). Tap Quality to change" else "")
        }
      }
    }, "speedtest").start()
  }

  private fun play(i: Int, v: Int, positionMs: Long) {
    val it = pl?.items?.get(i) ?: return
    item = i
    version = v
    ready = false
    stalls.clear()
    show("Loading ${it.label(v)}…")
    player.setMediaItem(MediaItem.fromUri(it.urls[v].toUri()), positionMs)
    player.prepare()
    player.playWhenReady = true
  }

  /** Keeps buffering? Step down one quality (unless the viewer picked one by hand). */
  private fun stalled() {
    val now = SystemClock.elapsedRealtime()
    if (now - readyAt < 15_000) return // the first seconds always buffer
    stalls.add(now)
    while (stalls.isNotEmpty() && now - stalls[0] > 120_000) stalls.removeAt(0)
    val it = pl?.items?.get(item) ?: return
    if (stalls.size >= 3 && !manualQuality && version + 1 < it.urls.size) {
      flash("Your Wi-Fi can't keep up. Switching to ${it.label(version + 1)}")
      play(item, version + 1, player.currentPosition)
    }
  }

  private fun togglePlay() {
    if (player.isPlaying) { player.pause(); saveProgress(false) } else player.play()
  }

  private fun seekBy(ms: Long) {
    val dur = player.duration
    val target = (player.currentPosition + ms).coerceAtLeast(0)
    player.seekTo(if (dur > 0) target.coerceAtMost(dur - 1000) else target)
  }

  /** Next lower quality, wrapping back to the best. Turns automatic switching off. */
  private fun nextQuality() {
    val it = pl?.items?.get(item) ?: return
    if (it.urls.size < 2) return
    manualQuality = true
    val v = (version + 1) % it.urls.size
    flash("Quality: ${it.label(v)}")
    play(item, v, player.currentPosition)
  }

  // --------------------------------------------------------------- subtitles
  private fun cycleSubtitle() {
    val it = pl?.items?.get(item) ?: return
    if (it.subs.isEmpty()) return
    sub = if (sub + 1 >= it.subs.size) -1 else sub + 1
    subtitleView?.text = ""
    if (sub < 0) { flash("Subtitles off"); return }
    val s = it.subs[sub]
    flash("Subtitles: ${s.label}")
    if (s.text == null && !s.loading) loadSub(s)
  }

  private fun loadSub(s: Playlist.Sub) {
    Playlist.loadSub(s) { runOnUiThread { flash("Couldn't load the subtitles") } }
  }

  private fun drawSubtitle() {
    val view = subtitleView ?: return
    val it = pl?.items?.getOrNull(item)
    val line = if (it == null || sub < 0 || !ready) "" else Playlist.cueAt(it.subs[sub], player.currentPosition / 1000.0)
    if (!line.contentEquals(view.text)) view.text = line
    showSubtitles(line.isNotEmpty() && !webMode && !moviesMode)
  }

  /** The subtitle panel is shown only while there's a line to read: an empty one lying over the
   *  bottom of the picture made it flicker there. */
  private var subtitlesShown = true

  private fun showSubtitles(on: Boolean) {
    if (on == subtitlesShown) return
    subtitlesShown = on
    subtitles?.setComponent(Visible(on))
  }

  // ------------------------------------------------------------------ the end
  /** ♥ while watching: the PC remembers it and lines up similar titles under "For you" (TV page too). */
  private fun toggleLike() {
    val p = pl ?: return
    if (p.like == null) { flash("Nothing to like here"); return }
    show("♥ …")
    p.toggleLike { liked ->
      ui.post {
        flash(when (liked) {
          null -> "Couldn't reach the PC to save the ♥"
          true -> "♥ Liked. Picks like it will appear under ♥ For you"
          else -> "Removed from your likes"
        })
        likeBtn?.text = if (p.liked == 1) "♥ Liked" else "♡ Like"
      }
    }
  }

  private fun saveProgress(finished: Boolean) {
    val p = pl ?: return
    val it = p.items.getOrNull(item) ?: return
    val dur = player.duration
    if (dur <= 0) return
    val pos = if (finished) dur else player.currentPosition
    p.saveProgress(it, it.label(version), pos.toInt(), dur.toInt())
  }

  /** Back to the browse panel in Horizon Home. */
  private fun close() {
    saveProgress(false)
    player.pause()
    val panel =
        Intent(applicationContext, QuestMainActivity::class.java)
            .setAction(Intent.ACTION_MAIN)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
    val pending =
        PendingIntent.getActivity(
            applicationContext, 0, panel, PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
    startActivity(
        Intent(Intent.ACTION_MAIN)
            .addCategory(Intent.CATEGORY_HOME)
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
            .putExtra("extra_launch_in_home_pending_intent", pending))
    finish()
  }

  override fun onPause() {
    if (seatDirty) saveSeat()
    saveProgress(false)
    if (::player.isInitialized) player.pause()
    if (webMode) webScreen.pause()
    if (moviesMode) moviesScreen.pause()
    super.onPause()
  }

  override fun onResume() {
    super.onResume()
    if (webMode) webScreen.resume()
    if (moviesMode) moviesScreen.resume()
  }

  companion object {
    const val MIN_SIZE = 0.25f
    const val MAX_SIZE = 4f
    // Screen light on the room. Measured on the Quest: the glow layer at 0.15 lights the Grand
    // hall's seats and walls from the screen about as brightly as its house lights. At gain 0.35
    // (an average frame ~0.1) the film's light was too much in a dark hall; 0.15 gives ~0.045
    const val GLOW_GAIN = 0.15f
    const val SCREEN_PX_W = 3840           // the film panel's surface
    const val MASK_AHEAD = 0.25f           // the masking: metres in front of the screen (placeNear)
    const val SUB_AHEAD = 0.45f            // the subtitles: in front of the masking
    const val MASK_MARGIN = 0.12f          // the masking reaches this far over the room's screen edge
    const val SCREEN_PX_H = 2160
    const val IDLE_GLOW = 0.015f           // no film yet: as if the screen showed a dim grey
    const val WEB_GLOW = 0.017f            // a web page on the screen: an even, soft light
    const val MOVIES_GLOW = 0.006f         // the Movies page is dark: hardly any light from it
    const val BAR_DIST = 0.6f              // the control / web bar: metres in front of you
    const val FOLLOW_ANGLE = 35f           // ...glides back in front of you once you look this far away
    const val FOLLOW_DIST = 0.5f           // ...or step this far (metres) from it
    const val BAR_DROP = 0.08f             // ...and its middle this far under your eyes
    const val MOVIES_BAR_DROP = 0.3f       // the Movies bar: well under the page on the screen
    const val BAR_SCALE = 0.5f             // 1.6 m panels shown 0.8 m wide (as wide to the eye as before)
    const val CONTRAST_STEP = 0.08f        // ⚙ Settings: Contrast −5..+5 (Media3 Contrast, -1..1)
    const val BRIGHTNESS_STEP = 0.03f      // Brightness −5..+5 (added, -1..1)
    const val COLOUR_STEP = 10f            // Colour −5..+5 (saturation, -100..100)
    val LIGHT_STEPS = intArrayOf(0, 2, 4, 6, 8, 10, 13, 16, 20, 25, 30, 40, 50, 65, 80, 100)
    const val ROOM_COLUMNS = 4             // the room picker: 11 rooms in rows of 4
    const val ROOM_SWAP_MS = 250L          // old room's models swept before the next one loads
    const val FILM_SPILL = 13f             // My room: how strongly the film's colour lights your room
    const val TAG = "BuzzVR"
    const val POINTER_REACH = 80f          // metres: past the far wall of the biggest hall
    const val WEB_SCROLL = 9f              // right stick on a web page: mouse-wheel ticks a second
    const val STICK_TURN = 1
    const val STICK_SIZE = 2
    val SIDEWAYS = ButtonBits.ButtonThumbRL or ButtonBits.ButtonThumbRR
    val RIGHT_STICK = SIDEWAYS or ButtonBits.ButtonThumbRU or ButtonBits.ButtonThumbRD
    const val SNAP_TURN = 30f              // degrees per flick of the right stick
    const val MAX_STEP = 0.65f             // highest step you can walk up or down (metres)
    const val ARC_SPEED = 7f               // teleport arc: throw speed (m/s), ~5 m on the level
    const val ARC_STEP = 0.02f
    const val ARC_DOTS = 40
    val FRAME_ERRORS =
        setOf(
            PlaybackException.ERROR_CODE_VIDEO_FRAME_PROCESSOR_INIT_FAILED,
            PlaybackException.ERROR_CODE_VIDEO_FRAME_PROCESSING_FAILED,
        )
  }

  override fun onDestroy() {
    ui.removeCallbacksAndMessages(null)
    sound?.release()
    if (::player.isInitialized) player.release()
    if (webPanel != null) webScreen.destroy()
    if (moviesPanel != null) moviesScreen.destroy()
    super.onDestroy()
  }
}
