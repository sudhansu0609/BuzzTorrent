"""Subtitles for the TV player: find .srt/.vtt files that belong to a video and turn them
into a simple cue list ({start, end, text} in seconds) that any player can draw."""
from __future__ import annotations

import re
from pathlib import PurePosixPath

SUB_EXT = (".srt", ".vtt")
MAX_BYTES = 3 * 1024 * 1024

# filename hints -> (code, label)
LANGS = [
    (r"eng(lish)?|\ben\b", "en", "English"), (r"hin(di)?|\bhi\b", "hi", "Hindi"), (r"ben(gali)?|bangla|\bbn\b", "bn", "Bengali"),
    (r"urd(u)?|\bur\b", "ur", "Urdu"), (r"tam(il)?|\bta\b", "ta", "Tamil"), (r"tel(ugu)?|\bte\b", "te", "Telugu"),
    (r"mar(athi)?|\bmr\b", "mr", "Marathi"), (r"pun(jabi)?|\bpa\b", "pa", "Punjabi"), (r"mal(ayalam)?|\bml\b", "ml", "Malayalam"),
    (r"spa(nish)?|\bes\b", "es", "Spanish"), (r"fre(nch)?|fra|\bfr\b", "fr", "French"), (r"ger(man)?|deu|\bde\b", "de", "German"),
    (r"ara(bic)?|\bar\b", "ar", "Arabic"), (r"por(tuguese)?|\bpt\b", "pt", "Portuguese"),
]
_LANGS = [(re.compile(rf"(?:^|[ ._\-\[(])(?:{rx})(?:$|[ ._\-\])])", re.I), code, label) for rx, code, label in LANGS]


def language(name: str) -> tuple[str, str]:
    stem = PurePosixPath(name).stem
    for rx, code, label in _LANGS:
        if rx.search(stem):
            return code, label
    return "", "Subtitles"


def is_subtitle(name: str) -> bool:
    return name.lower().endswith(SUB_EXT) and not name.startswith("history/")


def for_video(video: str, subs: list[str], only_video: bool) -> list[str]:
    """Subtitle files that belong to a video: same name start ("Film.mkv" -> "Film.en.srt"),
    or every subtitle when the item has only one video."""
    stem = PurePosixPath(video).stem.lower()
    mine = [s for s in subs if PurePosixPath(s).name.lower().startswith(stem)]
    return mine or (list(subs) if only_video else [])


def describe(names: list[str]) -> list[dict]:
    """Labels for a video's subtitle files, made unique ("English", "English 2")."""
    # the same subtitles as .srt and .vtt: keep one (the .srt)
    by_stem: dict[str, str] = {}
    for n in sorted(names, key=lambda n: not n.lower().endswith(".srt")):
        by_stem.setdefault(PurePosixPath(n).stem.lower(), n)
    out, seen = [], {}
    for n in sorted(by_stem.values(), key=lambda n: (".asr." in n.lower(), language(n)[0] != "en",
                                                     language(n)[0] != "hi", n.lower())):
        code, label = language(n)
        if ".asr." in n.lower():          # the Archive's own speech-to-text captions
            code, label = code or "en", "Auto captions"
        seen[label] = seen.get(label, 0) + 1
        out.append({"file": n, "lang": code, "label": label if seen[label] == 1 else f"{label} {seen[label]}"})
    return out[:12]


def decode(data: bytes) -> str:
    if data[:2] in (b"\xff\xfe", b"\xfe\xff"):
        return data.decode("utf-16", errors="replace")
    for enc in ("utf-8-sig", "cp1252"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1", errors="replace")


_TIME = re.compile(r"(?:(\d{1,2}):)?(\d{1,2}):(\d{1,2})[.,](\d{1,3})")
_CUE = re.compile(r"((?:\d{1,2}:)?\d{1,2}:\d{1,2}[.,]\d{1,3})\s*-->\s*((?:\d{1,2}:)?\d{1,2}:\d{1,2}[.,]\d{1,3})")
_TAGS = re.compile(r"<[^>]{1,40}>|\{\\[^}]{0,40}\}")


def _secs(t: str) -> float:
    m = _TIME.fullmatch(t.strip())
    if not m:
        return 0.0
    h, mnt, s, ms = m.groups()
    return int(h or 0) * 3600 + int(mnt) * 60 + int(s) + int(ms.ljust(3, "0")) / 1000


def parse(text: str) -> list[dict]:
    """SRT or WebVTT -> cues. Styling tags are dropped; the text keeps its line breaks."""
    cues = []
    blocks = re.split(r"\r?\n\s*\r?\n", text.replace("\r\n", "\n"))
    for block in blocks:
        lines = [ln for ln in block.split("\n") if ln.strip()]
        for i, ln in enumerate(lines):
            m = _CUE.search(ln)
            if not m:
                continue
            body = "\n".join(_TAGS.sub("", x).strip() for x in lines[i + 1:]).strip()
            if body:
                cues.append({"start": round(_secs(m.group(1)), 3), "end": round(_secs(m.group(2)), 3), "text": body[:500]})
            break
    cues.sort(key=lambda c: c["start"])
    return cues[:20000]


# ---------------------------------------------------------------- online (SubDL)
# subdl.com has a free API (sign up, then copy the key into Settings or config.json:
# "subtitles": {"subdl_key": "..."}). Only the film's name/year/episode is sent.
SUBDL_API = "https://api.subdl.com/api/v1/subtitles"
SUBDL_DL = "https://dl.subdl.com"
SUBDL_LANGS = {"EN": ("en", "English"), "HI": ("hi", "Hindi"), "BN": ("bn", "Bengali"), "UR": ("ur", "Urdu"),
               "TA": ("ta", "Tamil"), "TE": ("te", "Telugu"), "ML": ("ml", "Malayalam"), "AR": ("ar", "Arabic"),
               "ES": ("es", "Spanish"), "FR": ("fr", "French")}
_SUBDL_PATH = re.compile(r"^/subtitle/[0-9A-Za-z_-]{1,40}\.zip$")
_EPISODE = re.compile(r"\bS(\d{1,2})[ ._-]?E(\d{1,3})\b", re.I)


def subdl_search(fetch_json, key: str, title: str, year: int | None, video_name: str,
                 langs: str = "EN,HI", limit: int = 6) -> list[dict]:
    """-> [{"lang", "label", "path"}]: the most-downloaded few per language."""
    params = {"api_key": key, "film_name": title, "languages": langs, "subs_per_page": "30"}
    ep = _EPISODE.search(video_name or "")
    if ep:
        params.update(type="tv", season_number=str(int(ep.group(1))), episode_number=str(int(ep.group(2))))
    else:
        params["type"] = "movie"
        if year:
            params["year"] = str(year)
    d = fetch_json(SUBDL_API + "?" + "&".join(f"{k}={_q(v)}" for k, v in params.items()))
    if not isinstance(d, dict) or not d.get("status"):
        return []
    out, per_lang = [], {}
    release = re.sub(r"\.[a-z0-9]{2,4}$", "", (video_name or "").lower())
    subs = [s for s in d.get("subtitles") or [] if isinstance(s, dict) and _SUBDL_PATH.match(str(s.get("url") or ""))]
    # a subtitle made for this exact release is in sync; put those first
    subs.sort(key=lambda s: release and str(s.get("release_name") or "").lower() not in release)
    for s in subs:
        code = str(s.get("lang") or s.get("language") or "").upper()[:2]
        lang, name = SUBDL_LANGS.get(code, (code.lower(), str(s.get("language") or code)))
        per_lang[lang] = per_lang.get(lang, 0) + 1
        if per_lang[lang] > 2:
            continue
        out.append({"lang": lang, "label": f"{name} (online{'' if per_lang[lang] == 1 else ' 2'})", "path": s["url"]})
        if len(out) >= limit:
            break
    return out


def subdl_valid(path: str) -> bool:
    return bool(_SUBDL_PATH.match(path))


def from_zip(data: bytes) -> bytes:
    """The subtitle inside a downloaded .zip (size-checked: no zip bombs)."""
    import io
    import zipfile
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        files = [i for i in z.infolist() if not i.is_dir() and is_subtitle(i.filename.rsplit("/", 1)[-1])
                 and i.file_size <= MAX_BYTES]
        if not files:
            raise ValueError("no subtitle file in the download")
        files.sort(key=lambda i: not i.filename.lower().endswith(".srt"))
        return z.read(files[0])


def _q(v: str) -> str:
    from urllib.parse import quote
    return quote(str(v), safe="")
