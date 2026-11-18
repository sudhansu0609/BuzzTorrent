package com.buzzcaf.buzztorrent.vr

import android.content.Context
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.math.roundToInt

/**
 * Where you can stand in a room, and how high the floor is there: a 25 cm grid made by
 * quest/scenes/build_walk.py from the room's model, in stage coordinates. Walls, posts and drops
 * are holes; seats and sofas aren't (walking into a seat is how you sit in it). The grid's x is
 * Blender x, which the SDK mirrors when it loads a glTF: stage x is -Blender x.
 */
class Walk private constructor(
    private val x0: Float,
    private val z0: Float,
    private val cell: Float,
    private val nx: Int,
    private val nz: Int,
    private val mm: ShortArray,
) {
  /** Floor height at (x, z) in metres, or null where you can't stand. */
  fun floor(x: Float, z: Float): Float? {
    val i = ((-x - x0) / cell).roundToInt()
    val j = ((z - z0) / cell).roundToInt()
    if (i !in 0 until nx || j !in 0 until nz) return null
    val v = mm[j * nx + i]
    return if (v == BLOCKED) null else v / 1000f
  }

  companion object {
    private const val BLOCKED: Short = -32768

    /** assets/walk/<room id>.bin, or null for rooms without one (void, passthrough). */
    fun load(context: Context, id: String): Walk? =
        try {
          context.assets.open("walk/$id.bin").use { input ->
            val b = ByteBuffer.wrap(input.readBytes()).order(ByteOrder.LITTLE_ENDIAN)
            val magic = ByteArray(4).also { b.get(it) }
            if (String(magic, Charsets.US_ASCII) != "WLK1") return null
            val x0 = b.float
            val z0 = b.float
            val cell = b.float
            val nx = b.int
            val nz = b.int
            val mm = ShortArray(nx * nz).also { b.asShortBuffer().get(it) }
            Walk(x0, z0, cell, nx, nz, mm)
          }
        } catch (e: java.io.IOException) {
          null
        }
  }
}
