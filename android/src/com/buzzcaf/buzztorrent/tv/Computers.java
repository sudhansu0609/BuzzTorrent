package com.buzzcaf.buzztorrent.tv;

import android.content.SharedPreferences;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;

/**
 * The computers this app has been paired with (your PC, your Mac…) and which one is in use.
 *
 * "server" in the prefs stays the one in use (everything else reads it); "computers" is the
 * list the PC ⇄ Mac toggle switches between. Each entry is {url, os, id}: os is "windows" or
 * "mac" (from BuzzTorrent's /api/tv/hello), id is the install's random id, so a computer whose
 * address changed (a new DHCP lease) is recognised instead of being saved twice. Shared by the
 * TV app and the Quest app (which also uses it from the VR cinema's browse screen).
 */
public final class Computers {
    static final String KEY = "computers";
    static final int MAX = 6;

    private Computers() {
    }

    /** The saved list, with the paired computer from before this list existed folded in. */
    public static synchronized JSONArray list(SharedPreferences prefs) {
        JSONArray a;
        try {
            a = new JSONArray(prefs.getString(KEY, "[]"));
        } catch (Exception e) {
            a = new JSONArray();
        }
        String server = prefs.getString("server", null);
        if (server != null && indexOfUrl(a, server) < 0) {
            JSONObject o = new JSONObject();
            try {
                o.put("url", server).put("os", "").put("id", "");
            } catch (Exception ignored) {
            }
            a.put(o);
        }
        return a;
    }

    /** {"active": url, "list": [...]} for the page's toggle. */
    public static String json(SharedPreferences prefs) {
        JSONObject o = new JSONObject();
        try {
            o.put("active", prefs.getString("server", ""));
            o.put("list", list(prefs));
        } catch (Exception ignored) {
        }
        return o.toString();
    }

    public static synchronized boolean known(SharedPreferences prefs, String url) {
        return url != null && indexOfUrl(list(prefs), url) >= 0;
    }

    /** Saves (or updates) a computer from its hello answer. Same id at a new address: moved. */
    public static synchronized void remember(SharedPreferences prefs, String url, JSONObject hello) {
        if (url == null) return;
        String os = hello == null ? "" : hello.optString("os", "");
        String id = hello == null ? "" : hello.optString("id", "");
        JSONArray a = list(prefs);
        int at = id.isEmpty() ? -1 : indexOfId(a, id);
        if (at < 0) at = indexOfUrl(a, url);
        JSONArray out = new JSONArray();
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o == null) continue;
            // the same address now answering as another install (a different computer got the IP)
            if (i != at && url.equals(o.optString("url"))) continue;
            if (i == at) {
                try {
                    o.put("url", url);
                    if (!os.isEmpty()) o.put("os", os);
                    if (!id.isEmpty()) o.put("id", id);
                } catch (Exception ignored) {
                }
            }
            out.put(o);
        }
        if (at < 0) {
            JSONObject o = new JSONObject();
            try {
                o.put("url", url).put("os", os).put("id", id);
            } catch (Exception ignored) {
            }
            out.put(o);
        }
        while (out.length() > MAX) out.remove(0);
        prefs.edit().putString(KEY, out.toString()).apply();
    }

    public static synchronized void forget(SharedPreferences prefs, String url) {
        JSONArray a = list(prefs), out = new JSONArray();
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && !o.optString("url").equals(url)) out.put(o);
        }
        SharedPreferences.Editor e = prefs.edit().putString(KEY, out.toString());
        if (url != null && url.equals(prefs.getString("server", null))) e.remove("server");
        e.apply();
    }

    /** The saved id of the computer at url ("" if unknown), to find it again after it moved. */
    public static synchronized String idOf(SharedPreferences prefs, String url) {
        JSONArray a = list(prefs);
        int i = indexOfUrl(a, url);
        return i < 0 ? "" : a.optJSONObject(i).optString("id", "");
    }

    /** Asks base + /api/tv/hello; the answer if it's BuzzTorrent, else null. Never on the UI thread. */
    public static JSONObject hello(String base) {
        HttpURLConnection c = null;
        try {
            c = (HttpURLConnection) new URL(base + "/api/tv/hello").openConnection();
            c.setConnectTimeout(1500);
            c.setReadTimeout(2500);
            if (c.getResponseCode() != 200) return null;
            InputStream in = c.getInputStream();
            ByteArrayOutputStream buf = new ByteArrayOutputStream();
            byte[] b = new byte[2048];
            int n;
            while ((n = in.read(b)) > 0 && buf.size() < 8192) buf.write(b, 0, n);
            JSONObject o = new JSONObject(buf.toString("UTF-8"));
            return "BuzzTorrent".equals(o.optString("app")) ? o : null;
        } catch (Exception e) {
            return null;
        } finally {
            if (c != null) c.disconnect();
        }
    }

    private static int indexOfUrl(JSONArray a, String url) {
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && url.equals(o.optString("url"))) return i;
        }
        return -1;
    }

    private static int indexOfId(JSONArray a, String id) {
        for (int i = 0; i < a.length(); i++) {
            JSONObject o = a.optJSONObject(i);
            if (o != null && id.equals(o.optString("id"))) return i;
        }
        return -1;
    }
}
