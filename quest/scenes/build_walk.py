"""Walk maps for the VR rooms: where you can stand, and how high the floor is there.

Reads each room's exported GLB, drops vertical rays on a 25 cm grid and floods outwards from
the viewer's spot, so you can walk up and down steps and tiers but not through walls, posts,
boulders or off a ledge. Low furniture (seats, sofas, crates) doesn't block: walking into a seat
is how you sit in it. The app (Walk.kt) loads assets/walk/<room>.bin:

  "WLK1", float x0, float z0, float cell, int nx, int nz, then nz rows of nx int16 floor heights
  in millimetres (-32768 = can't stand there); x = Blender x (the app looks up stage x as -x), z = -Blender y.

  blender -b -P quest/scenes/build_walk.py -- [--only grand,space] [--png out_dir]
"""
import math
import struct
import sys
from collections import deque
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402

WALK = K.HERE.parent / "app" / "src" / "main" / "assets" / "walk"
CELL = 0.25
BLOCKED = -32768
HEAD_LO, HEAD_HI = 1.2, 1.9      # anything in this band above the floor stops you (walls, posts)

# room id: (model, objects to ignore (name contains), largest step up, largest step down)
ROOMS = {
    "grand": ("hall_grand.glb", ["_seats"], 0.6, 0.6),
    "imax": ("hall_imax.glb", ["_seats"], 0.7, 0.7),
    "palace": ("hall_palace.glb", ["_seats"], 0.6, 0.6),
    "lounge": ("hall_lounge.glb", ["_furniture"], 0.45, 0.45),
    "space": ("space_deck.glb", ["_seats"], 0.5, 0.5),
    "drivein": ("drivein.glb", [], 0.3, 0.6),
    "jungle": ("jungle.glb", [], 0.3, 0.6),
    "night": ("stargaze.glb", [], 0.3, 0.6),
    "sunset": ("terrace.glb", [], 0.3, 0.6),
}


def load(model, ignore):
    K.reset()
    bpy.ops.import_scene.gltf(filepath=str(K.MODELS / model))
    dg = bpy.context.evaluated_depsgraph_get()
    bm = bmesh.new()
    lo, hi = Vector((1e9, 1e9, 1e9)), Vector((-1e9, -1e9, -1e9))
    for ob in bpy.context.scene.objects:
        if ob.type != "MESH" or any(s in ob.name for s in ignore):
            continue
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        me.transform(ob.matrix_world)
        for v in me.vertices:
            lo = Vector(map(min, lo, v.co))
            hi = Vector(map(max, hi, v.co))
        bm.from_mesh(me)
        ev.to_mesh_clear()
    bm.normal_update()
    return BVHTree.FromBMesh(bm), lo, hi


def surfaces(tree, x, y, top, bottom):
    """Every surface a ray dropped from top down to bottom passes: (height, faces up)."""
    out, z = [], top
    down = Vector((0, 0, -1))
    while z > bottom:
        loc, n, _, _ = tree.ray_cast(Vector((x, y, z)), down, z - bottom)
        if loc is None:
            break
        out.append((loc.z, n.z > 0.3))
        z = loc.z - 0.003
    return out


def floor_at(tree, x, y, h, up, down):
    """The floor you'd step onto at (x, y) coming from height h, or None if you can't."""
    hits = surfaces(tree, x, y, h + up + HEAD_HI, h - down)
    floors = [z for z, faces_up in hits if faces_up and h - down <= z <= h + up]
    if not floors:
        return None
    f = max(floors)
    if any(f + HEAD_LO < z <= f + HEAD_HI for z, _ in hits):
        return None
    return f


def blocked_between(tree, a, b, f):
    """A wall between two neighbouring cells, at chest and head height."""
    d = Vector((b[0] - a[0], b[1] - a[1], 0))
    for dz in (1.3, 1.7):
        loc, _, _, _ = tree.ray_cast(Vector((a[0], a[1], f + dz)), d.normalized(), d.length)
        if loc is not None:
            return True
    return False


def walk_map(room):
    model, ignore, up, down = ROOMS[room]
    tree, lo, hi = load(model, ignore)
    x0, x1 = max(lo.x, -45.0), min(hi.x, 45.0)
    y0, y1 = max(lo.y, -45.0), min(hi.y, 45.0)
    nx = int(math.ceil((x1 - x0) / CELL)) + 1
    ny = int(math.ceil((y1 - y0) / CELL)) + 1
    grid = np.full((ny, nx), np.nan, dtype=np.float32)    # [j, i]: Blender y = y0 + j*CELL

    def centre(i, j):
        return x0 + i * CELL, y0 + j * CELL

    i0, j0 = round(-x0 / CELL), round(-y0 / CELL)
    x, y = centre(i0, j0)
    h0 = floor_at(tree, x, y, 0.0, 0.3, 0.3)
    grid[j0, i0] = 0.0 if h0 is None else h0
    queue = deque([(i0, j0)])
    while queue:
        i, j = queue.popleft()
        h = float(grid[j, i])
        a = centre(i, j)
        for di, dj in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ni, nj = i + di, j + dj
            if not (0 <= ni < nx and 0 <= nj < ny) or not np.isnan(grid[nj, ni]):
                continue
            b = centre(ni, nj)
            f = floor_at(tree, b[0], b[1], h, up, down)
            if f is None or blocked_between(tree, a, b, max(h, f)):
                continue
            grid[nj, ni] = f
            queue.append((ni, nj))
    walkable = ~np.isnan(grid)
    print(f"{room}: {nx}x{ny} cells, {int(walkable.sum())} walkable, floor {np.nanmin(grid):.2f}..{np.nanmax(grid):.2f} m")
    return grid, x0, y0


def save(room, grid, x0, y0):
    """Stage rows run along +z = -Blender y, so row 0 is the largest Blender y."""
    ny, nx = grid.shape
    stage = grid[::-1, :]
    mm = np.where(np.isnan(stage), BLOCKED, np.round(stage * 1000)).astype("<i2")
    z0 = -(y0 + (ny - 1) * CELL)
    WALK.mkdir(parents=True, exist_ok=True)
    with open(WALK / f"{room}.bin", "wb") as f:
        f.write(b"WLK1" + struct.pack("<fffii", x0, z0, CELL, nx, ny))
        f.write(mm.tobytes())
    png = K.arg("--png")
    if png:
        img = bpy.data.images.new(room, nx, ny)
        lo, hi = np.nanmin(grid), np.nanmax(grid)
        v = np.where(np.isnan(grid), 0.0, 0.3 + 0.7 * (grid - lo) / max(hi - lo, 0.01))
        rgba = np.stack([v, v, v, np.ones_like(v)], axis=-1)
        rgba[round(-y0 / CELL), round(-x0 / CELL)] = (1, 0, 0, 1)          # you
        img.pixels = rgba.astype(np.float32).ravel()
        img.filepath_raw = str(Path(png) / f"walk_{room}.png")
        img.file_format = "PNG"
        img.save()


def main():
    only = K.arg("--only")
    for room in (only.split(",") if only else ROOMS):
        if not (K.MODELS / ROOMS[room][0]).exists():
            print("missing", ROOMS[room][0])
            continue
        save(room, *walk_map(room))


main()
