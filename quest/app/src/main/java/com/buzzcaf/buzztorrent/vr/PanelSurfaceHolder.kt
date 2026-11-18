package com.buzzcaf.buzztorrent.vr

import android.graphics.Canvas
import android.graphics.Rect
import android.view.Surface
import android.view.SurfaceHolder

/**
 * The cinema screen panel's Surface, together with its size. ExoPlayer can't learn a bare
 * Surface's size, and with a video effect on (ScreenSampler) it then drops every frame
 * ("Output surface and size not set"), leaving the screen blank. A holder reports the size.
 */
class PanelSurfaceHolder(private val surface: Surface, private val width: Int, private val height: Int) : SurfaceHolder {
  override fun getSurface(): Surface = surface

  override fun getSurfaceFrame(): Rect = Rect(0, 0, width, height)

  override fun isCreating(): Boolean = false

  // The panel owns the surface for the activity's whole life: nothing to report
  override fun addCallback(callback: SurfaceHolder.Callback?) {}

  override fun removeCallback(callback: SurfaceHolder.Callback?) {}

  @Deprecated("Deprecated in Java")
  override fun setType(type: Int) {}

  override fun setFixedSize(width: Int, height: Int) {}

  override fun setSizeFromLayout() {}

  override fun setFormat(format: Int) {}

  override fun setKeepScreenOn(screenOn: Boolean) {}

  override fun lockCanvas(): Canvas? = null

  override fun lockCanvas(dirty: Rect?): Canvas? = null

  override fun unlockCanvasAndPost(canvas: Canvas?) {}
}
