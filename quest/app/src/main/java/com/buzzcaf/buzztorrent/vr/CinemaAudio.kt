package com.buzzcaf.buzztorrent.vr

import android.content.Context
import android.media.AudioTrack
import android.media.audiofx.AudioEffect
import android.media.audiofx.DynamicsProcessing
import android.media.audiofx.Equalizer
import android.media.audiofx.LoudnessEnhancer
import android.media.audiofx.Virtualizer
import android.os.IBinder
import android.util.Log
import androidx.media3.common.AudioAttributes
import androidx.media3.common.util.UnstableApi
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.audio.AudioSink
import androidx.media3.exoplayer.audio.DefaultAudioSink
import androidx.media3.exoplayer.audio.DefaultAudioTrackProvider

/**
 * The film's sound in the immersive cinema. Horizon OS ties every Java AudioTrack to a
 * "volumetric window" (the app's default one), to play it from that window in your room. The
 * cinema has no such window on show, so the film played silent: its track never went active,
 * while the SDK's own native track (no window) did. Each track here is made with no window.
 */
@UnstableApi
class CinemaRenderers(context: Context) : DefaultRenderersFactory(context) {
  override fun buildAudioSink(context: Context, enableFloatOutput: Boolean, enableAudioOutputPlaybackParams: Boolean): AudioSink =
      DefaultAudioSink.Builder(context)
          .setEnableFloatOutput(enableFloatOutput)
          .setEnableAudioOutputPlaybackParameters(enableAudioOutputPlaybackParams)
          .setAudioTrackProvider(UnwindowedTracks())
          .build()

  private class UnwindowedTracks : DefaultAudioSink.AudioTrackProvider {
    private val tracks = DefaultAudioTrackProvider()

    override fun getAudioTrack(config: AudioSink.AudioTrackConfig, attributes: AudioAttributes, sessionId: Int, context: Context?): AudioTrack =
        tracks.getAudioTrack(config, attributes, sessionId, context).also { unwindow(it) }
  }

  companion object {
    private const val TAG = "BuzzVR"

    /** No window for [track]: Horizon OS's hidden AudioTrack.setVolumetricWindowToken(null). */
    fun unwindow(track: AudioTrack) {
      runCatching {
        AudioTrack::class.java.getMethod("setVolumetricWindowToken", IBinder::class.java).invoke(track, null)
        Log.i(TAG, "audio: track ${track.audioSessionId} unwindowed")
      }.onFailure { Log.w(TAG, "audio: couldn't unwindow the track: $it") }
    }

    /** And no default window for tracks made later in this process. */
    fun clearDefaultWindow() {
      runCatching {
        AudioTrack::class.java.getMethod("setDefaultVolumetricWindowToken", IBinder::class.java).invoke(null, null)
        Log.i(TAG, "audio: default window cleared")
      }.onFailure { Log.w(TAG, "audio: couldn't clear the default window: $it") }
    }
  }
}

/**
 * Sound modes (Settings): Android's audio effects on the film's audio session.
 *  Standard     the film's own mix, untouched
 *  Cinema       fuller bass, a little more air on top, the stereo widened
 *  Clear voice  less rumble, the speech band lifted
 *  Night        quiet parts lifted and loud ones held down, for a low volume
 * An effect the headset doesn't offer is left out: [apply] returns false if any was.
 */
class SoundModes(private val session: Int) {
  private val effects = ArrayList<AudioEffect>()

  fun apply(mode: Int): Boolean {
    release()
    var ok = true
    fun <T : AudioEffect> add(make: () -> T, setUp: T.() -> Unit) {
      runCatching { make().apply { setUp(); setEnabled(true) }.also { effects += it } }
          .onFailure { ok = false; Log.w(TAG, "audio effect ${mode}: $it") }
    }
    when (mode) {
      CINEMA -> {
        add({ Equalizer(0, session) }) { shape { hz -> if (hz < 150) 500 else if (hz > 7000) 200 else 0 } }
        add({ Virtualizer(0, session) }) { if (strengthSupported) setStrength(600.toShort()) }
        add({ LoudnessEnhancer(session) }) { setTargetGain(200) }
      }
      VOICE -> {
        add({ Equalizer(0, session) }) { shape { hz -> if (hz < 200) -400 else if (hz in 900..4500) 500 else 0 } }
        add({ LoudnessEnhancer(session) }) { setTargetGain(300) }
      }
      NIGHT -> add({ DynamicsProcessing(0, session, nightConfig()) }) {}
    }
    Log.i(TAG, "sound mode ${NAMES.getOrNull(mode)}: ${effects.size} effects${if (ok) "" else " (some not available)"}")
    return ok
  }

  fun release() {
    effects.forEach { runCatching { it.setEnabled(false); it.release() } }
    effects.clear()
  }

  /** Sets each band to [gain] (millibels) of its centre frequency, within what the equaliser allows. */
  private fun Equalizer.shape(gain: (Int) -> Int) {
    val (lo, hi) = bandLevelRange.let { it[0].toInt() to it[1].toInt() }
    for (b in 0 until numberOfBands) setBandLevel(b.toShort(), gain(getCenterFreq(b.toShort()) / 1000).coerceIn(lo, hi).toShort())
  }

  /** One-band compressor (4:1 above -30 dB), 10 dB of make-up gain and a limiter, on every channel. */
  private fun nightConfig(): DynamicsProcessing.Config {
    val c = DynamicsProcessing.Config.Builder(DynamicsProcessing.VARIANT_FAVOR_FREQUENCY_RESOLUTION, MAX_CHANNELS,
        false, 0, true, 1, false, 0, true).build()
    val band = DynamicsProcessing.MbcBand(true, 20000f, 10f, 200f, 4f, -30f, 0f, -90f, 1f, 0f, 10f)
    val limiter = DynamicsProcessing.Limiter(true, true, 0, 1f, 60f, 10f, -2f, 0f)
    for (ch in 0 until MAX_CHANNELS) {
      c.setMbcBandByChannelIndex(ch, 0, band)
      c.setLimiterByChannelIndex(ch, limiter)
    }
    return c
  }

  companion object {
    private const val TAG = "BuzzVR"
    const val STANDARD = 0
    const val CINEMA = 1
    const val VOICE = 2
    const val NIGHT = 3
    val NAMES = listOf("Standard", "Cinema", "Clear voice", "Night")
    private const val MAX_CHANNELS = 8     // up to 7.1: extra entries go unused on a stereo film
  }
}
