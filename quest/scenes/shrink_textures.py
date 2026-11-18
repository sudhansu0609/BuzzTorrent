"""Shrinks the textures inside GLB files in place (no re-bake): every image larger than --max
pixels on a side is resized and re-saved as JPEG, and the binary chunk is repacked.

The screen-light ("_glow") layers only hold the screen's soft light, so 1024 px is plenty and
saves about 16x their graphics memory (a 4096 px texture is ~85 MB on the GPU with mipmaps).
bakekit.export already writes new glow layers at GLOW_TEX; this fixes existing files.

  python quest/scenes/shrink_textures.py --max 1024 quest/app/src/main/assets/models/*_glow.glb

Needs Pillow (pip install pillow). Plain Python, not Blender.
"""
import argparse
import io
import json
import struct
from pathlib import Path

from PIL import Image


def pad4(b, fill=b"\0"):
    return b + fill * (-len(b) % 4)


def shrink(path, max_px, quality):
    data = path.read_bytes()
    magic, version, _ = struct.unpack_from("<III", data, 0)
    if magic != 0x46546C67:
        raise ValueError(f"{path}: not a GLB")
    jlen = struct.unpack_from("<I", data, 12)[0]
    gltf = json.loads(data[20:20 + jlen])
    blen = struct.unpack_from("<I", data, 20 + jlen)[0]
    bin0 = 28 + jlen
    binary = data[bin0:bin0 + blen]
    views = gltf["bufferViews"]
    replace = {}
    for img in gltf.get("images", []):
        v = views[img["bufferView"]]
        raw = binary[v.get("byteOffset", 0):v.get("byteOffset", 0) + v["byteLength"]]
        im = Image.open(io.BytesIO(raw))
        if max(im.size) <= max_px:
            continue
        k = max_px / max(im.size)
        im = im.convert("RGB").resize((round(im.width * k), round(im.height * k)), Image.LANCZOS)
        out = io.BytesIO()
        im.save(out, "JPEG", quality=quality)
        replace[img["bufferView"]] = out.getvalue()
        img["mimeType"] = "image/jpeg"
    if not replace:
        return 0, 0
    packed = b""
    for i, v in enumerate(views):
        chunk = replace.get(i)
        if chunk is None:
            off = v.get("byteOffset", 0)
            chunk = binary[off:off + v["byteLength"]]
        packed = pad4(packed)
        v["byteOffset"] = len(packed)
        v["byteLength"] = len(chunk)
        packed += chunk
    packed = pad4(packed)
    gltf["buffers"][0]["byteLength"] = len(packed)
    js = pad4(json.dumps(gltf, separators=(",", ":")).encode(), b" ")
    out = struct.pack("<III", 0x46546C67, version, 12 + 8 + len(js) + 8 + len(packed))
    out += struct.pack("<II", len(js), 0x4E4F534A) + js + struct.pack("<II", len(packed), 0x004E4942) + packed
    before = len(data)
    path.write_bytes(out)
    return before, len(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--max", type=int, default=1024)
    ap.add_argument("--quality", type=int, default=88)
    ap.add_argument("files", nargs="+", type=Path)
    a = ap.parse_args()
    for f in a.files:
        before, after = shrink(f, a.max, a.quality)
        if before:
            print(f"{f.name}: {before / 2**20:.1f} MB -> {after / 2**20:.1f} MB")
        else:
            print(f"{f.name}: already small")


main()
