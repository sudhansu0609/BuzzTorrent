package com.buzzcaf.buzztorrent.tv;

import android.content.Context;
import android.net.Uri;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.InputStream;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/**
 * What a player is asked to play, and the parts of playing it that don't depend on the screen:
 * the payload from the TV page (copies sharpest first, subtitles, resume point), the Wi-Fi check,
 * subtitle cues and saving the position on the PC. Used by the TV player and the Quest cinema.
 */
public class Playlist {
    public static class Sub {
        public String label, url;
        public double[] start, end;
        public String[] text;
        public volatile boolean loading, failed;
    }

    public static class Item {
        public String name, key, thumb;
        public double resume;
        public int startSub = -1;          // subtitles chosen before playing (-1 = off)
        public final List<String> urls = new ArrayList<>(), labels = new ArrayList<>();
        public final List<Long> bitrates = new ArrayList<>();
        public final List<Sub> subs = new ArrayList<>();

        public String label(int v) {
            String l = labels.get(v);
            return l == null || l.isEmpty() ? "This copy" : l;
        }

        /** Rough bandwidth a copy needs: its real bitrate when known, else by resolution. */
        public double needMbps(int v) {
            long bps = bitrates.get(v);
            if (bps > 0) return bps / 1e6 * 1.2;
            String l = labels.get(v);
            switch (l == null ? "" : l) {
                case "8K": return 60;
                case "4K": return 20;
                case "1080p": return 6;
                case "720p": return 3;
                case "480p": return 1.5;
                case "Low": return 0.8;
                default: return 4;
            }
        }

        /** The sharpest copy a connection of `mbps` can keep up with (0 = unknown: the best). */
        public int pickFor(double mbps) {
            if (mbps <= 0) return 0;
            for (int v = 0; v < urls.size(); v++) {
                if (needMbps(v) <= mbps / 1.25) return v;
            }
            return urls.size() - 1;
        }
    }

    public String title = "", progressUrl = "";
    public int index;
    /** ♥ button: where to post the like, and the title as the PC knows it (null = no button). */
    public JSONObject like;
    public volatile int liked = -1;    // -1 unknown, 0 no, 1 yes (after the first press)
    public final List<Item> items = new ArrayList<>();
    private final Context context;

    private Playlist(Context context) {
        this.context = context;
    }

    String serverBase() {
        return context.getSharedPreferences("buzztv", Context.MODE_PRIVATE).getString("server", "");
    }

    /** Only archive.org, this PC's /api/tv/ and the app's own downloads may play. */
    boolean allowedUrl(String u) {
        if (u == null) return false;
        if (MainActivity.ARCHIVE_URL.matcher(u).matches()) return true;
        String server = serverBase();
        if (!server.isEmpty() && u.startsWith(server + "/api/tv/")) return true;      // this PC's library / subtitles
        if (!u.startsWith("file://")) return false;
        String path = Uri.parse(u).getPath();
        return path != null && new TvDownloads(context).inOurDirs(new File(path));
    }

    /** Parses the TV page's payload; null if it's broken or nothing in it may play. */
    public static Playlist parse(Context context, String json) {
        Playlist p = new Playlist(context);
        try {
            JSONObject o = new JSONObject(json);
            p.title = o.optString("title", "");
            p.index = o.optInt("index", 0);
            String prog = o.optString("progress", "");
            if (p.allowedUrl(prog)) p.progressUrl = prog;
            JSONObject like = o.optJSONObject("like");
            if (like != null && p.allowedUrl(like.optString("url", "")) && !like.optString("title", "").isEmpty()) p.like = like;
            JSONArray arr = o.getJSONArray("items");
            for (int i = 0; i < arr.length(); i++) {
                JSONObject it = arr.getJSONObject(i);
                Item x = new Item();
                x.name = it.optString("name", "");
                x.key = it.optString("key", "");
                x.thumb = it.optString("thumb", "");
                x.resume = it.optDouble("resume", 0);
                x.startSub = it.optInt("sub", -1);
                JSONArray urls = it.getJSONArray("urls");
                JSONArray labels = it.optJSONArray("labels");
                JSONArray rates = it.optJSONArray("bitrates");
                for (int j = 0; j < urls.length(); j++) {
                    String u = urls.getString(j);
                    if (!p.allowedUrl(u)) continue;
                    x.urls.add(u);
                    x.labels.add(labels != null && j < labels.length() ? labels.optString(j, "") : "");
                    x.bitrates.add(rates != null && j < rates.length() ? rates.optLong(j, 0) : 0L);
                }
                JSONArray subs = it.optJSONArray("subs");
                for (int j = 0; subs != null && j < subs.length(); j++) {
                    JSONObject s = subs.getJSONObject(j);
                    Sub sb = new Sub();
                    sb.label = s.optString("label", "Subtitles");
                    sb.url = s.optString("url", "");
                    if (p.allowedUrl(sb.url)) x.subs.add(sb);
                }
                if (!x.urls.isEmpty()) p.items.add(x);
            }
        } catch (Exception e) {
            return null;
        }
        if (p.items.isEmpty()) return null;
        p.index = Math.max(0, Math.min(p.index, p.items.size() - 1));
        return p;
    }

    /** Downloads up to 4 MB of the video for at most 5 s and returns the speed in Mbps (0 = unknown). */
    public static double measureMbps(String url) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(url).openConnection();
            c.setConnectTimeout(5000);
            c.setReadTimeout(5000);
            c.setRequestProperty("Range", "bytes=0-4194303");
            InputStream in = c.getInputStream();
            byte[] buf = new byte[64 * 1024];
            long first = 0, total = 0;
            long deadline = System.currentTimeMillis() + 5000;
            int n;
            while ((n = in.read(buf)) > 0) {
                if (first == 0) first = System.nanoTime();
                total += n;
                if (total >= 4194304 || System.currentTimeMillis() > deadline) break;
            }
            double secs = (System.nanoTime() - first) / 1e9;
            return total < 256 * 1024 || secs <= 0 ? 0 : total * 8 / secs / 1e6;
        } catch (Exception e) {
            return 0;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    /** Fetches a subtitle's cue list (prepared by the PC) in the background. */
    public static void loadSub(Sub s, Runnable onFail) {
        s.loading = true;
        new Thread(() -> {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(s.url).openConnection();
                c.setConnectTimeout(6000);
                c.setReadTimeout(15000);
                InputStream in = c.getInputStream();
                ByteArrayOutputStream buf = new ByteArrayOutputStream();
                byte[] b = new byte[16384];
                int n;
                while ((n = in.read(b)) > 0 && buf.size() < 8 * 1024 * 1024) buf.write(b, 0, n);
                JSONArray cues = new JSONObject(buf.toString("UTF-8")).getJSONArray("cues");
                double[] st = new double[cues.length()], en = new double[cues.length()];
                String[] tx = new String[cues.length()];
                for (int i = 0; i < cues.length(); i++) {
                    JSONObject q = cues.getJSONObject(i);
                    st[i] = q.optDouble("start");
                    en[i] = q.optDouble("end");
                    tx[i] = q.optString("text");
                }
                s.start = st;
                s.end = en;
                s.text = tx;
            } catch (Exception e) {
                s.failed = true;
                if (onFail != null) onFail.run();
            } finally {
                s.loading = false;
                if (c != null) c.disconnect();
            }
        }, "subtitles").start();
    }

    /** The subtitle line showing at `seconds`, "" between cues or while loading. */
    public static String cueAt(Sub s, double seconds) {
        if (s == null || s.text == null) return "";
        int lo = 0, hi = s.start.length - 1, found = -1;
        while (lo <= hi) {                                  // last cue starting at or before t
            int mid = (lo + hi) >>> 1;
            if (s.start[mid] <= seconds) { found = mid; lo = mid + 1; } else hi = mid - 1;
        }
        return found >= 0 && seconds <= s.end[found] ? s.text[found] : "";
    }

    /** Saves the position on the PC so "Continue watching" works from any screen. */
    public void saveProgress(Item it, String quality, int posMs, int durMs) {
        if (progressUrl.isEmpty() || it.key.isEmpty() || durMs <= 0) return;
        final String body;
        try {
            body = new JSONObject().put("key", it.key).put("pos", posMs / 1000.0).put("dur", durMs / 1000.0)
                    .put("title", title).put("name", items.size() > 1 ? it.name : "")
                    .put("thumb", it.thumb).put("quality", quality).toString();
        } catch (Exception e) {
            return;
        }
        final String url = progressUrl;
        new Thread(() -> {
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(4000);
                c.setReadTimeout(4000);
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setRequestProperty("X-BuzzTorrent", "1");
                try (OutputStream out = c.getOutputStream()) {
                    out.write(body.getBytes("UTF-8"));
                }
                c.getResponseCode();
            } catch (Exception ignored) {
            } finally {
                if (c != null) c.disconnect();
            }
        }, "progress").start();
    }

    /** Callback for toggleLike: liked = true after a ♥, false after un-liking, null if the PC didn't answer. */
    public interface LikeResult {
        void done(Boolean liked);
    }

    /** ♥ / un-♥ the playing title on the PC (it keeps the likes and builds "For you" from them). */
    public void toggleLike(LikeResult cb) {
        if (like == null) { cb.done(null); return; }
        final String body, url = like.optString("url", "");
        try {
            body = new JSONObject().put("action", "toggle").put("title", like.optString("title", ""))
                    .put("category", like.optString("category", "movies")).put("year", like.opt("year"))
                    .put("thumb", like.optString("thumb", "")).toString();
        } catch (Exception e) {
            cb.done(null);
            return;
        }
        new Thread(() -> {
            Boolean result = null;
            HttpURLConnection c = null;
            try {
                c = (HttpURLConnection) new URL(url).openConnection();
                c.setConnectTimeout(4000);
                c.setReadTimeout(6000);
                c.setRequestMethod("POST");
                c.setDoOutput(true);
                c.setRequestProperty("Content-Type", "application/json");
                c.setRequestProperty("X-BuzzTorrent", "1");
                try (OutputStream out = c.getOutputStream()) {
                    out.write(body.getBytes("UTF-8"));
                }
                if (c.getResponseCode() == 200) {
                    ByteArrayOutputStream buf = new ByteArrayOutputStream();
                    try (InputStream in = c.getInputStream()) {
                        byte[] b = new byte[4096];
                        int n;
                        while ((n = in.read(b)) > 0 && buf.size() < 65536) buf.write(b, 0, n);
                    }
                    result = new JSONObject(buf.toString("UTF-8")).optBoolean("liked", true);
                    liked = result ? 1 : 0;
                }
            } catch (Exception ignored) {
            } finally {
                if (c != null) c.disconnect();
            }
            cb.done(result);
        }, "like").start();
    }

    public static String time(long ms) {
        long s = Math.max(0, ms / 1000);
        long h = s / 3600, m = (s % 3600) / 60, sec = s % 60;
        return h > 0 ? String.format(Locale.ROOT, "%d:%02d:%02d", h, m, sec) : String.format(Locale.ROOT, "%d:%02d", m, sec);
    }
}
