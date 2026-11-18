package com.buzzcaf.buzztorrent.vr

import android.content.Context
import android.opengl.GLES20
import androidx.media3.common.util.GlProgram
import androidx.media3.common.util.GlUtil
import androidx.media3.common.util.Size
import androidx.media3.common.util.UnstableApi
import androidx.media3.effect.BaseGlShaderProgram
import androidx.media3.effect.GlEffect
import androidx.media3.effect.GlShaderProgram
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * A pass-through video effect that also measures the film's average colour a few times a second,
 * so the room can be lit by the picture (bright explosions, blue night scenes, dark cuts).
 * Each sampled frame is also drawn into a tiny 32×18 framebuffer and read back; [onColor] gets
 * linear-ish RGB in 0..1 on the video processing thread. Every one of those pixels averages 8×8
 * points across its patch of the picture: one point each (a plain shrink) was so noisy that the
 * room's light flickered with every small movement in the film.
 */
@UnstableApi
class ScreenSampler(private val onColor: (Float, Float, Float) -> Unit) : GlEffect {
  override fun toGlShaderProgram(context: Context, useHdr: Boolean): GlShaderProgram = Program(useHdr)

  private inner class Program(useHdr: Boolean) : BaseGlShaderProgram(useHdr, 1) {
    private val program =
        GlProgram(VERTEX, FRAGMENT).apply {
          setBufferAttribute("aFramePosition", GlUtil.getNormalizedCoordinateBounds(), GlUtil.HOMOGENEOUS_COORDINATE_VECTOR_SIZE)
        }
    private val average =
        GlProgram(VERTEX, AVERAGE).apply {
          setBufferAttribute("aFramePosition", GlUtil.getNormalizedCoordinateBounds(), GlUtil.HOMOGENEOUS_COORDINATE_VECTOR_SIZE)
        }
    private val pixels = ByteBuffer.allocateDirect(W * H * 4).order(ByteOrder.nativeOrder())
    private var smallTex = 0
    private var smallFbo = 0
    private var frames = 0

    override fun configure(inputWidth: Int, inputHeight: Int): Size = Size(inputWidth, inputHeight)

    override fun drawFrame(inputTexId: Int, presentationTimeUs: Long) {
      if (frames++ % EVERY == 0) sample(inputTexId)
      program.use()
      program.setSamplerTexIdUniform("uTexSampler", inputTexId, 0)
      program.bindAttributesAndUniforms()
      GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4) // the frame itself, unchanged
    }

    private fun sample(inputTexId: Int) {
      val fbo = IntArray(1)
      val viewport = IntArray(4)
      GLES20.glGetIntegerv(GLES20.GL_FRAMEBUFFER_BINDING, fbo, 0)
      GLES20.glGetIntegerv(GLES20.GL_VIEWPORT, viewport, 0)
      if (smallTex == 0) {
        smallTex = GlUtil.createTexture(W, H, false)
        smallFbo = GlUtil.createFboForTexture(smallTex)
      }
      GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, smallFbo)
      GLES20.glViewport(0, 0, W, H)
      average.use()
      average.setSamplerTexIdUniform("uTexSampler", inputTexId, 0)
      average.setFloatsUniform("uCell", floatArrayOf(1f / W, 1f / H))
      average.bindAttributesAndUniforms()
      GLES20.glDrawArrays(GLES20.GL_TRIANGLE_STRIP, 0, 4)
      pixels.rewind()
      GLES20.glReadPixels(0, 0, W, H, GLES20.GL_RGBA, GLES20.GL_UNSIGNED_BYTE, pixels)
      GLES20.glBindFramebuffer(GLES20.GL_FRAMEBUFFER, fbo[0])
      GLES20.glViewport(viewport[0], viewport[1], viewport[2], viewport[3])
      var r = 0L
      var g = 0L
      var b = 0L
      for (i in 0 until W * H) {
        r += pixels.get(i * 4).toInt() and 0xFF
        g += pixels.get(i * 4 + 1).toInt() and 0xFF
        b += pixels.get(i * 4 + 2).toInt() and 0xFF
      }
      val n = 255f * W * H
      onColor(r / n, g / n, b / n)
    }

    override fun release() {
      super.release()
      program.delete()
      average.delete()
      if (smallFbo != 0) GLES20.glDeleteFramebuffers(1, intArrayOf(smallFbo), 0)
      if (smallTex != 0) GLES20.glDeleteTextures(1, intArrayOf(smallTex), 0)
    }
  }

  companion object {
    private const val W = 32
    private const val H = 18
    private const val EVERY = 5 // frames between samples: ~5–12 a second

    private const val VERTEX =
        """
        attribute vec4 aFramePosition;
        varying vec2 vTexSamplingCoord;
        void main() {
          gl_Position = aFramePosition;
          vTexSamplingCoord = aFramePosition.xy * 0.5 + 0.5;
        }
        """

    private const val FRAGMENT =
        """
        precision mediump float;
        uniform sampler2D uTexSampler;
        varying vec2 vTexSamplingCoord;
        void main() {
          gl_FragColor = texture2D(uTexSampler, vTexSamplingCoord);
        }
        """

    /** One small pixel: the mean of 8×8 points spread over its patch (uCell) of the frame. */
    private const val AVERAGE =
        """
        precision mediump float;
        uniform sampler2D uTexSampler;
        uniform vec2 uCell;
        varying vec2 vTexSamplingCoord;
        void main() {
          vec4 sum = vec4(0.0);
          for (int y = 0; y < 8; y++) {
            for (int x = 0; x < 8; x++) {
              vec2 at = (vec2(float(x), float(y)) + 0.5) / 8.0 - 0.5;
              sum += texture2D(uTexSampler, vTexSamplingCoord + at * uCell);
            }
          }
          gl_FragColor = sum / 64.0;
        }
        """
  }
}
