package com.buzzcaf.buzztorrent.vr

import android.util.Log
import androidx.core.net.toUri
import com.meta.spatial.core.Color4
import com.meta.spatial.core.Entity
import com.meta.spatial.core.Pose
import com.meta.spatial.core.Quaternion
import com.meta.spatial.core.Vector3
import com.meta.spatial.core.Vector4
import com.meta.spatial.runtime.BlendMode
import com.meta.spatial.runtime.DepthTest
import com.meta.spatial.runtime.DepthWrite
import com.meta.spatial.runtime.MaterialSidedness
import com.meta.spatial.runtime.SceneMaterial
import com.meta.spatial.runtime.SceneObject
import com.meta.spatial.runtime.SortOrder
import com.meta.spatial.toolkit.Box
import com.meta.spatial.toolkit.Light
import com.meta.spatial.toolkit.LightType
import com.meta.spatial.toolkit.Material
import com.meta.spatial.toolkit.Mesh
import com.meta.spatial.toolkit.MeshCollision
import com.meta.spatial.toolkit.Scale
import com.meta.spatial.toolkit.Sphere
import com.meta.spatial.toolkit.Transform
import com.meta.spatial.toolkit.TransformParent
import com.meta.spatial.toolkit.Visible
import kotlin.math.abs
import kotlin.math.atan2
import kotlin.math.cos
import kotlin.math.sin

/**
 * The virtual rooms: light-baked models from quest/scenes (plus a 360° sky photo and live fire),
 * in "stage" coordinates: the viewer at the origin on the floor, +Z towards the screen,
 * +Y up. The stage itself is turned to wherever the viewer looks when the cinema opens.
 * Spatial SDK is left-handed and mirrors X when it loads a glTF, so Blender (x, y) is stage (-x, -y).
 *
 * Sky photos: Poly Haven (CC0), ESO/S. Brunier (CC BY 4.0), NASA Blue Marble (public domain).
 */

/**
 * Where the screen goes in a room: its width and distance (metres) and the height of its centre.
 * [height] is the room's own screen surface (16:9 unless said), which the picture lies on, masked
 * in black wherever the film doesn't cover it. [floor] is as low as the picture's bottom edge may
 * go: 15 cm off your floor, or, above a stage, the screen's own bottom edge. [grounded]: films
 * stand on [floor] instead of centring on [centerY] (a screen taller than the film, where a
 * centred film left bare screen under it). [subsInside]: the subtitles go inside the picture's
 * foot, where under it the floor or a stage in front of the screen would hide them.
 */
data class ScreenSpot(
    val width: Float,
    val distance: Float,
    val centerY: Float,
    val height: Float = width * 9f / 16f,
    val floor: Float = 0.15f,
    val grounded: Boolean = false,
    val subsInside: Boolean = grounded,
)

/**
 * How far the glow layer is shrunk towards your eyes: 1 % of the distance (10 cm at 10 m). Depth
 * precision falls off with distance squared, so 0.2 % still flashed on a big hall's far walls
 * once the hall was dimmed and the glow became most of the light.
 */
private const val GLOW_SHRINK = 0.99f

/** The bare screen's halo: brighter than the room glow, as a wall right behind a screen is lit. */
private const val HALO_GAIN = 10.7f

/**
 * Additive layers write colour but never alpha (Vulkan's R|G|B bits). Panels (the Movies page, the
 * bars) show through holes in the scene's alpha; an additive layer adding alpha filled those holes
 * in, and the BuzzTorrent page on the screen went black.
 */
private const val RGB_ONLY = 1 or 2 or 4

/**
 * The shader uniform the texture is multiplied by. Every tint (house lights, the screen's glow,
 * the halo, firelight pools) sets it directly: setAlbedoColor on the baked rooms turned them white,
 * so it does more than scale the texture.
 */
private const val ALBEDO_FACTOR = "albedoFactor"

/** Live fire: flipbook frames from quest/scenes/make_fire.py, played at FIRE_FPS. */
private const val FIRE_FRAMES = 12
private const val FIRE_FPS = 14f

/** Firelight's flicker, about 1: a few unrelated beats added up. */
fun flicker(seconds: Float, phase: Float = 0f): Float =
    0.86f + 0.08f * sin(seconds * 9.1f + phase) + 0.05f * sin(seconds * 23.7f + phase * 3f) +
        0.03f * sin(seconds * 41.3f + phase * 7f)

/** Builds and removes a room's entities under the stage. */
class Kit(
    private val stage: Entity,
    private val sceneObject: (Entity) -> java.util.concurrent.CompletableFuture<SceneObject>?,
) {
  private val made = mutableListOf<Entity>()
  private val glowMaterials = java.util.concurrent.CopyOnWriteArrayList<SceneMaterial>()
  private val glowLayers = mutableListOf<Entity>()
  private val lastGlow = floatArrayOf(-1f, -1f, -1f)
  private val roomMaterials = java.util.concurrent.CopyOnWriteArrayList<SceneMaterial>()
  @Volatile private var house = 1f

  private class Flame(val frames: List<Entity>, val at: Vector3, val size: Float, val phase: Float) {
    var shown = 0
  }
  private class Spark(val e: Entity, val from: Vector3, val rise: Float, val speed: Float, val phase: Float)
  private class Glow(val light: Entity, val intensity: Float, val pool: MutableList<SceneMaterial>, val phase: Float)
  private val flames = mutableListOf<Flame>()
  private var backing: Entity? = null
  private var halo: Entity? = null
  private val haloMaterials = java.util.concurrent.CopyOnWriteArrayList<SceneMaterial>()
  private val sparks = mutableListOf<Spark>()
  private val fireGlows = mutableListOf<Glow>()

  /** Room glow on/off (the bar's "Room glow" button); new rooms follow it too. */
  var glowOn = true
    set(on) {
      field = on
      glowLayers.forEach { it.setComponent(Visible(on)) }
      halo?.setComponent(Visible(on))
    }

  /** True once the room's screen-light layer is loaded and can follow the film. */
  val glows: Boolean
    get() = glowMaterials.isNotEmpty()

  private fun add(vararg components: com.meta.spatial.core.ComponentBase): Entity =
      Entity.create(components.toList() + TransformParent(stage)).also { made += it }

  fun box(
      x0: Float, y0: Float, z0: Float,
      x1: Float, y1: Float, z1: Float,
      color: Color4,
      glow: Boolean = false,
      rotation: Quaternion = Quaternion(),
  ): Entity {
    // Centred at the box's middle so a rotation turns it in place
    val c = Vector3((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2)
    val h = Vector3((x1 - x0) / 2, (y1 - y0) / 2, (z1 - z0) / 2)
    return add(
        Mesh("mesh://box".toUri(), hittable = MeshCollision.NoCollision),
        Box(-h, h),
        Material().apply {
          baseColor = color
          unlit = glow
        },
        Transform(Pose(c, rotation)),
    )
  }

  fun sphere(x: Float, y: Float, z: Float, radius: Float, color: Color4, glow: Boolean = false, texture: Int = 0): Entity =
      add(
          Mesh("mesh://sphere".toUri(), hittable = MeshCollision.NoCollision),
          Sphere(radius),
          Material().apply {
            baseColor = color
            unlit = glow
            if (texture != 0) baseTextureAndroidResourceId = texture
          },
          Transform(Pose(Vector3(x, y, z))),
      )

  fun light(x: Float, y: Float, z: Float, color: Vector3, intensity: Float, range: Float): Entity =
      add(
          Light(LightType.POINT, color, intensity, range, Vector3(0f, -1f, 0f), 0f, 0f),
          Transform(Pose(Vector3(x, y, z))),
      )

  /** A 3D model from the APK's assets (quest/scenes builds them in Blender, with the lighting baked in). */
  fun model(path: String, baked: Boolean = true, glow: Boolean = false): Entity {
    val e =
        add(
            Mesh("apk:///$path".toUri(), hittable = MeshCollision.NoCollision).apply {
              if (baked) defaultShaderOverride = SceneMaterial.UNLIT_SHADER  // the textures already hold the light
            },
            Transform(Pose()),
        )
    if (baked) {
      // Left as loaded; houseLights() only ever scales the albedo factor
      sceneObject(e)?.thenAccept { so ->
        so.materials?.forEach { m ->
          val at = runCatching { m.getAttributeIndex(ALBEDO_FACTOR) }.getOrDefault(-1)
          Log.i("BuzzVR", "house lights: $path material $ALBEDO_FACTOR=$at params=${m.params?.map { it.name }}")
          if (at < 0) return@forEach
          if (house < 1f) m.setAttribute(ALBEDO_FACTOR, Vector4(house, house, house, 1f))
          roomMaterials += m
        }
      }
    }
    if (glow) {
      // The same room lit only by a white screen, added on top and tinted with the film's colour.
      // Drawn after the room without touching depth. glowPivot() keeps it a hair in front of the
      // room's own surfaces as seen from your eyes, so the two never fight over the same pixels.
      val g =
          add(
              Mesh("apk:///${path.removeSuffix(".glb")}_glow.glb".toUri(), hittable = MeshCollision.NoCollision).apply {
                defaultShaderOverride = SceneMaterial.UNLIT_SHADER
              },
              Transform(Pose()),
          )
      sceneObject(g)?.thenAccept { so ->
        so.materials?.forEach { m ->
          m.setBlendMode(BlendMode.ADDITIVE)
          m.setColorWrite(RGB_ONLY)
          m.setSortOrder(SortOrder.TRANSLUCENT)
          m.setDepthTest(DepthTest.LESS_OR_EQUAL)
          m.setDepthWrite(DepthWrite.DISABLE)
          m.setAttribute(ALBEDO_FACTOR, Vector4(0f, 0f, 0f, 1f))
          glowMaterials += m
        }
      }
      if (!glowOn) g.setComponent(Visible(false))
      glowLayers += g
    }
    return e
  }

  /**
   * Shrinks the glow layers a hair towards [eye] (stage coordinates): shrinking about the eye moves
   * every surface straight along your line of sight, so the layer covers exactly the same pixels
   * but sits just in front of the room in depth. A copy at the very same depth z-fights (flashes)
   * on the Quest's GPU; one shrunk about any other point slides out of place as you move.
   */
  fun glowPivot(eye: Vector3) {
    val t = eye * (1f - GLOW_SHRINK)
    glowLayers.forEach {
      it.setComponent(Transform(Pose(t)))
      it.setComponent(Scale(Vector3(GLOW_SHRINK)))
    }
  }

  /** Light from the screen: 0 = dark, 1 = a white frame. */
  fun glow(r: Float, g: Float, b: Float) {
    val v = floatArrayOf(r.coerceIn(0f, 1f), g.coerceIn(0f, 1f), b.coerceIn(0f, 1f))
    // Only touch the materials when the colour really changes (not 25 times a second for nothing),
    // in steps of at most 2 %: a fixed 0.004 was a sixth of a dark scene's light, a visible jump
    if ((0..2).all { abs(v[it] - lastGlow[it]) < maxOf(0.0003f, lastGlow[it] * 0.02f) }) return
    v.copyInto(lastGlow)
    val c = Vector4(v[0], v[1], v[2], 1f)
    glowMaterials.forEach { it.setAttribute(ALBEDO_FACTOR, c) }
    val hc = Vector4(v[0] * HALO_GAIN, v[1] * HALO_GAIN, v[2] * HALO_GAIN, 1f)
    haloMaterials.forEach { it.setAttribute(ALBEDO_FACTOR, hc) }
  }

  /**
   * House lights: 1 = the room as baked, lower darkens it. The screen's glow layer on top isn't
   * dimmed, so while a film plays the hall is lit mostly by the picture.
   */
  fun houseLights(level: Float) {
    val v = level.coerceIn(0f, 1f)
    if (abs(v - house) < maxOf(0.0003f, house * 0.02f) && (v < 1f || house == 1f)) return
    house = v
    val f = Vector4(v, v, v, 1f)
    roomMaterials.forEach { it.setAttribute(ALBEDO_FACTOR, f) }
  }

  /** Draws [e] on top of the room, adding its colour to what's behind (black = see-through), both sides. */
  private fun additive(e: Entity, into: MutableList<SceneMaterial>? = null) {
    sceneObject(e)?.thenAccept { so ->
      so.materials?.forEach { m ->
        m.setBlendMode(BlendMode.ADDITIVE)
        m.setColorWrite(RGB_ONLY)
        m.setSortOrder(SortOrder.TRANSLUCENT)
        m.setDepthWrite(DepthWrite.DISABLE)
        m.setSidedness(MaterialSidedness.DOUBLE_SIDED)
        into?.add(m)
      }
    }
  }

  /**
   * A live fire standing on (x, y, z): three flame tongues [size] metres tall, each playing the
   * flipbook on its own beat and turned to face you, sparks rising, a pool of flickering light on
   * the floor at [floorY] and a real light for the unbaked things (plants). The room's bake already
   * holds the fire's steady light; this adds the movement.
   */
  fun fire(
      x: Float, y: Float, z: Float, size: Float, floorY: Float, poolRadius: Float,
      sparkCount: Int = 8, lightIntensity: Float = 3f, lightRange: Float = 7f,
  ) {
    val phase0 = ((x * 7.3f + z * 3.1f) % 1f + 1f) % 1f   // fires out of step with each other
    listOf(Triple(0f, 1f, 0f), Triple(-0.2f, 0.72f, 0.37f), Triple(0.18f, 0.8f, 0.71f)).forEach { (dx, s, ph) ->
      val at = Vector3(x + dx * size, y, z + dx * size * 0.4f)
      val frames =
          (0 until FIRE_FRAMES).map { i ->
            add(
                Mesh("apk:///models/fire/flame_${i.toString().padStart(2, '0')}.glb".toUri(), hittable = MeshCollision.NoCollision).apply {
                  defaultShaderOverride = SceneMaterial.UNLIT_SHADER
                },
                Transform(Pose(at)),
                Scale(Vector3(size * s)),
                Visible(i == 0),
            ).also { additive(it) }
          }
      flames += Flame(frames, at, size * s, (ph + phase0) % 1f)
    }
    val pool =
        add(
            Mesh("apk:///models/fire/pool.glb".toUri(), hittable = MeshCollision.NoCollision).apply {
              defaultShaderOverride = SceneMaterial.UNLIT_SHADER
            },
            Transform(Pose(Vector3(x, floorY + 0.015f, z))),
            Scale(Vector3(poolRadius * 2, 1f, poolRadius * 2)),
        )
    val poolMats = java.util.concurrent.CopyOnWriteArrayList<SceneMaterial>()
    additive(pool, poolMats)
    fireGlows += Glow(light(x, y + size * 0.5f, z, Vector3(1f, 0.55f, 0.2f), lightIntensity, lightRange), lightIntensity, poolMats, phase0 * 6f)
    repeat(sparkCount) { i ->
      val e = sphere(x, y, z, 0.012f, rgb(1f, 0.62f, 0.22f), glow = true)
      sparks += Spark(e, Vector3(x, y + size * 0.2f, z), size * (1.6f + (i % 3) * 0.5f), 0.45f + (i % 4) * 0.12f, i / sparkCount.toFloat())
    }
  }

  /**
   * A screen for rooms with none baked in (My room, Dark void): a dark matte surface behind the
   * picture, so there is a screen even before a film plays, and a halo of the film's colour on
   * the wall round it, like a TV's bias lighting. [placeScreen] sizes both to the picture.
   */
  fun bareScreen() {
    backing =
        add(
            Mesh("mesh://box".toUri(), hittable = MeshCollision.NoCollision),
            Box(Vector3(-0.5f), Vector3(0.5f)),
            Material().apply { baseColor = Color4(0.035f, 0.035f, 0.04f, 1f) },
            Transform(Pose()),
        )
    halo =
        add(
            Mesh("apk:///models/fire/pool.glb".toUri(), hittable = MeshCollision.NoCollision).apply {
              defaultShaderOverride = SceneMaterial.UNLIT_SHADER
            },
            Transform(Pose()),
        ).also { additive(it, haloMaterials) }
    if (!glowOn) halo?.setComponent(Visible(false))
  }

  /** Fits the bare screen's surface and halo to a picture [w] x [h] centred at [center]. */
  fun placeScreen(center: Vector3, w: Float, h: Float, border: Float) {
    backing?.setComponent(Transform(Pose(center + Vector3(0f, 0f, 0.05f))))
    backing?.setComponent(Scale(Vector3(w + 2 * border + 0.04f, h + 2 * border + 0.04f, 0.04f)))
    // the light pool's quad lies flat: stand it up behind the screen, wider than the picture
    halo?.setComponent(Transform(Pose(center + Vector3(0f, 0f, 0.12f), Quaternion(90f, 0f, 0f))))
    halo?.setComponent(Scale(Vector3(w * 2.1f, 1f, h * 2.6f)))
  }

  /** Every frame: flames step through the flipbook and face [eye] (stage coordinates), sparks rise, light flickers. */
  fun animate(seconds: Float, eye: Vector3) {
    if (flames.isEmpty()) return
    for (fl in flames) {
      val i = (seconds * FIRE_FPS + fl.phase * FIRE_FRAMES).toInt() % FIRE_FRAMES
      val yaw = Math.toDegrees(atan2((eye.x - fl.at.x).toDouble(), (eye.z - fl.at.z).toDouble())).toFloat()
      val e = fl.frames[i]
      e.setComponent(Transform(Pose(fl.at, Quaternion(0f, yaw, 0f))))
      e.setComponent(Scale(Vector3(fl.size * (0.94f + 0.06f * sin(seconds * 5.3f + fl.phase * 6f)))))
      if (i != fl.shown) {
        e.setComponent(Visible(true))
        fl.frames[fl.shown].setComponent(Visible(false))
        fl.shown = i
      }
    }
    for (sp in sparks) {
      val p = (seconds * sp.speed + sp.phase) % 1f
      val drift = 0.14f * p
      sp.e.setComponent(
          Transform(Pose(Vector3(
              sp.from.x + sin(seconds * 1.3f + sp.phase * 9f) * drift,
              sp.from.y + p * sp.rise,
              sp.from.z + cos(seconds * 1.1f + sp.phase * 7f) * drift))))
      sp.e.setComponent(Scale(Vector3(1f - p)))
    }
    for (g in fireGlows) {
      val f = flicker(seconds, g.phase)
      g.light.getComponent<Light>().let { l -> l.intensity = g.intensity * f; g.light.setComponent(l) }
      val c = Vector4(f * 0.85f, f * 0.85f, f * 0.85f, 1f)
      g.pool.forEach { it.setAttribute(ALBEDO_FACTOR, c) }
    }
  }

  fun clear() {
    backing = null
    halo = null
    haloMaterials.clear()
    flames.clear()
    sparks.clear()
    fireGlows.clear()
    glowMaterials.clear()
    roomMaterials.clear()
    house = 1f
    glowLayers.clear()
    lastGlow.fill(-1f)
    made.forEach { it.destroy() }
    made.clear()
  }
}

fun rgb(r: Float, g: Float, b: Float) = Color4(r, g, b, 1f)

/** A hall's best seat and seats on other rows: row k is k rows nearer the screen, [row] metres apart. */
fun rows(row: Float, vararg named: Pair<String, Int>) = listOf("Best" to Vector3(0f)) + named.map { (n, k) -> n to Vector3(0f, 0f, k * row) }

abstract class Room(val id: String, val label: String, val about: String) {
  /** 360° sky photo, or 0 for a plain colour */
  open val sky: Int = 0
  open val skyColor: Color4 = rgb(0f, 0f, 0f)
  open val passthrough = false
  /** No screen baked into the room: Kit.bareScreen draws one. */
  open val bareScreen = false
  open val ambient = Vector3(0.15f)
  /** How far the house lights go down while a film plays: 1 = all the way to the Lights setting, 0 = not at all. */
  open val houseDim = 1f
  abstract val screen: ScreenSpot
  /** Seats to jump to (Settings), as stage (x, 0, z): the walk map gives the floor. The first is
   *  the room's best seat, where it starts you. */
  open val seats: List<Pair<String, Vector3>> = listOf("Best" to Vector3(0f))

  open fun build(k: Kit) {}

  /** Called ~5 times a second while the room is shown (flicker, etc.). */
  open fun tick(seconds: Float) {}
}

object Void : Room("void", "Dark void", "Just the screen in the dark") {
  override val screen = ScreenSpot(6f, 5.5f, 1.5f)
  override val bareScreen = true
  override fun build(k: Kit) { k.bareScreen() }
}

/** Your real room through the cameras, with a big screen in it: the lights go down while the
 *  film plays and your room takes on the film's colours (CinemaActivity.houseLights). */
object MyRoom : Room("room", "My room", "Your real room, lights down") {
  override val passthrough = true
  override val bareScreen = true
  override val screen = ScreenSpot(3.2f, 3f, 1.35f)
  override fun build(k: Kit) { k.bareScreen() }
}

object NightSky : Room("night", "Stargazing deck", "Wooden deck under the Milky Way") {
  override val houseDim = 0.55f   // outdoors: the sky and fires stay, only the near things dim
  override val sky = R.drawable.sky_night
  override val screen = ScreenSpot(9f, 10f, 3.2f)
  override fun build(k: Kit) { k.model("models/stargaze.glb", glow = true) }       // quest/scenes/build_outdoor.py
}

object Sunset : Room("sunset", "Sunset terrace", "Cliff terrace at sunset") {
  override val houseDim = 0.4f   // outdoors: the sky and fires stay, only the near things dim
  override val sky = R.drawable.sky_sunset
  override val ambient = Vector3(0.45f, 0.35f, 0.32f)
  override val screen = ScreenSpot(4.8f, 4.6f, 1.9f)   // rooftop truss screen: build_outdoor.py TERRACE_SCREEN

  override fun build(k: Kit) {
    k.model("models/terrace.glb", glow = true)                                     // quest/scenes/build_outdoor.py
    k.model("models/terrace_plants.glb", baked = false)
  }
}

object Space : Room("space", "Space", "Orbital deck with Earth and Moon") {
  override val houseDim = 0.6f   // the deck dims; Earth, Moon and stars stay
  // Sky: Earth, Moon and Milky Way rendered in Cycles (quest/scenes/build_space.py)
  override val sky = R.drawable.sky_space
  override val ambient = Vector3(0.05f)
  override val screen = ScreenSpot(14f, 14f, 3.8f, floor = 3.8f - 14f * 9f / 32f)      // matches quest/scenes/build_space.py

  override fun build(k: Kit) {
    k.model("models/space_deck.glb", glow = true)   // the orbital auditorium
  }
}

object GrandHall : Room("grand", "Grand IMAX", "Recliners, star-lit ceiling") {
  override val screen = ScreenSpot(20f, 18f, 2.5f, floor = 2.5f - 20f * 9f / 32f, subsInside = true)     // matches quest/scenes/build_halls.py SPOTS
  override val seats = rows(1.65f, "Front" to 6, "Middle" to 3, "Back" to -3)     // build_halls.py ROW
  override fun build(k: Kit) { k.model("models/hall_grand.glb", glow = true) }
}

/** Giant screen: 28 m × 19.6 m in the tall 1.43:1 IMAX shape; films fill its width, standing on its bottom edge. */
object ImaxHall : Room("imax", "IMAX Laser", "The giant 28 m screen") {
  override val screen = ScreenSpot(28f, 17f, 5.4f, height = 28f / 1.43f, floor = 5.4f - 14f / 1.43f, grounded = true)     // matches build_halls.py SPOTS
  override val seats = rows(1.5f, "Front" to 6, "Middle" to 3, "Back" to -8, "Top row" to -13)
  override fun build(k: Kit) { k.model("models/hall_imax.glb", glow = true) }
}

object PalaceHall : Room("palace", "Royal Palace", "1920s gilded picture palace") {
  override val screen = ScreenSpot(13f, 15f, 2.8f, floor = 2.8f - 13f * 9f / 32f)     // matches quest/scenes/build_halls.py SPOTS
  override val seats = rows(1.0f, "Front" to 8, "Middle" to 4, "Back" to -5)
  override fun build(k: Kit) { k.model("models/hall_palace.glb", glow = true) }
}

object LoungeHall : Room("lounge", "Private Lounge", "VIP screening room, plush sofas") {
  override val screen = ScreenSpot(5.6f, 6.2f, 1.75f)
  // The tan sofa at the back is yours; the two front sofas are two steps down (build_halls.py lounge)
  override val seats = listOf("Best" to Vector3(0f), "Front left" to Vector3(-1.6f, 0f, 2.1f), "Front right" to Vector3(1.6f, 0f, 2.1f))
  override fun build(k: Kit) { k.model("models/hall_lounge.glb", glow = true) }
}

object DriveIn : Room("drivein", "Drive-in", "1950s convertible at night") {
  override val houseDim = 0.55f   // outdoors: the sky and fires stay, only the near things dim
  override val sky = R.drawable.sky_drivein
  override val screen = ScreenSpot(18f, 30f, 8.5f)     // matches quest/scenes/build_drivein.py

  override fun build(k: Kit) {
    k.model("models/drivein.glb", glow = true)
    // Fire barrels (quest/scenes/build_drivein.py BARRELS; Blender (x, y) is stage (-x, -y))
    for ((x, z) in listOf(3.6f to 2.2f, -5.4f to 10.8f, 5.6f to 17.5f)) {
      k.fire(x, 0.8f, z, size = 0.75f, floorY = 0f, poolRadius = 3.4f, sparkCount = 6, lightIntensity = 2f, lightRange = 5f)
    }
  }
}

object Jungle : Room("jungle", "Jungle camp", "Campfire in a forest clearing") {
  override val houseDim = 0.55f   // outdoors: the sky and fires stay, only the near things dim
  override val sky = R.drawable.sky_jungle
  override val ambient = Vector3(0.10f, 0.11f, 0.14f)
  override val screen = ScreenSpot(6f, 7.5f, 2.4f)     // matches quest/scenes/build_jungle.py

  override fun build(k: Kit) {
    k.model("models/jungle.glb", glow = true)
    k.model("models/jungle_plants.glb", baked = false)
    // The campfire (Blender (1.9, -1.5) is stage (-1.9, 1.5)): flames from the embers' top
    k.fire(-1.9f, 0.2f, 1.5f, size = 0.95f, floorY = 0f, poolRadius = 3.2f, sparkCount = 12)
  }
}

// Lazy: the room objects call rgb() in this file while they initialise, so an eager list could be
// built before the first room exists and hold a null.
val ROOMS: List<Room> by lazy {
  listOf(GrandHall, ImaxHall, PalaceHall, LoungeHall, DriveIn, Jungle, NightSky, Sunset, Space, Void, MyRoom)
}
