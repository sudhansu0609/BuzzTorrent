"""Streaming to the TV (TorrServer driven over HTTP) and the per-indexer Jackett search.
A small fake TorrServer stands in for the real one."""
import json
import re
import threading
import time
import unittest
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory

from buzz.providers import TorznabProvider
from buzz.streamer import MB, Streamer, StreamError, pick_files
from buzz.tvstate import KEY

H = "a" * 40
MKV = b"\x1a\x45\xdf\xa3" + b"\x00" * 200
FILES = [{"id": 1, "path": "Film/Film.2160p.mkv", "length": 9000 * MB},
         {"id": 2, "path": "Film/Sample/sample.mkv", "length": 30 * MB},
         {"id": 3, "path": "Film/Codec.exe", "length": 2 * MB},
         {"id": 4, "path": "Film/Fake.mkv", "length": 800 * MB}]


class _FakeTorrServer(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, body: bytes, status=200, ctype="application/json"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.headers.get("Authorization") != self.server.auth:
            return self._send(b"unauthorized", 401)
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])) or b"{}")
        if self.path == "/settings":
            return self._send(b"{}")
        if body.get("action") == "add":
            return self._send(json.dumps({"hash": H}).encode())
        if body.get("action") == "get":
            return self._send(json.dumps({"hash": H, "stat": 3, "file_stats": FILES, "active_peers": 7,
                                          "total_peers": 20, "download_speed": 4e6,
                                          "preloaded_bytes": 10, "preload_size": 10}).encode())
        return self._send(b"{}")

    def do_GET(self):
        q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query, keep_blank_values=True)
        if "preload" in q:
            return self._send(b"")
        data = MKV if q.get("index") == ["1"] else b"MZ\x90\x00" + b"\x00" * 200    # file 4 is a renamed program
        m = re.fullmatch(r"bytes=(\d+)-(\d*)", self.headers.get("Range") or "")
        if m:
            data = data[int(m.group(1)):int(m.group(2)) + 1 if m.group(2) else None]
        self._send(data, 206 if m else 200, "video/x-matroska")


class _Alive:
    def poll(self):
        return None


class StreamerTests(unittest.TestCase):
    def setUp(self):
        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), _FakeTorrServer)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.tmp = TemporaryDirectory()
        self.st = Streamer(Path(self.tmp.name), "TorrServer.exe")
        self.st.proc, self.st.port, self.st.auth = _Alive(), self.srv.server_address[1], "Basic secret"
        self.srv.auth = "Basic secret"

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        self.tmp.cleanup()

    def wait_stage(self, index, stages):
        for _ in range(100):
            s = self.st.status(H, index)
            if s["stage"] in stages:
                return s
            time.sleep(0.05)
        self.fail(f"stuck at {s['stage']}")

    def test_only_real_videos_are_listed_and_programs_are_named(self):
        videos, warnings, why = pick_files(FILES)
        self.assertEqual(sorted(v["index"] for v in videos), [1, 4])      # the sample and the .exe are left out
        self.assertTrue(any("Codec.exe" in w for w in warnings))
        self.assertEqual(why, "")
        none, _, why = pick_files([{"id": 1, "path": "Film.rar", "length": 4000 * MB}])
        self.assertEqual(none, [])
        self.assertIn("archive", why)

    def test_a_video_is_checked_buffered_then_streamed(self):
        self.assertEqual(self.st.add("Film", magnet=f"magnet:?xt=urn:btih:{H}"), H)
        self.assertEqual(self.st.status(H, None)["stage"], "choose")
        with self.assertRaises(PermissionError):
            self.st.open(H, 1, None)                     # not checked yet: refused
        self.st.prepare(H, 1)
        s = self.wait_stage(1, ("ready", "error"))
        self.assertEqual(s["stage"], "ready", s)
        conn, resp = self.st.open(H, 1, "bytes=0-3")
        try:
            self.assertEqual(resp.status, 206)
            self.assertEqual(resp.read(), MKV[:4])
        finally:
            conn.close()

    def test_a_renamed_program_is_blocked(self):
        self.st.add("Film", magnet=f"magnet:?xt=urn:btih:{H}")
        self.st.prepare(H, 4)
        s = self.wait_stage(4, ("error", "ready"))
        self.assertEqual(s["stage"], "error")
        self.assertIn("Windows program", s["error"])
        with self.assertRaises(PermissionError):
            self.st.open(H, 4, None)

    def test_bad_hashes_are_refused(self):
        with self.assertRaises(StreamError):
            self.st.status("../../etc", 1)
        with self.assertRaises(StreamError):
            self.st.prepare("x" * 40, 1)

    def test_stream_positions_can_be_saved(self):
        self.assertTrue(KEY.match(f"bt:{H}:1"))
        self.assertFalse(KEY.match("bt:zz:1"))


FEED = """<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0" xmlns:torznab="http://torznab.com/schemas/2015/feed"><channel>
 <item><title>{name} Film 2024 1080p</title><size>2147483648</size>
  <torznab:attr name="infohash" value="{hash}"/><torznab:attr name="seeders" value="5"/>
  <torznab:attr name="category" value="2000"/></item>
</channel></rss>"""
INDEXERS = b"""<?xml version="1.0"?><indexers>
 <indexer id="fast" configured="true"><title>Fast</title></indexer>
 <indexer id="aniRena" configured="true"><title>Mixed case</title></indexer>
 <indexer id="broken" configured="true"><title>Broken</title></indexer>
 <indexer id="../evil" configured="true"><title>Bad id</title></indexer>
</indexers>"""


class _Jackett(BaseHTTPRequestHandler):
    seen: list = []

    def log_message(self, *a):
        pass

    def do_GET(self):
        self.seen.append(self.path)
        if "t=indexers" in self.path:
            body = INDEXERS
        elif "/indexers/broken/" in self.path:
            self.send_response(500)
            self.end_headers()
            return
        elif "/indexers/all/" in self.path:
            time.sleep(1)                                 # the slow aggregate endpoint
            body = FEED.format(name="All", hash="c" * 40).encode()
        else:
            name = self.path.split("/indexers/")[1].split("/")[0]
            body = FEED.format(name=name, hash=("d" if name == "fast" else "e") * 40).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/rss+xml")
        self.end_headers()
        self.wfile.write(body)


class JackettSplitTests(unittest.TestCase):
    def test_each_indexer_is_asked_directly(self):
        srv = ThreadingHTTPServer(("127.0.0.1", 0), _Jackett)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        try:
            url = f"http://127.0.0.1:{srv.server_address[1]}/api/v2.0/indexers/all/results/torznab/api"
            p = TorznabProvider("Jackett", url, "k")
            titles = sorted(r.title for r in p.search("film", "movies", 50))
            self.assertEqual(titles, ["aniRena Film 2024 1080p", "fast Film 2024 1080p"])   # broken one skipped
            self.assertFalse(any("/indexers/all/" in s and "t=search" in s for s in _Jackett.seen))
            self.assertFalse(any("evil" in s for s in _Jackett.seen))
        finally:
            srv.shutdown()
            srv.server_close()


class SubtitleTests(unittest.TestCase):
    def test_subtitles_in_the_torrent_go_with_their_video(self):
        files = [{"id": 1, "path": "Film/Film.1999.1080p.mkv", "length": 4000 * MB},
                 {"id": 2, "path": "Film/Subs/English.srt", "length": 80_000},
                 {"id": 3, "path": "Film/Subs/Hindi.srt", "length": 90_000},
                 {"id": 4, "path": "Film/Subs/huge.srt", "length": 50 * MB}]
        videos, _, _ = pick_files(files)
        self.assertEqual({(x["index"], x["lang"]) for x in videos[0]["subs"]}, {(2, "en"), (3, "hi")})

    def test_online_search_sends_only_the_title_and_ranks_the_exact_release_first(self):
        from buzz import subtitles as subs_mod
        seen = []
        def fake(url):
            seen.append(url)
            return {"status": True, "subtitles": [
                {"lang": "EN", "language": "English", "release_name": "Other.Release", "url": "/subtitle/1-1.zip"},
                {"lang": "EN", "language": "English", "release_name": "Film.1999.1080p", "url": "/subtitle/2-2.zip"},
                {"lang": "EN", "language": "English", "release_name": "x", "url": "https://evil.example/a.zip"}]}
        out = subs_mod.subdl_search(fake, "KEY", "Film", 1999, "Film.1999.1080p.mkv")
        self.assertEqual([o["path"] for o in out], ["/subtitle/2-2.zip", "/subtitle/1-1.zip"])
        self.assertIn("film_name=Film", seen[0])
        self.assertIn("type=movie", seen[0])
        tv = subs_mod.subdl_search(fake, "KEY", "Show", None, "Show.S02E05.mkv")
        self.assertTrue(tv)
        self.assertIn("season_number=2", seen[1])

    def test_zip_downloads_are_size_checked(self):
        import io
        import zipfile
        from buzz import subtitles as subs_mod
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("film.srt", "1\n00:00:01,000 --> 00:00:02,000\nHello\n")
            z.writestr("readme.exe", "MZ")
        self.assertIn(b"Hello", subs_mod.from_zip(buf.getvalue()))
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("bomb.srt", "a" * (subs_mod.MAX_BYTES + 1))
        with self.assertRaises(ValueError):
            subs_mod.from_zip(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
