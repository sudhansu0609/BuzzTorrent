"""Live fire for the VR rooms (campfire, fire barrels): flipbook flame frames and a pool of
firelight, exported as small GLBs into assets/models/fire. Rooms.kt (Kit.fire) shows the frames
one at a time on a quad that turns to face you, drawn additively (black = see-through), and
flickers the light pool on the ground. Generated here from noise, so nothing to license.

  blender -b -P quest/scenes/make_fire.py [-- --preview strip.png]

  flame_00 .. flame_11.glb   a 0.5 x 1 m quad, origin at the bottom middle, facing glTF +Z
  pool.glb                   a 1 x 1 m flat quad (radius 0.5 m) on the ground, origin in the middle

The frames loop: frame k samples the same tileable noise k/FRAMES further along, so the last
frame flows back into the first.
"""
import sys
from pathlib import Path

import bpy
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402

FRAMES = 12           # Rooms.kt FIRE_FRAMES
W, H = 128, 256       # pixels per frame (the quad is 0.5 m x 1 m)
OUT = K.MODELS / "fire"
rng = np.random.default_rng(7)


def tile_noise(gx, gy, xs, ys):
    """Smooth value noise on a gx x gy lattice that wraps in y (period 1 in ys)."""
    g = rng.random((gy, gx + 1))
    fx, fy = xs * gx, (ys % 1.0) * gy
    x0, y0 = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - x0, fy - y0
    tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
    x0 = np.clip(x0, 0, gx - 1)
    y1 = (y0 + 1) % gy
    y0 = y0 % gy
    a = g[y0, x0] * (1 - tx) + g[y0, x0 + 1] * tx
    b = g[y1, x0] * (1 - tx) + g[y1, x0 + 1] * tx
    return a * (1 - ty) + b * ty


def fbm(xs, ys, base):
    out, amp, tot = 0.0, 1.0, 0.0
    for o in range(4):
        n = 2 ** o
        out = out + amp * tile_noise(base[0] * n, base[1] * n, xs, ys)
        tot += amp
        amp *= 0.5
    return out / tot


def ramp(t):
    """Flame colour by heat: black, deep red, orange, yellow, near-white."""
    stops = np.array([0.0, 0.18, 0.42, 0.7, 1.0])
    cols = np.array([(0, 0, 0), (0.45, 0.04, 0.0), (1.0, 0.32, 0.02), (1.0, 0.68, 0.18), (1.0, 0.95, 0.78)])
    return np.stack([np.interp(t, stops, cols[:, c]) for c in range(3)], -1)


def flame_frames():
    u = np.linspace(-1, 1, W)[None, :]            # across, -1..1
    v = np.linspace(0, 1, H)[:, None]             # up: 0 = base, 1 = tip
    xs = (u + 1) / 2 + np.zeros_like(v)
    frames = []
    for k in range(FRAMES):
        t = k / FRAMES
        ys = (v * 0.9 - t) + np.zeros_like(u)     # the noise rises through the flame
        n = fbm(xs, ys, (6, 4))
        warp = fbm(xs * 0.6 + 0.2, ys * 0.7 + 0.37, (3, 3)) - 0.5
        width = 0.9 * (1 - v) ** 0.95 * (0.55 + 0.45 * np.clip(v * 5, 0, 1))   # wide base, ragged tip
        ud = u + warp * 1.3 * v ** 1.1
        shape = np.clip(1 - (np.abs(ud) / np.maximum(width, 1e-3)) ** 1.6, 0, 1)
        heat = shape * 1.15 - (1 - n) * (0.25 + v * 1.45)     # noise eats the flame from the top: tongues
        heat = np.clip(heat, 0, 1) * np.clip(v * 9, 0, 1) * np.clip((1 - v) * 5, 0, 1)
        heat = heat ** 1.15 * 0.92
        frames.append(ramp(heat))
    return frames


def pool_image(size=128):
    a = np.linspace(-1, 1, size)
    r = np.sqrt(a[None, :] ** 2 + a[:, None] ** 2)
    i = np.clip(1 - r, 0, 1) ** 2.2
    return np.stack([i * 1.0, i * 0.42, i * 0.1], -1)


def image(name, rgb):
    h, w, _ = rgb.shape
    img = bpy.data.images.new(name, w, h, alpha=False)
    px = np.ones((h, w, 4), dtype=np.float32)
    px[..., :3] = rgb
    img.pixels.foreach_set(px.ravel())     # Blender rows run bottom to top, as v does here
    img.file_format = "PNG"
    return img


def quad(name, img, verts):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], [(0, 1, 2, 3)])
    uv = me.uv_layers.new(name="uv")
    for i, c in enumerate([(0, 0), (1, 0), (1, 1), (0, 1)]):
        uv.data[i].uv = c
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
    tex.image = img
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
    mat.use_backface_culling = False
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def export(ob, path):
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_image_format="AUTO", export_apply=True,
                              export_lights=False, export_cameras=False)
    print("exported", path)


def main():
    K.reset()
    frames = flame_frames()
    if "--preview" in K.ARGS:
        strip = np.concatenate(frames, axis=1)
        img = image("strip", strip)
        img.filepath_raw = K.arg("--preview")
        img.save()
        return
    OUT.mkdir(parents=True, exist_ok=True)
    for k, rgb in enumerate(frames):
        # Blender X across, Z up, facing -Y: glTF +X, +Y up, facing +Z
        ob = quad(f"flame_{k:02d}", image(f"flame_{k:02d}", rgb),
                  [(-0.25, 0, 0), (0.25, 0, 0), (0.25, 0, 1), (-0.25, 0, 1)])
        export(ob, OUT / f"flame_{k:02d}.glb")
        bpy.data.objects.remove(ob)
    ob = quad("pool", image("pool", pool_image()), [(-0.5, 0.5, 0), (0.5, 0.5, 0), (0.5, -0.5, 0), (-0.5, -0.5, 0)])
    export(ob, OUT / "pool.glb")


main()
