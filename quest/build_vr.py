"""Builds the Meta Quest VR app (BuzzTorrent VR) and optionally installs it.

  python quest/build_vr.py             build quest/build/BuzzTorrentVR.apk
  python quest/build_vr.py --install   build, then install on the Quest plugged in over USB

Needs JDK 17 (JAVA_HOME, or %LOCALAPPDATA%\\Programs\\jdk-17) and the Android SDK with
platform 35 (ANDROID_HOME or %LOCALAPPDATA%\\Android\\Sdk). Gradle comes via the wrapper.
"""
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OUT = HERE / "build" / "BuzzTorrentVR.apk"


def java_home() -> str:
    for cand in (os.environ.get("JAVA_HOME"), Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "jdk-17"):
        if cand and Path(cand, "release").is_file():
            release = Path(cand, "release").read_text(encoding="utf-8", errors="replace")
            m = re.search(r'JAVA_VERSION="(\d+)', release)
            if m and int(m.group(1)) >= 17:
                return str(cand)
    sys.exit("JDK 17 not found: install it and set JAVA_HOME")


def sdk_dir() -> Path:
    for cand in (os.environ.get("ANDROID_HOME"), os.environ.get("ANDROID_SDK_ROOT"),
                 Path(os.environ.get("LOCALAPPDATA", "")) / "Android" / "Sdk"):
        if cand and Path(cand, "platforms").is_dir():
            return Path(cand)
    sys.exit("Android SDK not found: set ANDROID_HOME")


def main() -> None:
    env = dict(os.environ, JAVA_HOME=java_home())
    sdk = sdk_dir()
    local = HERE / "local.properties"
    if not local.is_file():
        local.write_text(f"sdk.dir={sdk.as_posix()}\n", encoding="utf-8")
    gradlew = HERE / ("gradlew.bat" if os.name == "nt" else "gradlew")
    subprocess.run([str(gradlew), "assembleRelease", "--console=plain", "-q"], cwd=HERE, env=env, check=True)
    OUT.parent.mkdir(exist_ok=True)
    shutil.copy2(HERE / "app" / "build" / "outputs" / "apk" / "release" / "app-release.apk", OUT)
    print(f"OK: {OUT} ({OUT.stat().st_size // (1024 * 1024)} MB)")
    if "--install" in sys.argv[1:]:
        adb = sdk / "platform-tools" / ("adb.exe" if os.name == "nt" else "adb")
        subprocess.run([str(adb), "install", "-r", str(OUT)], check=True)
        print("Installed. On the Quest: App Library > Unknown Sources > BuzzTorrent VR")


if __name__ == "__main__":
    main()
