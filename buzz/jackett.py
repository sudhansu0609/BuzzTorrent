"""Starts the local Jackett together with BuzzTorrent and stops it again when BuzzTorrent quits.

A Jackett that was already running (a Windows service, or started by hand) is left alone:
only a copy this module started is ever killed."""
from __future__ import annotations

import os
import socket
import subprocess
import threading
import time
from pathlib import Path

from . import osutil

EXE_NAMES = ("JackettConsole.exe",) if osutil.IS_WIN else ("jackett",)


def find_exe(configured: str | None = None) -> str | None:
    cands: list[str | Path | None] = [configured]
    if osutil.IS_WIN:
        for var in ("ProgramData", "LOCALAPPDATA", "ProgramFiles", "ProgramFiles(x86)", "APPDATA"):
            base = os.environ.get(var)
            if base:
                cands += [Path(base) / "Jackett" / n for n in EXE_NAMES]
                cands += [Path(base) / "Programs" / "Jackett" / n for n in EXE_NAMES]   # winget / per-user install
    else:
        cands += [Path.home() / "Jackett" / "jackett", Path("/opt/Jackett/jackett"), Path("/usr/local/bin/jackett")]
    cands += [osutil.which(n) for n in EXE_NAMES]
    return next((str(c) for c in cands if c and Path(c).is_file()), None)


def is_up(port: int) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=1):
            return True
    except OSError:
        return False


class JackettRunner:
    def __init__(self, exe: str | None, port: int = 9117):
        self.exe, self.port = exe, port
        self.proc: subprocess.Popen | None = None

    def start(self) -> str:
        """Returns a short status line for the log."""
        if is_up(self.port):
            return "already running (left as is)"
        if not self.exe:
            return "not found (install Jackett, or set \"jackett.exe\" in config.json)"
        try:
            self.proc = subprocess.Popen([self.exe], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                         stdin=subprocess.DEVNULL, cwd=str(Path(self.exe).parent),
                                         creationflags=osutil.NO_WINDOW)
        except OSError as e:
            return f"couldn't start: {e}"
        return "started"

    def wait_ready(self, seconds: float = 30) -> bool:
        end = time.time() + seconds
        while time.time() < end:
            if self.proc and self.proc.poll() is not None:
                return False
            if is_up(self.port):
                return True
            time.sleep(0.5)
        return False

    def start_async(self) -> None:
        def run() -> None:
            print(f"Jackett: {self.start()}", flush=True)
        threading.Thread(target=run, name="jackett", daemon=True).start()

    def stop(self) -> None:
        proc, self.proc = self.proc, None
        if not proc or proc.poll() is not None:
            return
        try:
            if osutil.IS_WIN:       # also takes down anything Jackett spawned
                subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10,
                               creationflags=osutil.NO_WINDOW)
            else:
                proc.kill()
        except (OSError, subprocess.SubprocessError):
            proc.kill()
