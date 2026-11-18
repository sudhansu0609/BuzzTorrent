"""Shared helpers for the VR room builders: meshes from bevelled boxes, materials, Cycles setup,
light baking (into a tone-mapped JPEG on a second UV map) and GLB export."""
import math
import os
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
HERE = Path(__file__).resolve().parent
# BUZZ_MODELS_OUT: export somewhere else (a staging folder), so an app build running meanwhile
# never packs a half-written GLB
MODELS = Path(os.environ.get("BUZZ_MODELS_OUT") or HERE.parent / "app" / "src" / "main" / "assets" / "models")
GLOW_TEX = 1024   # screen-light layers: soft light only, so small textures (Quest memory)


def arg(name, default=None):
    return ARGS[ARGS.index(name) + 1] if name in ARGS else default


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)


class Builder:
    """One mesh object built from bevelled boxes, grids and cylinders, with material slots."""

    def __init__(self, name):
        self.name = name
        self.bm = bmesh.new()
        self.mats = []

    def mat(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _claim(self, mat, verts):
        """Gives every face of the part just made (all faces touching its verts) this material.
        BMesh reuses freed slots, so new faces aren't always at the end of the face list."""
        idx = self.mat(mat)
        for v in verts:
            if v.is_valid:
                for f in v.link_faces:
                    f.material_index = idx

    def box(self, size, loc, mat, rot=(0, 0, 0), bevel=0.0, segs=2):
        sx, sy, sz = size
        M = Matrix.Translation(loc) @ Matrix.Rotation(math.radians(rot[2]), 4, "Z") @ \
            Matrix.Rotation(math.radians(rot[1]), 4, "Y") @ Matrix.Rotation(math.radians(rot[0]), 4, "X") @ \
            Matrix.Diagonal((sx, sy, sz, 1))
        geom = bmesh.ops.create_cube(self.bm, size=1.0, matrix=M)
        verts = geom["verts"]
        if bevel > 0:
            edges = list({e for v in verts for e in v.link_edges})
            res = bmesh.ops.bevel(self.bm, geom=edges, offset=min(bevel, min(size) * 0.45), segments=segs,
                                  affect="EDGES", profile=0.5)
            verts = list(res["verts"]) + [v for v in verts if v.is_valid]
        self._claim(mat, verts)
        return self

    def grid(self, w, h, loc, mat, xseg, yseg, rot=(90, 0, 0), wave=None):
        M = Matrix.Translation(loc) @ Matrix.Rotation(math.radians(rot[2]), 4, "Z") @ \
            Matrix.Rotation(math.radians(rot[0]), 4, "X")
        geom = bmesh.ops.create_grid(self.bm, x_segments=xseg, y_segments=yseg, size=0.5, matrix=Matrix())
        for v in geom["verts"]:
            v.co.x *= w
            v.co.y *= h
            if wave:
                v.co.z += wave(v.co.x)
            v.co = M @ v.co
        self._claim(mat, geom["verts"])
        return self

    def cyl(self, r, depth, loc, mat, segs=16):
        M = Matrix.Translation(loc)
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segs, radius1=r, radius2=r, depth=depth, matrix=M)
        self._claim(mat, geom["verts"])
        return self

    def rod(self, p, q, r, mat, segs=12, r2=None):
        """A round rod (log, pipe, rail) from p to q, radius r tapering to r2 at q."""
        p, q = Vector(p), Vector(q)
        d = q - p
        M = Matrix.Translation((p + q) / 2) @ d.to_track_quat("Z", "Y").to_matrix().to_4x4()
        geom = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=segs, radius1=r,
                                     radius2=r if r2 is None else r2, depth=d.length, matrix=M)
        self._claim(mat, geom["verts"])
        return self

    def build(self):
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        me = bpy.data.meshes.new(self.name)
        self.bm.to_mesh(me)
        self.bm.free()
        for m in self.mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(self.name, me)
        bpy.context.scene.collection.objects.link(ob)
        for p in me.polygons:
            p.use_smooth = True
        return ob


def material(name, color, rough=0.6, sheen=0.0, emit=None, emit_strength=0.0, noise=0.0, scale=40.0, metal=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = rough
    bsdf.inputs["Metallic"].default_value = metal
    if sheen:
        bsdf.inputs["Sheen Weight"].default_value = sheen
        bsdf.inputs["Sheen Tint"].default_value = (1, 0.75, 0.75, 1)
    if emit:
        bsdf.inputs["Emission Color"].default_value = (*emit, 1)
        bsdf.inputs["Emission Strength"].default_value = emit_strength
    if noise:          # subtle variation so large surfaces don't look flat (fabric, carpet)
        tex = nt.nodes.new("ShaderNodeTexNoise")
        tex.inputs["Scale"].default_value = scale
        tex.inputs["Detail"].default_value = 8
        coord = nt.nodes.new("ShaderNodeTexCoord")
        nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
        mix = nt.nodes.new("ShaderNodeMix")
        mix.data_type = "RGBA"
        mix.inputs["A"].default_value = (*[c * (1 - noise) for c in color], 1)
        mix.inputs["B"].default_value = (*[min(1, c * (1 + noise)) for c in color], 1)
        nt.links.new(tex.outputs["Fac"], mix.inputs["Factor"])
        nt.links.new(mix.outputs["Result"], bsdf.inputs["Base Color"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = 0.15
        nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
        nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def glowing(name, color, glow, threshold=0.5, strength=6.0, scale=12.0):
    """Charcoal with glowing cracks: noise picks where it burns (embers, charred logs, coals)."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = 0.9
    coord = nt.nodes.new("ShaderNodeTexCoord")
    tex = nt.nodes.new("ShaderNodeTexNoise")
    tex.inputs["Scale"].default_value = scale
    tex.inputs["Detail"].default_value = 6
    nt.links.new(coord.outputs["Object"], tex.inputs["Vector"])
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    els = ramp.color_ramp.elements
    els[0].position, els[0].color = threshold, (0, 0, 0, 1)
    els[1].position, els[1].color = min(1.0, threshold + 0.22), (*glow, 1)
    nt.links.new(tex.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], bsdf.inputs["Emission Color"])
    bsdf.inputs["Emission Strength"].default_value = strength
    bump = nt.nodes.new("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 0.3
    nt.links.new(tex.outputs["Fac"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return m


def add_light(kind, loc, energy, color, size=0.2, rot=(0, 0, 0), screen=False):
    data = bpy.data.lights.new(f"{kind}", kind)
    data.energy = energy
    data.color = color
    if kind == "AREA":
        data.shape = "RECTANGLE"
        data.size, data.size_y = size
    else:
        data.shadow_soft_size = size
    ob = bpy.data.objects.new(data.name, data)
    ob.location = loc
    ob.rotation_euler = [math.radians(a) for a in rot]
    bpy.context.scene.collection.objects.link(ob)
    if screen:
        ob["screen"] = True          # the film's light: baked separately so the app can tint it live
    return ob



def screen_light(width, distance, center_z, energy):
    """Area light filling the screen, facing the viewer: what a white frame of film would cast."""
    return add_light("AREA", (0, -distance + 0.06, center_z), energy, (1.0, 1.0, 1.0),
                     (width, width * 9 / 16), (90, 0, 0), screen=True)



def dim_screens(factor=0.3):
    """Previews: the screen at an average film's brightness instead of a white frame."""
    for o in bpy.data.objects:
        if o.get("screen"):
            o.data.energy *= factor


def decimate(ob, max_tris):
    """Scanned models can be millions of triangles: cut down to what the Quest can draw."""
    tris = sum(len(p.vertices) - 2 for p in ob.data.polygons)
    if tris <= max_tris:
        return ob
    mod = ob.modifiers.new("lighter", "DECIMATE")
    mod.ratio = max_tris / tris
    bpy.ops.object.select_all(action="DESELECT")
    ob.select_set(True)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.object.modifier_apply(modifier=mod.name)
    print(f"decimated {ob.name}: {tris} -> {sum(len(p.vertices) - 2 for p in ob.data.polygons)} triangles")
    return ob


def setup_cycles(samples):
    sc = bpy.context.scene
    sc.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for dev in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = dev
            prefs.get_devices()
            if any(d.type == dev for d in prefs.devices):
                for d in prefs.devices:
                    d.use = d.type == dev
                sc.cycles.device = "GPU"
                print("Cycles on", dev)
                break
        except TypeError:
            continue
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.view_settings.view_transform = "AgX"
    sc.view_settings.exposure = 0.0


def _bake_into(objects, img_for, samples):
    """One COMBINED bake for each object into its float image (active image node)."""
    sc = bpy.context.scene
    sc.cycles.samples = samples
    for ob in objects:
        img = img_for[ob.name]
        for m in ob.data.materials:
            node = m.node_tree.nodes.get("bake_target") or m.node_tree.nodes.new("ShaderNodeTexImage")
            node.name = "bake_target"
            node.image = img
            m.node_tree.nodes.active = node
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.bake(type="COMBINED", margin=6, uv_layer="bake")


def _screen_only(on):
    """Glow pass: only the screen's light; other lamps, glowing materials and the sky off."""
    state = []
    for ob in bpy.data.objects:
        if ob.type == "LIGHT" and not ob.get("screen"):
            state.append((ob, "hide_render", ob.hide_render))
            ob.hide_render = on
        if ob.type == "LIGHT" and ob.get("screen"):
            state.append((ob, "hide_render", ob.hide_render))
            ob.hide_render = not on
    for m in bpy.data.materials:
        if not m.node_tree:
            continue
        for n in m.node_tree.nodes:
            for name in ("Emission Strength", "Strength"):
                if n.type in ("BSDF_PRINCIPLED", "EMISSION") and name in n.inputs:
                    state.append((n.inputs[name], "default_value", n.inputs[name].default_value))
                    if on:
                        n.inputs[name].default_value = 0.0
    w = bpy.context.scene.world
    if w and w.node_tree and "Background" in w.node_tree.nodes:
        inp = w.node_tree.nodes["Background"].inputs["Strength"]
        state.append((inp, "default_value", inp.default_value))
        if on:
            inp.default_value = 0.0
    return state


def _restore(state):
    for obj, attr, val in reversed(state):
        setattr(obj, attr, val)


def _to_jpeg(img, name, exposure, reinhard):
    px = np.array(img.pixels[:], dtype=np.float32).reshape(-1, 4)
    rgb = px[:, :3] * exposure
    if reinhard:
        rgb = rgb / (1.0 + rgb)
    rgb = np.clip(rgb, 0, 1) ** (1 / 2.2)
    out = bpy.data.images.new(name, img.size[0], img.size[1])
    out.pixels[:] = np.concatenate([rgb, np.ones((rgb.shape[0], 1), np.float32)], axis=1).ravel()
    out.file_format = "JPEG"
    out.filepath_raw = str(HERE / f"{name}.jpg")
    out.save()
    return out


NUDGE = 0.01   # how far a flush part is moved off the surface it would z-fight with (1 cm)


def _islands(bm):
    """Connected pieces of a mesh (each box, cylinder or grid the Builder made)."""
    seen, out = set(), []
    for v in bm.verts:
        if v.index in seen:
            continue
        stack, part = [v], []
        seen.add(v.index)
        while stack:
            a = stack.pop()
            part.append(a)
            for e in a.link_edges:
                b = e.other_vert(a)
                if b.index not in seen:
                    seen.add(b.index)
                    stack.append(b)
        out.append(part)
    return out


def _overlap(a, b, u, v):
    """Do two convex faces (vertex lists in one plane, axes u, v) overlap by more than a sliver?"""
    A = [(p.dot(u), p.dot(v)) for p in a]
    B = [(p.dot(u), p.dot(v)) for p in b]
    for P in (A, B):
        for i in range(len(P)):
            (x1, y1), (x2, y2) = P[i], P[(i + 1) % len(P)]
            ax = (y1 - y2, x2 - x1)
            L = math.hypot(*ax)
            if L < 1e-9:
                continue
            pa = [(x * ax[0] + y * ax[1]) / L for x, y in A]
            pb = [(x * ax[0] + y * ax[1]) / L for x, y in B]
            if min(pa) >= max(pb) - 0.003 or min(pb) >= max(pa) - 0.003:
                return False
    return True


def separate_overlaps(objects, passes=6):
    """Removes parts built twice in the same place, and moves parts that lie flush on another
    surface (a trim strip on a wall, a slab on a stage) 1 cm off it. On the Quest such coplanar
    faces z-fight: they flash and shimmer as you move your head."""
    from collections import defaultdict
    bms = {}
    for ob in objects:
        bm = bmesh.new()
        bm.from_mesh(ob.data)
        bm.transform(ob.matrix_world)
        bms[ob.name] = bm
    removed = 0
    for bm in bms.values():                              # exact duplicates: keep one
        bm.verts.index_update()
        keep = {}
        for part in _islands(bm):
            key = tuple(sorted((round(p.co.x, 3), round(p.co.y, 3), round(p.co.z, 3)) for p in part))
            if key in keep:
                bmesh.ops.delete(bm, geom=part, context="VERTS")
                removed += 1
            else:
                keep[key] = True
    moved = 0
    for _ in range(passes):
        faces = []                                       # (bucket key, d, verts, island id, area)
        island_area = {}
        island_verts = {}
        for name, bm in bms.items():
            bm.verts.index_update()
            owner = {}
            for i, part in enumerate(_islands(bm)):
                for p in part:
                    owner[p.index] = (name, i)
                island_verts[(name, i)] = part
            for f in bm.faces:
                area = f.calc_area()
                if area < 1e-5:
                    continue
                isl = owner[f.verts[0].index]
                island_area[isl] = island_area.get(isl, 0.0) + area
                n = f.normal
                faces.append(((round(n.x, 2), round(n.y, 2), round(n.z, 2)), n.dot(f.verts[0].co),
                              [p.co.copy() for p in f.verts], isl, n.copy()))
        groups = defaultdict(list)
        for f in faces:
            groups[f[0]].append(f)
        to_move = {}
        for key, fs in groups.items():
            fs.sort(key=lambda f: f[1])
            n = fs[0][4]
            u = n.orthogonal().normalized()
            v = n.cross(u)
            touching = defaultdict(set)                  # island -> islands it is flush with
            for i in range(len(fs)):
                j = i + 1
                while j < len(fs) and fs[j][1] - fs[i][1] < 0.004:
                    a, b = fs[i], fs[j]
                    j += 1
                    if a[3] != b[3] and b[3] not in touching[a[3]] and _overlap(a[2], b[2], u, v):
                        touching[a[3]].add(b[3])
                        touching[b[3]].add(a[3])
            level = {}                                   # biggest part stays, the others step off
            for isl in sorted(touching, key=lambda k: -island_area[k]):     # it in 1 cm layers
                used = {level[o] for o in touching[isl] if o in level}
                level[isl] = next(k for k in range(len(used) + 1) if k not in used)
                if level[isl] and isl not in to_move:
                    to_move[isl] = n * (NUDGE * level[isl])
        if not to_move:
            break
        for isl, offset in to_move.items():
            for p in island_verts[isl]:
                p.co += offset
        moved += len(to_move)
    for ob in objects:
        bm = bms[ob.name]
        bm.transform(ob.matrix_world.inverted())
        bm.to_mesh(ob.data)
        bm.free()
    print(f"overlaps: removed {removed} duplicate parts, moved {moved} flush parts by {NUDGE * 100:.0f} cm")


def bake_all(objects, size, samples, glow=True):
    """Bakes every object's lighting before any material is swapped (so bounce light comes from
    the real materials), then gives each object a plain material with its baked picture.
    With glow, a second bake holds only the screen's light, for the app to tint with the film."""
    separate_overlaps(objects)
    setup_cycles(samples)
    bpy.context.scene.render.bake.margin = 6
    for ob in objects:
        me = ob.data
        me.uv_layers.active = me.uv_layers.new(name="bake")
        bpy.ops.object.select_all(action="DESELECT")
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.mode_set(mode="EDIT")
        bpy.ops.mesh.select_all(action="SELECT")
        bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.002)
        bpy.ops.object.mode_set(mode="OBJECT")
    base = {o.name: bpy.data.images.new(f"{o.name}_base", size, size, float_buffer=True) for o in objects}
    has_screen = any(o.get("screen") for o in bpy.data.objects)
    screens = [o for o in bpy.data.objects if o.get("screen")]
    for o in screens:
        o.hide_render = True                   # the room as it is with the screen dark
    _bake_into(objects, base, samples)
    glowimg = {}
    if glow and has_screen:
        glowimg = {o.name: bpy.data.images.new(f"{o.name}_glowf", size, size, float_buffer=True) for o in objects}
        state = _screen_only(True)
        _bake_into(objects, glowimg, max(64, samples // 2))
        _restore(state)
    for o in screens:
        o.hide_render = False
    exposure = float(arg("--exposure", 1.6))
    for ob in objects:
        me = ob.data
        lit = _to_jpeg(base[ob.name], f"{ob.name}_lit", exposure, True)
        ob["lit_image"] = lit.name
        if ob.name in glowimg:
            ob["glow_image"] = _to_jpeg(glowimg[ob.name], f"{ob.name}_glow", exposure, False).name
        mat = bpy.data.materials.new(f"{ob.name}_lit")
        mat.use_nodes = True
        tex = mat.node_tree.nodes.new("ShaderNodeTexImage")
        tex.name = "baked"
        tex.image = lit
        bsdf = mat.node_tree.nodes["Principled BSDF"]
        mat.node_tree.links.new(tex.outputs["Color"], bsdf.inputs["Base Color"])
        bsdf.inputs["Roughness"].default_value = 1.0
        me.materials.clear()
        me.materials.append(mat)
        for p in me.polygons:
            p.material_index = 0
        for layer in [l for l in me.uv_layers if l.name != "bake"]:
            me.uv_layers.remove(layer)


def bake(obj, size, samples):
    bake_all([obj], size, samples)


def _export_file(objects, path):
    bpy.ops.object.select_all(action="DESELECT")
    for ob in objects:
        ob.select_set(True)
    MODELS.mkdir(parents=True, exist_ok=True)
    bpy.ops.export_scene.gltf(filepath=str(path), export_format="GLB", use_selection=True,
                              export_image_format="JPEG", export_jpeg_quality=88, export_apply=True,
                              export_lights=False, export_cameras=False)
    print("exported", path)


def export(objects, name):
    """name.glb, and name_glow.glb (same geometry, the screen's light only) when it was baked."""
    _export_file(objects, MODELS / f"{name}.glb")
    glowing = [o for o in objects if o.get("glow_image")]
    if not glowing:
        return
    for o in glowing:
        small = bpy.data.images[o["glow_image"]].copy()
        small.scale(GLOW_TEX, GLOW_TEX)
        o.data.materials[0].node_tree.nodes["baked"].image = small
    _export_file(glowing, MODELS / f"{name}_glow.glb")
    for o in glowing:
        o.data.materials[0].node_tree.nodes["baked"].image = bpy.data.images[o["lit_image"]]


def polyhaven(asset, res="2k"):
    """Downloads a Poly Haven (CC0) model as glTF with its textures, checking each file's MD5,
    and imports it. Returns the imported objects."""
    import hashlib
    import json
    import urllib.request
    dest = HERE / "_downloads" / asset

    def fetch(url, timeout):   # Poly Haven refuses Python's default user agent
        req = urllib.request.Request(url, headers={"User-Agent": "BuzzTorrent-VR-scene-builder/1.0"})
        return urllib.request.urlopen(req, timeout=timeout).read()

    files = json.loads(fetch(f"https://api.polyhaven.com/files/{asset}", 60))
    entry = files["gltf"][res]["gltf"]
    todo = [(entry["url"], entry["md5"], dest / Path(entry["url"]).name)]
    todo += [(v["url"], v["md5"], dest / rel) for rel, v in entry.get("include", {}).items()]
    for url, md5, path in todo:
        if path.is_file() and hashlib.md5(path.read_bytes()).hexdigest() == md5:
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        data = fetch(url, 300)
        if hashlib.md5(data).hexdigest() != md5:
            raise RuntimeError(f"checksum mismatch for {url}")
        path.write_bytes(data)
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(todo[0][2]))
    return [o for o in bpy.data.objects if o not in before]


def place(objects, loc=(0, 0, 0), rot_z=0.0, scale=1.0):
    """Moves an imported model (all its parts) as one."""
    import mathutils
    M = mathutils.Matrix.Translation(loc) @ mathutils.Matrix.Rotation(math.radians(rot_z), 4, "Z") @ \
        mathutils.Matrix.Scale(scale, 4)
    for o in objects:
        if o.parent is None:
            o.matrix_world = M @ o.matrix_world
    return objects


def join(objects, name):
    """Joins imported mesh parts into one object (so it can be baked onto one texture)."""
    alive = [o for o in objects if o.name in bpy.data.objects and bpy.data.objects[o.name] == o]
    meshes = [o for o in alive if o.type == "MESH"]
    leftovers = [o.name for o in alive if o.type != "MESH"]       # empties etc., removed after joining
    bpy.ops.object.select_all(action="DESELECT")
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    bpy.ops.object.parent_clear(type="CLEAR_KEEP_TRANSFORM")
    bpy.ops.object.join()
    ob = bpy.context.active_object
    ob.name = name
    for n in leftovers:
        if n in bpy.data.objects:
            bpy.data.objects.remove(bpy.data.objects[n])
    return ob
