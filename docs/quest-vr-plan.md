# BuzzTorrent VR for Meta Quest 3 (native, Meta Spatial SDK)

Goal: watch BuzzTorrent films on a giant screen inside virtual environments (cinema hall, night sky,
etc.), with every format the TV app plays (MKV, HEVC, 4K) plus AC3/DTS sound.

## Design

- **New Gradle project `quest/`**, app id `com.buzzcaf.buzztorrent.vr`, Kotlin + Meta Spatial SDK
  (0.13.x), AGP 8.11, Gradle wrapper 9.4, JDK 17. Installs next to the 2D TV app; pairs with its own PIN.
  The no-Gradle TV build (`android/`) is untouched.
- **Hybrid app** (pattern from Meta's HybridSample):
  1. *Browse* = a 2D panel with the same WebView + `BuzzTV` bridge as the TV app (search, details,
     My PC, Continue watching all come from the PC's `/tv` page as today). The bridge Java is shared
     with `android/src` through a Gradle `sourceSets` entry, not copied.
  2. *Watch* = `playNative(payload)` launches **CinemaActivity** (immersive `AppSystemActivity`) with
     the same JSON payload the TV player takes (copies + labels + bitrates, subtitles, resume, progress URL).
- **Player**: Media3 ExoPlayer rendering to a Spatial SDK video panel (MKV/MP4/WebM, HEVC/H.264/AV1 in
  hardware). AC3/E-AC3/DTS/TrueHD audio via the prebuilt FFmpeg audio decoder AAR
  (`org.jellyfin.media3:media3-ffmpeg-decoder`), so torrent MKVs don't play silent. Keeps the TV
  player's behaviour: Wi-Fi check picks quality, steps down on stalls, subtitles from the PC's cue
  lists, progress saved every 15 s to the PC.
- **Controls panel** under the screen: play/pause, ±10 s, seek bar, CC, Quality, Next, Environment,
  Screen size, Close. Controllers' thumbstick seeks; trigger = select.
- **Environments** (switchable live, last choice remembered):
  | Room | How it's built |
  |---|---|
  | Cinema hall | built in code from primitives: dark walls, raked seat rows, screen glow on the walls |
  | Night sky | 360° star sky (NASA/ESO public-domain image) + dark ground plane |
  | Sunset / mountains | Poly Haven CC0 HDRI, tonemapped to an equirect JPG |
  | Dark void | black, screen only (OLED-cinema feel) |
  | My room (passthrough) | Quest passthrough: the screen floats in your real room |
  | Space | 360° Milky Way / nebula panorama (NASA public domain), screen floating in orbit |
  | Drive-in | night sky + tarmac ground, big framed outdoor screen, rows of parked cars from primitives |
  | Jungle campsite | Poly Haven CC0 forest HDRI, campfire (baked logs and coals + live flames), optional night ambience (CC0 audio) |
- **Screen**: size presets (Medium 3 m / Large 6 m / IMAX 12 m wide), distance follows size, recenter
  on long-press. Environment dims while playing.
- Security stays as in the TV app: WebView only loads the paired PC + bundled setup page; player only
  accepts archive.org, the PC's `/api/tv/` and its own files.

## Toolchain (one-time, ~2–3 GB, no admin)

- Temurin JDK 17 portable zip → `%LOCALAPPDATA%\Programs\jdk-17`
- Android cmdline-tools → `sdkmanager "platforms;android-34" "build-tools;35.0.0" "platform-tools"`
- Gradle comes via the wrapper. No NDK (no custom shaders), no Android Studio required.
- Meta Spatial Editor: not needed (scenes are built in code).
- Build: `quest\gradlew assembleRelease` → `adb install -r` to the headset over USB.

## Risks

- Can't run on the headset from here: each milestone needs the user to install and report back.
- Spatial SDK APIs change between versions: code follows the current samples, not memory.
- Assets must be CC0/public domain; none of Meta's sample assets (SDK licence) are shipped.

## Status

| # | Item | Status |
|---|---|---|
| 1 | Toolchain: JDK 17, SDK 34/35, cmdline-tools | done (JDK 17.0.20.1, platforms 34+35, build-tools 35, Gradle 9.4.1 wrapper verified) |
| 2 | `quest/` skeleton from Spatial SDK template builds an APK | done |
| 3 | Browse panel: WebView + shared bridge, pairing works | built; needs headset test |
| 4 | CinemaActivity: ExoPlayer on a big screen in a dark void | built; needs headset test |
| 5 | FFmpeg audio decoder (AC3/DTS) | built (Media3 1.9.0 + jellyfin ffmpeg 1.9.0+1) |
| 6 | Controls panel + quality/subtitles/progress parity with TV player | built; logic shared via android/src/.../Playlist.java |
| 7 | Environments: void, passthrough, night sky, sunset | built; needs headset test |
| 8 | Cinema hall built from primitives | built; needs headset test |
| 8b | Space, drive-in, jungle campsite | built; needs headset test |
| 9 | Screen size presets, recenter, remember choices | built |
| 10 | README + `make_share.py` include the VR APK | done (`python quest/build_vr.py [--install]`) |
| 11 | Room picker: Room ▾ opens a list of every room (name + one line), current one ringed | built 2026-10-15; needs headset test |
| 12 | Live fire (Kit.fire): flipbook flames from `quest/scenes/make_fire.py`, sparks, flickering light pool | built 2026-10-15; needs headset test |
| 13 | Jungle campfire rebuilt (coal bed, charred teepee); drive-in: lofted two-tone 1950s cars (`quest/scenes/cars.py`), fire barrels, festoon lights | built 2026-10-15; needs headset test |
| 14 | My room: screen surface + film-coloured halo (Kit.bareScreen); passthrough LUT dims the room while playing and tints it with the film | built 2026-10-15; needs headset test |
| 15 | IMAX Laser OOM fix: far seats chamfered (926k -> ~520k tris), glow layers at 1024 px (`scenes/shrink_textures.py`, GLOW_TEX), old room swept from the mesh cache before the next loads | built 2026-10-15; needs headset test |
| 16 | Lower screens: IMAX Laser films stand on the 1.43 screen's foot; Grand (stage 0.4 m, screen 2.5 m) and Palace (2.8 m) rebaked; subtitles inside the picture where a stage would hide them | built 2026-10-18; needs headset test |
| 17 | ⚙ Settings panel: lights 0-100 %, picture contrast/brightness/colour (Media3 effects), sound modes (SoundModes), seat presets per hall (Room.seats) | built 2026-10-18; needs headset test |

## Open questions for the first headset test

- Screen faces the viewer? (stage = head yaw, panels at +Z; flip if it's behind you)
- Controls panel reachable/readable at (0, 0.85 m, 1.15 m)? Subtitle size?
- Skybox orientation/brightness per room; cinema hall too dark or too bright?
- Frame rate in the cinema hall (~130 boxes) and drive-in.
- Live fire: flames upright and facing you (not mirrored/edge-on)? Light pool on the ground, not floating?
- Room picker: readable, every tile clickable, closes after a pick?
- My room: lights fade down on Play and up on Pause? Tint follows the film? Video visible over passthrough?
- IMAX Laser after Grand IMAX: no out-of-memory kill (`adb logcat | grep oom-kill`)?
- Close: does Horizon reopen the browse panel?
