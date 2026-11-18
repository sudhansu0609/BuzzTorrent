"""Watch a torrent while it downloads: streaming to the TV.

The BitTorrent work is done by TorrServer (https://github.com/YouROK/TorrServer), an
open-source engine built for exactly this: it fetches a video's pieces in playing order
and keeps them in memory, so playback starts after a short buffer and seeking works.
BuzzTorrent starts it hidden on 127.0.0.1 with a random password, and the TV gets the
video through BuzzTorrent itself (paired TVs and signed links only, like everything else).

Safety, the same rules as the rest of the app:
* only video files are ever streamed, and their first bytes are checked to really be
  video (a renamed program or archive is refused);
* nothing is written to disk: pieces live in TorrServer's memory cache and are dropped
  when the stream closes, so nothing lands in a folder where it could later be opened;
* program files inside a torrent are named in a warning and never fetched or opened;
* TorrServer itself is installed only from its official GitHub release, after its
  SHA-256 matches the one GitHub publishes and the antivirus has scanned it."""
from __future__ import annotations

import base64
import hashlib
import http.client
import json
import os
import platform
import re
import secrets
import socket
import subprocess
import threading
import time
import urllib.parse
from pathlib import Path

from . import av, osutil
from . import subtitles as subs_mod
from .content_scan import DOUBLE_EXT, PROGRAM_EXT, SCRIPT_EXT, VIDEO_EXT, ext_of, sniff
from .safehttp import FetchError, FetchPolicy, fetch

RELEASES = "https://api.github.com/repos/YouROK/TorrServer/releases/latest"
GITHUB = FetchPolicy(("github.com", "api.github.com", "githubusercontent.com"), content_types=("json",),
                     max_bytes=2 * 1024 * 1024, timeout=20)
GITHUB_BIN = FetchPolicy(("github.com", "githubusercontent.com"), max_redirects=4,
                         content_types=("octet-stream", "x-msdownload", "x-executable", "binary"),
                         max_bytes=200 * 1024 * 1024, timeout=120)
MB = 1024 * 1024
MIN_VIDEO = 20 * MB                 # smaller "videos" are samples, trailers or bait
HASH = re.compile(r"^[0-9a-f]{40}$")
ARCHIVE_EXT = {"rar", "zip", "7z", "iso"}
STAT_PRELOAD, STAT_WORKING = 2, 3


class StreamError(ValueError):
    pass


def _asset() -> tuple[str, str] | None:
    """TorrServer's release file for this computer, and the name it's saved under."""
    machine = platform.machine().lower()
    arch = "arm64" if machine in ("arm64", "aarch64") else "amd64" if machine in ("amd64", "x86_64") else None
    if arch is None:
        return None
    if osutil.IS_WIN:
        return f"TorrServer-windows-{arch}.exe", "TorrServer.exe"
    if osutil.IS_MAC:
        return f"TorrServer-darwin-{arch}", "TorrServer"
    return f"TorrServer-linux-{arch}", "TorrServer"


def install_dir() -> Path:
    if osutil.IS_WIN:
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Programs" / "TorrServer"
    if osutil.IS_MAC:
        return Path.home() / "Library" / "Application Support" / "BuzzTorrent" / "TorrServer"
    return Path.home() / ".local" / "share" / "buzztorrent" / "torrserver"


def find_torrserver(configured: str | None = None) -> str | None:
    asset = _asset()
    local = install_dir() / asset[1] if asset else None
    for cand in (configured, local, osutil.which("TorrServer"), osutil.which("torrserver")):
        if cand and Path(cand).is_file():
            return str(cand)
    return None


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _natural(s: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def pick_files(file_stats: list[dict]) -> tuple[list[dict], list[str], str]:
    """The torrent's streamable videos (episodes in order), warnings about anything else
    in it, and why nothing can stream if the list is empty."""
    videos, warnings, archives, subs = [], [], [], {}
    for f in file_stats or []:
        path = str(f.get("path") or "")
        name = path.replace("\\", "/").rsplit("/", 1)[-1]
        ext, size = ext_of(name), int(f.get("length") or 0)
        if ext in PROGRAM_EXT or ext in SCRIPT_EXT or DOUBLE_EXT.search(name):
            warnings.append(f"This torrent also holds a program ({name}). It isn't downloaded or opened: "
                            "only the video streams. Never run files like this.")
        elif subs_mod.is_subtitle(name) and 0 < size <= subs_mod.MAX_BYTES:
            subs[path] = int(f.get("id") or 0)
        elif ext in ARCHIVE_EXT:
            archives.append(name)
        elif ext in VIDEO_EXT and size >= MIN_VIDEO and not (re.search(r"\bsample\b", name, re.I) and size < 400 * MB):
            videos.append({"index": int(f.get("id") or 0), "name": name, "path": path, "size": size})
    videos.sort(key=lambda v: _natural(v["path"]))
    for v in videos:      # subtitle files that came with each video ("Film.mkv" + "Subs/English.srt")
        mine = subs_mod.for_video(v["path"], list(subs), len(videos) == 1)
        labels = {d["file"]: d for d in subs_mod.describe(mine)}
        v["subs"] = [{"index": subs[path], "label": d["label"], "lang": d["lang"]} for path, d in labels.items()]
    why = ""
    if not videos:
        why = ("This copy is packed in an archive (" + archives[0] + "), so it can't stream. Pick another copy, "
               "or use Download on PC.") if archives else "There's no video in this torrent that can stream."
    return videos, warnings[:3], why


class Streamer:
    def __init__(self, data_dir: Path, exe: str | None, cache_mb: int = 512, preload_pct: int = 8):
        self.dir = data_dir / "torrserver"
        self.exe = exe
        self.cache_mb = max(64, min(int(cache_mb), 4096))
        self.preload_pct = max(5, min(int(preload_pct), 60))
        self.lock = threading.RLock()
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.auth = ""
        self.setup = {"state": "idle", "done": 0, "total": 0, "error": ""}
        self.prep: dict[tuple[str, int], dict] = {}      # (hash, file) -> {"stage", "error", "kind"}
        self.private: set[str] = set()                    # hashes from the private section: no traces
        self.titles: dict[str, str] = {}

    @property
    def available(self) -> bool:
        return bool(self.exe)

    # ------------------------------------------------------------ install
    def install_async(self) -> None:
        with self.lock:
            if self.exe or self.setup["state"] in ("downloading", "scanning"):
                return
            self.setup = {"state": "downloading", "done": 0, "total": 0, "error": ""}
        threading.Thread(target=self._install, name="torrserver-install", daemon=True).start()

    def _install(self) -> None:
        try:
            self.exe = self.install()
            self.setup = {"state": "done", "done": 0, "total": 0, "error": ""}
        except (FetchError, OSError, StreamError) as e:
            self.setup = {"state": "error", "done": 0, "total": 0, "error": str(e)}

    def install(self) -> str:
        """Downloads TorrServer's official release, checks it, and returns its path."""
        asset = _asset()
        if not asset:
            raise StreamError(f"Streaming isn't available for this kind of computer ({platform.machine()})")
        want, saved = asset
        rel = json.loads(fetch(RELEASES, GITHUB, accept="application/vnd.github+json"))
        found = next((a for a in rel.get("assets", []) if a.get("name") == want), None)
        digest = str((found or {}).get("digest") or "")
        if not found or not digest.startswith("sha256:"):
            raise StreamError("TorrServer's release has no checksum to verify it against; not installed")
        self.setup["total"] = int(found.get("size") or 0)
        body = fetch(found["browser_download_url"], GITHUB_BIN)
        if hashlib.sha256(body).hexdigest() != digest.split(":", 1)[1].lower():
            raise StreamError("The download didn't match TorrServer's published checksum; not installed")
        self.setup["done"] = len(body)
        folder = install_dir()
        folder.mkdir(parents=True, exist_ok=True)
        part = folder / (saved + ".part")
        part.write_bytes(body)
        self.setup["state"] = "scanning"
        engine = av.best_engine()
        if engine is not None:
            rep = engine.scan(part)
            if rep.get("threats") or av.neutralised(part, wait=3):
                part.unlink(missing_ok=True)
                raise StreamError("The antivirus flagged the TorrServer download; it was not installed")
        final = folder / saved
        os.replace(part, final)
        if not osutil.IS_WIN:
            final.chmod(0o755)
        (folder / "VERSION.txt").write_text(f"{rel.get('tag_name', '')}\n{digest}\n", encoding="utf-8")
        return str(final)

    # ------------------------------------------------------------ process
    def ensure(self) -> None:
        """Starts TorrServer (once), listening on this PC only, password protected."""
        if not self.exe:
            raise StreamError("The streaming engine isn't installed yet")
        with self.lock:
            if self.proc and self.proc.poll() is None:
                return
            self.dir.mkdir(parents=True, exist_ok=True)
            self._kill_leftover()
            password = secrets.token_hex(16)
            (self.dir / "accs.db").write_text(json.dumps({"buzz": password}), encoding="utf-8")
            self.auth = "Basic " + base64.b64encode(f"buzz:{password}".encode()).decode()
            for listen_here in (True, False):          # older builds have no --ip option
                self.port = _free_port()
                args = [self.exe, "--port", str(self.port), "--path", str(self.dir), "--httpauth"]
                if listen_here:
                    args += ["--ip", "127.0.0.1"]
                self.proc = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                             stdin=subprocess.DEVNULL, cwd=str(self.dir),
                                             creationflags=osutil.NO_WINDOW)
                (self.dir / "torrserver.pid").write_text(str(self.proc.pid))
                for _ in range(200):                     # the first start can take a while
                    if self.proc.poll() is not None:
                        break
                    try:
                        self._call("GET", "/echo")
                        self._configure()
                        return
                    except (OSError, StreamError, http.client.HTTPException):
                        time.sleep(0.1)
                if self.proc.poll() is None:
                    self.proc.kill()
            self.proc = None
        raise StreamError("The streaming engine didn't start")

    def stop(self) -> None:
        with self.lock:
            if self.proc and self.proc.poll() is None:
                self.proc.kill()
                (self.dir / "torrserver.pid").unlink(missing_ok=True)
            self.proc = None

    def _kill_leftover(self) -> None:
        """A TorrServer left running by an earlier BuzzTorrent (closed without stopping it) keeps
        its settings database locked, so a new one can't start. Stop it, if it's really ours."""
        pid_file = self.dir / "torrserver.pid"
        try:
            pid = int(pid_file.read_text().strip())
        except (OSError, ValueError):
            return
        pid_file.unlink(missing_ok=True)
        try:
            if osutil.IS_WIN:
                out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"], capture_output=True,
                                     text=True, timeout=10, creationflags=osutil.NO_WINDOW).stdout
                if "torrserver" in out.lower():
                    subprocess.run(["taskkill", "/PID", str(pid), "/F"], capture_output=True, timeout=10,
                                   creationflags=osutil.NO_WINDOW)
            else:
                out = subprocess.run(["ps", "-p", str(pid), "-o", "comm="], capture_output=True, text=True,
                                     timeout=10).stdout
                if "torrserver" in out.lower():
                    os.kill(pid, 9)
            time.sleep(0.5)
        except (OSError, subprocess.SubprocessError):
            pass

    def _configure(self) -> None:
        """Memory-only cache big enough for 4K, a short buffer so playback starts quickly (the
        engine keeps reading ahead while it plays), plenty of peer connections, no extras."""
        sets = self._json("/settings", {"action": "get"}) or {}
        sets.update({"CacheSize": self.cache_mb * MB, "PreloadCache": self.preload_pct, "ReaderReadAHead": 95,
                     "ConnectionsLimit": 100, "ResponsiveMode": True,
                     "UseDisk": False, "RemoveCacheOnDrop": True, "TorrentDisconnectTimeout": 60,
                     "EnableDLNA": False, "EnableRutorSearch": False, "EnableDebug": False})
        self._json("/settings", {"action": "set", "sets": sets})

    def _conn(self, timeout: float) -> http.client.HTTPConnection:
        return http.client.HTTPConnection("127.0.0.1", self.port, timeout=timeout)

    def _call(self, method: str, path: str, body: bytes | None = None, headers: dict | None = None,
              timeout: float = 15) -> bytes:
        c = self._conn(timeout)
        try:
            c.request(method, path, body=body, headers={"Authorization": self.auth, **(headers or {})})
            r = c.getresponse()
            data = r.read(8 * MB)
            if r.status >= 400:
                raise StreamError(f"streaming engine: {data[:200].decode('utf-8', 'replace').strip() or r.status}")
            return data
        finally:
            c.close()

    def _json(self, path: str, payload: dict, timeout: float = 15):
        data = self._call("POST", path, json.dumps(payload).encode(), {"Content-Type": "application/json"}, timeout)
        return json.loads(data) if data.strip() else None

    # ------------------------------------------------------------ torrents
    def add(self, title: str, magnet: str | None = None, torrent: bytes | None = None, private: bool = False) -> str:
        self.ensure()
        st = None
        if torrent:          # a verified .torrent skips the wait for the file list from peers
            boundary = secrets.token_hex(12)
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"title\"\r\n\r\n{title}\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"save\"\r\n\r\nfalse\r\n"
                    f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"a.torrent\"\r\n"
                    "Content-Type: application/x-bittorrent\r\n\r\n").encode() + torrent + f"\r\n--{boundary}--\r\n".encode()
            try:
                st = json.loads(self._call("POST", "/torrent/upload", body,
                                           {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
            except (StreamError, ValueError, OSError, http.client.HTTPException):
                st = None
        if not st or not st.get("hash"):
            if not magnet:
                raise StreamError("This result has no magnet link")
            st = self._json("/torrents", {"action": "add", "link": magnet, "title": title, "save_to_db": False})
        h = str((st or {}).get("hash") or "").lower()
        if not HASH.match(h):
            raise StreamError("The streaming engine couldn't open this torrent")
        self.titles[h] = title
        if private:
            self.private.add(h)
        return h

    def drop(self, h: str, forget: bool = True) -> None:
        if HASH.match(h) and self.proc and self.proc.poll() is None:
            try:
                self._json("/torrents", {"action": "drop", "hash": h})
            except (StreamError, OSError, ValueError, http.client.HTTPException):
                pass
        if forget:
            for k in [k for k in self.prep if k[0] == h]:
                self.prep.pop(k, None)

    def status(self, h: str, index: int | None) -> dict:
        """Where a stream is at, for the TV's "starting" screen."""
        if self.setup["state"] in ("downloading", "scanning"):
            return {"stage": "installing", **self.setup}
        if self.setup["state"] == "error" and not self.exe:
            return {"stage": "error", "error": "Couldn't set up streaming: " + self.setup["error"]}
        if not HASH.match(h):
            raise StreamError("bad torrent hash")
        failed = self.prep.get((h, index), {}) if index is not None else {}
        if failed.get("stage") == "error":               # e.g. blocked: the torrent is already dropped
            return {"stage": "error", "error": failed.get("error", "")}
        try:
            self.ensure()
            st = self._json("/torrents", {"action": "get", "hash": h}) or {}
        except (OSError, http.client.HTTPException) as e:
            raise StreamError(f"The streaming engine isn't answering ({e})") from e
        out = {"stage": "metadata", "peers": int(st.get("active_peers") or 0),
               "seeders": int(st.get("connected_seeders") or 0), "total_peers": int(st.get("total_peers") or 0),
               "speed": int(st.get("download_speed") or 0), "files": None, "warnings": []}
        stats = st.get("file_stats")
        if not stats:
            return out
        files, warnings, why = pick_files(stats)
        out.update(files=files, warnings=warnings)
        if not files:
            return {**out, "stage": "error", "error": why}
        if index is None:
            return {**out, "stage": "choose"}
        prep = self.prep.get((h, index))
        if prep is None:
            return {**out, "stage": "choose"}
        out.update(stage=prep["stage"], error=prep.get("error", ""),
                   preloaded=int(st.get("preloaded_bytes") or 0), preload_size=int(st.get("preload_size") or 0))
        if prep["stage"] == "buffering" and st.get("stat") == STAT_WORKING and out["preloaded"] >= out["preload_size"] > 0:
            out["stage"] = "ready"
        return out

    def prepare(self, h: str, index: int) -> None:
        """Checks the chosen file really is a video, then fills the buffer (in the background)."""
        if not HASH.match(h):
            raise StreamError("bad torrent hash")
        key = (h, index)
        with self.lock:
            if key in self.prep and self.prep[key]["stage"] != "error":
                return
            self.prep[key] = {"stage": "checking"}
        threading.Thread(target=self._prepare, args=key, name="stream-prep", daemon=True).start()

    def _prepare(self, h: str, index: int) -> None:
        key = (h, index)
        try:
            head = self._read_head(h, index)
            kind = sniff(head)
            if kind != "video":
                self.prep[key] = {"stage": "error", "kind": kind,
                                  "error": f"Blocked: this file says it's a video but is really {kind_name(kind)}."}
                self.drop(h, forget=False)          # keep the reason, so the TV can show it
                return
            self.prep[key] = {"stage": "buffering", "kind": kind}
            self._call("GET", f"/stream?{urllib.parse.urlencode({'link': h, 'index': index})}&preload", timeout=900)
            if self.prep.get(key, {}).get("stage") == "buffering":
                self.prep[key] = {"stage": "ready", "kind": kind}
        except socket.timeout:
            if self.prep.get(key, {}).get("stage") == "checking":
                self.prep[key] = {"stage": "error", "error": "No one is sharing this copy right now. Try another one."}
        except (OSError, StreamError, http.client.HTTPException) as e:
            if self.prep.get(key, {}).get("stage") in ("checking", "buffering"):
                self.prep[key] = {"stage": "error", "error": f"The stream stopped: {e}"}

    def _read_head(self, h: str, index: int, n: int = 64 * 1024) -> bytes:
        c = self._conn(240)
        try:
            c.request("GET", self._play_path(h, index), headers={"Authorization": self.auth, "Range": f"bytes=0-{n - 1}"})
            r = c.getresponse()
            if r.status >= 400:
                raise StreamError(r.read(300).decode("utf-8", "replace").strip() or f"error {r.status}")
            return r.read(n)
        finally:
            c.close()

    @staticmethod
    def _play_path(h: str, index: int) -> str:
        return f"/stream?{urllib.parse.urlencode({'link': h, 'index': index})}&play"

    def subtitle(self, h: str, index: int) -> bytes:
        """A subtitle file from the torrent (checked to be one, and small)."""
        if not HASH.match(h):
            raise StreamError("bad torrent hash")
        st = self._json("/torrents", {"action": "get", "hash": h}) or {}
        f = next((f for f in st.get("file_stats") or [] if int(f.get("id") or 0) == index), None)
        name = str((f or {}).get("path") or "")
        if not f or not subs_mod.is_subtitle(name.rsplit("/", 1)[-1]) or int(f.get("length") or 0) > subs_mod.MAX_BYTES:
            raise StreamError("not a subtitle file in this torrent")
        return self._read_head(h, index, subs_mod.MAX_BYTES)

    def verified(self, h: str, index: int) -> bool:
        return self.prep.get((h, index), {}).get("kind") == "video"

    def open(self, h: str, index: int, range_header: str | None):
        """The video itself, for BuzzTorrent to pass on to the TV (HTTP Range works)."""
        if not self.verified(h, index):
            raise PermissionError("This stream wasn't checked yet. Start it again from the TV")
        self.ensure()
        c = self._conn(180)
        headers = {"Authorization": self.auth}
        if range_header and re.fullmatch(r"bytes=\d*-\d*", range_header.strip()):
            headers["Range"] = range_header.strip()
        c.request("GET", self._play_path(h, index), headers=headers)
        return c, c.getresponse()


def kind_name(kind: str) -> str:
    return {"exe": "a Windows program", "elf": "a program", "macho": "a Mac program", "lnk": "a shortcut",
            "zip": "an archive", "rar": "an archive", "7z": "an archive", "script": "a script", "html": "a web page",
            "ole": "an installer or Office file", "pdf": "a PDF", "text": "text", "empty": "empty"}.get(kind, "not a video")
