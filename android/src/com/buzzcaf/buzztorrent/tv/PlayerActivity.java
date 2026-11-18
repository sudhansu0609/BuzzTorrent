package com.buzzcaf.buzztorrent.tv;

import android.app.Activity;
import android.content.pm.PackageManager;
import android.content.res.ColorStateList;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.media.MediaPlayer;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.view.Gravity;
import android.view.KeyEvent;
import android.view.MotionEvent;
import android.view.View;
import android.view.WindowManager;
import android.widget.FrameLayout;
import android.widget.LinearLayout;
import android.widget.SeekBar;
import android.widget.TextView;
import android.widget.VideoView;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * Full-screen native player using the TV's own decoders (MKV, HEVC, 1080p, 4K).
 *
 * - Each video comes with all its copies, sharpest first. Before playing, a short Wi-Fi speed
 *   check picks the best copy the connection can keep up with; if it still keeps buffering,
 *   it steps down a quality by itself. ▼ changes quality by hand.
 * - ▲ cycles subtitles (drawn here from a cue list the PC prepares from .srt/.vtt files).
 * - The position is saved on the PC every few seconds, so "Continue watching" works from
 *   any TV or phone, and playback resumes where it stopped.
 * - Without a TV remote (Meta Quest, phones, tablets) the HUD gets tap buttons and a
 *   draggable seek bar. They never take focus, so a remote's keys work as before.
 */
public class PlayerActivity extends Activity {
    public static final String EXTRA = "payload";

    Playlist pl;
    List<Playlist.Item> items;
    int item, version, sub = -1;
    int resumeAt;              // ms to seek to once prepared
    boolean prepared, manualQuality, resumed;
    boolean touchUi, dragging;  // touchUi: tap controls instead of remote hints
    long preparedAt;
    final List<Long> stalls = new ArrayList<>();
    int ticks;

    VideoView video;
    LinearLayout hud;
    TextView hudTitle, hudTime, hudHint, message, subtitle;
    TextView playBtn, ccBtn, qualityBtn, nextBtn;
    TextView likeBtn;
    LinearLayout controls;
    SeekBar bar;
    final Handler ui = new Handler(Looper.getMainLooper());
    final Runnable tick = new Runnable() {
        @Override
        public void run() {
            updateHud();
            drawSubtitle();
            if (++ticks % 75 == 0 && prepared && video.isPlaying()) saveProgress(false);   // every 15 s
            ui.postDelayed(this, 200);
        }
    };
    final Runnable hideHud = () -> {
        if (video.isPlaying() && !dragging) hud.setVisibility(View.GONE);
    };
    final Runnable hideMessage = () -> {
        if (prepared) message.setVisibility(View.GONE);
    };

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON | WindowManager.LayoutParams.FLAG_FULLSCREEN);
        touchUi = !getPackageManager().hasSystemFeature(PackageManager.FEATURE_LEANBACK);
        pl = Playlist.parse(this, getIntent().getStringExtra(EXTRA));
        if (pl == null) {
            finish();
            return;
        }
        items = pl.items;
        item = pl.index;
        buildUi();
        start(item);
        ui.post(tick);
    }

    // ---------------------------------------------------------------- layout
    int dp(float v) {
        return Math.round(v * getResources().getDisplayMetrics().density);
    }

    TextView text(float sp, int color, boolean bold) {
        TextView t = new TextView(this);
        t.setTextSize(sp);
        t.setTextColor(color);
        if (bold) t.setTypeface(Typeface.DEFAULT_BOLD);
        return t;
    }

    void buildUi() {
        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.BLACK);
        video = new VideoView(this);
        root.addView(video, new FrameLayout.LayoutParams(-1, -1, Gravity.CENTER));

        subtitle = text(26, Color.WHITE, true);
        subtitle.setGravity(Gravity.CENTER);
        subtitle.setShadowLayer(6, 0, 2, Color.BLACK);
        subtitle.setPadding(dp(60), 0, dp(60), 0);
        FrameLayout.LayoutParams sl = new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM | Gravity.CENTER_HORIZONTAL);
        sl.bottomMargin = dp(48);
        root.addView(subtitle, sl);

        message = text(20, Color.WHITE, true);
        message.setGravity(Gravity.CENTER);
        message.setPadding(dp(48), dp(24), dp(48), dp(24));
        GradientDrawable pill = new GradientDrawable();
        pill.setColor(0xCC151A24);
        pill.setCornerRadius(dp(16));
        message.setBackground(pill);
        root.addView(message, new FrameLayout.LayoutParams(-2, -2, Gravity.CENTER));

        hud = new LinearLayout(this);
        hud.setOrientation(LinearLayout.VERTICAL);
        hud.setPadding(dp(48), dp(40), dp(48), dp(28));
        hud.setBackground(new GradientDrawable(GradientDrawable.Orientation.BOTTOM_TOP, new int[]{0xE6000000, 0x00000000}));
        hudTitle = text(20, Color.WHITE, true);
        bar = new SeekBar(this);
        bar.setMax(1000);
        bar.setFocusable(false);                    // ◀ ▶ on a remote skip; only touch drags the bar
        bar.setProgressTintList(ColorStateList.valueOf(0xFFFFC531));
        bar.setThumbTintList(ColorStateList.valueOf(0xFFFFC531));
        bar.setPadding(0, dp(6), 0, dp(6));
        bar.setOnSeekBarChangeListener(new SeekBar.OnSeekBarChangeListener() {
            @Override
            public void onProgressChanged(SeekBar b, int p, boolean fromUser) {
                if (!fromUser || !prepared) return;
                int dur = video.getDuration();
                hudTime.setText(time((int) ((long) dur * p / 1000)) + " / " + time(dur));
            }

            @Override
            public void onStartTrackingTouch(SeekBar b) {
                dragging = true;
                ui.removeCallbacks(hideHud);
            }

            @Override
            public void onStopTrackingTouch(SeekBar b) {
                dragging = false;
                if (prepared) video.seekTo((int) ((long) video.getDuration() * b.getProgress() / 1000));
                showHud();
            }
        });
        LinearLayout row = new LinearLayout(this);
        hudTime = text(14, 0xFFB0B7C8, false);
        hudHint = text(14, 0xFF7D869B, false);
        hudHint.setGravity(Gravity.END);
        row.addView(hudTime, new LinearLayout.LayoutParams(0, -2, 1));
        row.addView(hudHint, new LinearLayout.LayoutParams(0, -2, 3));
        controls = new LinearLayout(this);
        controls.setGravity(Gravity.CENTER);
        controls.setPadding(0, dp(14), 0, 0);
        controls.addView(button("« 10s", v -> seekBy(-10000)));
        playBtn = button("❚❚  Pause", v -> togglePlay());
        controls.addView(playBtn);
        controls.addView(button("10s »", v -> seekBy(10000)));
        ccBtn = button("CC", v -> cycleSubtitle());
        controls.addView(ccBtn);
        qualityBtn = button("Quality", v -> nextQuality());
        controls.addView(qualityBtn);
        likeBtn = button("♡ Like", v -> toggleLike());
        controls.addView(likeBtn);
        nextBtn = button("Next ⏭", v -> {
            if (item + 1 < items.size()) { saveProgress(false); start(item + 1); }
        });
        controls.addView(nextBtn);
        controls.addView(button("✕  Close", v -> finish()));
        hud.addView(hudTitle);
        hud.addView(bar, new LinearLayout.LayoutParams(-1, -2));
        hud.addView(row);
        hud.addView(controls);
        root.addView(hud, new FrameLayout.LayoutParams(-1, -2, Gravity.BOTTOM));
        setContentView(root);
        applyTouchUi();
        // A tap on the picture shows or hides the controls
        video.setOnClickListener(v -> {
            if (hud.getVisibility() == View.VISIBLE && video.isPlaying()) hud.setVisibility(View.GONE);
            else showHud();
        });

        video.setOnPreparedListener(mp -> {
            prepared = true;
            preparedAt = System.currentTimeMillis();
            message.setVisibility(View.GONE);
            mp.setOnInfoListener((p, what, extra) -> {
                if (what == MediaPlayer.MEDIA_INFO_BUFFERING_START) {
                    show("Buffering…");
                    stalled();
                } else if (what == MediaPlayer.MEDIA_INFO_BUFFERING_END) {
                    message.setVisibility(View.GONE);
                }
                return false;
            });
            Playlist.Item it = items.get(item);
            if (resumeAt == 0 && !resumed && it.resume > 0) {
                resumeAt = (int) (it.resume * 1000);
                flash("Resumed from " + time(resumeAt) + (touchUi ? ". Drag the bar to go back" : ". Hold ◀ to go back"));
            }
            resumed = true;
            if (resumeAt > 0) video.seekTo(resumeAt);
            resumeAt = 0;
            video.start();
            showHud();
        });
        video.setOnErrorListener((mp, what, extra) -> {
            Playlist.Item it = items.get(item);
            int pos = prepared ? video.getCurrentPosition() : resumeAt;
            if (version + 1 < it.urls.size()) {
                flash(label(it, version) + " can't play on this device. Trying " + label(it, version + 1) + "…");
                play(item, version + 1, pos);
            } else {
                show("This video can't play on this device.\n" + (touchUi ? "Tap ✕ Close" : "Press Back") + " to choose another copy.");
            }
            return true;
        });
        video.setOnCompletionListener(mp -> {
            saveProgress(true);
            if (item + 1 < items.size()) start(item + 1);
            else finish();
        });
    }

    // -------------------------------------------------------------- playback
    String label(Playlist.Item it, int v) {
        return it.label(v);
    }

    /** Starts an item: picks the quality the Wi-Fi can carry, then plays. */
    void start(int i) {
        item = i;
        sub = -1;
        resumed = false;
        Playlist.Item it = items.get(i);
        if (it.startSub >= 0 && it.startSub < it.subs.size()) {
            sub = it.startSub;
            Playlist.Sub chosen = it.subs.get(sub);
            if (chosen.text == null && !chosen.loading) loadSub(chosen);
        }
        boolean remote = it.urls.get(0).startsWith("https://");
        if (manualQuality || it.urls.size() < 2 || !remote) {
            play(i, manualQuality ? Math.min(version, it.urls.size() - 1) : 0, 0);
            return;
        }
        show("Checking your Wi-Fi speed…");
        new Thread(() -> {
            double mbps = Playlist.measureMbps(it.urls.get(0));
            final int chosen = it.pickFor(mbps);
            final String note = mbps <= 0 ? "" : String.format(Locale.ROOT, "Wi-Fi ≈ %.0f Mbps · playing %s", mbps, label(it, chosen))
                    + (chosen > 0 ? " (" + label(it, 0) + " needs more). " + (touchUi ? "Tap Quality" : "▼") + " to change" : "");
            runOnUiThread(() -> {
                if (isFinishing()) return;
                play(i, chosen, 0);
                if (!note.isEmpty()) flash(note);
            });
        }, "speedtest").start();
    }

    void play(int i, int v, int positionMs) {
        item = i;
        version = v;
        prepared = false;
        resumeAt = positionMs;
        stalls.clear();
        Playlist.Item it = items.get(i);
        show("Loading " + label(it, v) + "…");
        video.setVideoURI(Uri.parse(it.urls.get(v)));
        showHud();
    }

    /** Keeps buffering? Step down one quality (unless the viewer picked one by hand). */
    void stalled() {
        long now = System.currentTimeMillis();
        if (now - preparedAt < 15000) return;                 // the first seconds always buffer
        stalls.add(now);
        while (!stalls.isEmpty() && now - stalls.get(0) > 120000) stalls.remove(0);
        Playlist.Item it = items.get(item);
        if (stalls.size() >= 3 && !manualQuality && version + 1 < it.urls.size()) {
            flash("Your Wi-Fi can't keep up. Switching to " + label(it, version + 1));
            play(item, version + 1, video.getCurrentPosition());
        }
    }

    // ------------------------------------------------------------- subtitles
    void cycleSubtitle() {
        Playlist.Item it = items.get(item);
        if (it.subs.isEmpty()) {
            flash("No subtitles for this video");
            return;
        }
        sub = sub + 1 >= it.subs.size() ? -1 : sub + 1;
        subtitle.setText("");
        if (sub < 0) {
            flash("Subtitles off");
            return;
        }
        Playlist.Sub s = it.subs.get(sub);
        flash("Subtitles: " + s.label);
        if (s.text == null && !s.loading) loadSub(s);
    }

    void loadSub(Playlist.Sub s) {
        Playlist.loadSub(s, () -> runOnUiThread(() -> flash("Couldn't load the subtitles")));
    }

    void drawSubtitle() {
        if (sub < 0 || !prepared) {
            if (subtitle.length() > 0) subtitle.setText("");
            return;
        }
        Playlist.Sub s = items.get(item).subs.get(sub);
        if (s.text == null) return;
        String line = Playlist.cueAt(s, video.getCurrentPosition() / 1000.0);
        if (!line.contentEquals(subtitle.getText())) subtitle.setText(line);
    }

    // -------------------------------------------------------------- progress
    void saveProgress(boolean finished) {
        if (items == null || items.isEmpty()) return;
        Playlist.Item it = items.get(item);
        int dur = prepared ? video.getDuration() : 0;
        int pos = finished ? dur : (prepared ? video.getCurrentPosition() : 0);
        pl.saveProgress(it, label(it, version), pos, dur);
    }

    // ------------------------------------------------------------------- HUD
    void show(String msg) {
        ui.removeCallbacks(hideMessage);
        message.setText(msg);
        message.setVisibility(View.VISIBLE);
    }

    void flash(String msg) {
        show(msg);
        ui.postDelayed(hideMessage, 3500);
    }

    static String time(int ms) {
        return Playlist.time(ms);
    }

    void updateHud() {
        if (video == null || items.isEmpty()) return;
        Playlist.Item it = items.get(item);
        String name = items.size() > 1 ? pl.title + " · " + it.name : pl.title;
        String subLabel = sub >= 0 ? " · CC " + it.subs.get(sub).label : "";
        hudTitle.setText(name + "   [" + label(it, version) + (manualQuality ? "" : " auto") + subLabel + "]");
        if (touchUi) updateButtons(it);
        if (dragging) return;                        // the bar and time show where the drag will land
        int dur = prepared ? video.getDuration() : 0, pos = prepared ? video.getCurrentPosition() : 0;
        bar.setProgress(dur > 0 ? (int) (1000L * pos / dur) : 0);
        hudTime.setText(time(pos) + " / " + time(dur));
        StringBuilder hint = new StringBuilder("OK pause · ◀ ▶ skip");
        if (!it.subs.isEmpty()) hint.append(" · ▲ subtitles");
        if (it.urls.size() > 1) hint.append(" · ▼ quality");
        if (items.size() > 1) hint.append(" · ⏭ next");
        if (pl.like != null) hint.append(" · Menu ♥ like");
        hint.append(" · Back");
        hudHint.setText(hint);
    }

    void showHud() {
        updateHud();
        hud.setVisibility(View.VISIBLE);
        ui.removeCallbacks(hideHud);
        ui.postDelayed(hideHud, touchUi ? 6000 : 4000);
    }

    // --------------------------------------------------------- tap controls
    TextView button(String label, View.OnClickListener onClick) {
        TextView b = text(17, Color.WHITE, true);
        b.setText(label);
        b.setSingleLine(true);
        b.setGravity(Gravity.CENTER);
        b.setPadding(dp(20), dp(10), dp(20), dp(10));
        b.setMinWidth(dp(64));
        GradientDrawable bg = new GradientDrawable();
        bg.setColor(0xCC232A38);
        bg.setStroke(dp(1), 0x55FFFFFF);
        bg.setCornerRadius(dp(24));
        b.setBackground(bg);
        b.setFocusable(false);                      // a remote's OK keeps meaning play/pause
        b.setOnClickListener(v -> {
            onClick.onClick(v);
            showHud();
        });
        LinearLayout.LayoutParams lp = new LinearLayout.LayoutParams(-2, -2);
        lp.setMargins(dp(6), 0, dp(6), 0);
        b.setLayoutParams(lp);
        return b;
    }

    void applyTouchUi() {
        controls.setVisibility(touchUi ? View.VISIBLE : View.GONE);
        hudHint.setVisibility(touchUi ? View.GONE : View.VISIBLE);
    }

    static void setIfChanged(TextView t, String s) {
        if (!s.contentEquals(t.getText())) t.setText(s);
    }

    static void showIf(View v, boolean show) {
        int want = show ? View.VISIBLE : View.GONE;
        if (v.getVisibility() != want) v.setVisibility(want);
    }

    void updateButtons(Playlist.Item it) {
        setIfChanged(playBtn, video.isPlaying() ? "❚❚  Pause" : "▶  Play");
        showIf(ccBtn, !it.subs.isEmpty());
        if (!it.subs.isEmpty()) setIfChanged(ccBtn, sub >= 0 ? "CC: " + it.subs.get(sub).label : "CC: Off");
        showIf(qualityBtn, it.urls.size() > 1);
        setIfChanged(qualityBtn, "Quality: " + label(it, version));
        showIf(nextBtn, item + 1 < items.size());
        showIf(likeBtn, pl.like != null);
        setIfChanged(likeBtn, pl.liked == 1 ? "♥ Liked" : "♡ Like");
    }

    /** ♥ while watching: the PC remembers it and lines up similar titles under "For you". */
    void toggleLike() {
        if (pl == null || pl.like == null) return;
        show("♥ …");
        pl.toggleLike(liked -> ui.post(() -> {
            if (liked == null) flash("Couldn't reach the PC to save the ♥");
            else flash(liked ? "♥ Liked. Picks like it will appear under ♥ For you" : "Removed from your likes");
            if (touchUi && !items.isEmpty()) updateButtons(items.get(item));
        }));
    }

    void togglePlay() {
        if (video.isPlaying()) { video.pause(); saveProgress(false); } else video.start();
        showHud();
    }

    /** Any touch (Quest controller or hand, finger, mouse) switches to tap controls and keeps them up. */
    @Override
    public boolean dispatchTouchEvent(MotionEvent ev) {
        if (!touchUi && controls != null) {
            touchUi = true;
            applyTouchUi();
        }
        if (ev.getActionMasked() == MotionEvent.ACTION_DOWN && hud != null && hud.getVisibility() == View.VISIBLE && !dragging) {
            ui.removeCallbacks(hideHud);
            ui.postDelayed(hideHud, 6000);
        }
        return super.dispatchTouchEvent(ev);
    }

    void seekBy(int ms) {
        if (!prepared) return;
        int dur = video.getDuration();
        video.seekTo(Math.max(0, Math.min(dur > 0 ? dur - 1000 : Integer.MAX_VALUE, video.getCurrentPosition() + ms)));
        showHud();
    }

    /** ▼: next lower quality, wrapping back to the best. Turns automatic switching off. */
    void nextQuality() {
        Playlist.Item it = items.get(item);
        if (it.urls.size() < 2) {
            flash("Only one copy of this video");
            return;
        }
        manualQuality = true;
        int v = (version + 1) % it.urls.size();
        flash("Quality: " + label(it, v));
        play(item, v, prepared ? video.getCurrentPosition() : resumeAt);
    }

    @Override
    public boolean onKeyDown(int keyCode, KeyEvent event) {
        int step = event.getRepeatCount() > 2 ? 30000 : 10000;
        switch (keyCode) {
            case KeyEvent.KEYCODE_DPAD_CENTER:
            case KeyEvent.KEYCODE_ENTER:
            case KeyEvent.KEYCODE_SPACE:
            case KeyEvent.KEYCODE_MEDIA_PLAY_PAUSE:
                if (event.getRepeatCount() == 0) togglePlay();
                return true;
            case KeyEvent.KEYCODE_MEDIA_PLAY:
                video.start(); showHud(); return true;
            case KeyEvent.KEYCODE_MEDIA_PAUSE:
                video.pause(); saveProgress(false); showHud(); return true;
            case KeyEvent.KEYCODE_DPAD_LEFT:
                seekBy(-step); return true;
            case KeyEvent.KEYCODE_DPAD_RIGHT:
                seekBy(step); return true;
            case KeyEvent.KEYCODE_MEDIA_REWIND:
                seekBy(-30000); return true;
            case KeyEvent.KEYCODE_MEDIA_FAST_FORWARD:
                seekBy(30000); return true;
            case KeyEvent.KEYCODE_DPAD_UP:
            case KeyEvent.KEYCODE_CAPTIONS:
                if (event.getRepeatCount() == 0) cycleSubtitle();
                showHud();
                return true;
            case KeyEvent.KEYCODE_DPAD_DOWN:
                if (event.getRepeatCount() == 0) nextQuality();
                return true;
            case KeyEvent.KEYCODE_MEDIA_NEXT:
                if (item + 1 < items.size()) { saveProgress(false); start(item + 1); }
                return true;
            case KeyEvent.KEYCODE_MENU:
            case KeyEvent.KEYCODE_BOOKMARK:
            case KeyEvent.KEYCODE_BUTTON_Y:
                if (event.getRepeatCount() == 0) toggleLike();
                showHud();
                return true;
            case KeyEvent.KEYCODE_MEDIA_PREVIOUS:
                if (item > 0) { saveProgress(false); start(item - 1); }
                return true;
            default:
                return super.onKeyDown(keyCode, event);
        }
    }

    @Override
    protected void onPause() {
        super.onPause();
        if (video != null && prepared) saveProgress(false);
        if (video != null && video.isPlaying()) video.pause();
    }

    @Override
    protected void onDestroy() {
        ui.removeCallbacksAndMessages(null);
        if (video != null) video.stopPlayback();
        super.onDestroy();
    }
}
