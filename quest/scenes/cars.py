"""1950s cars for the drive-in, modelled in code: a smooth lofted body (subdivided, wheel arches cut
out), a two-tone cabin whose window band is glass, whitewall tyres with chrome hubcaps, a chrome
grille, bumpers, headlights, side spears and glowing tail-fin lights.

Nose towards -Y, centred on x = 0, standing on z = 0. sedan() returns one object; build_drivein.py
places copies and joins them.
"""
import math

import bmesh
import bpy
from mathutils import Matrix, Vector

import bakekit as K

LENGTH = 5.3
FRONT, REAR = -2.65, 2.65
AXLES = (-1.55, 1.62)
WHEEL_R = 0.37


def _lerp(table, y):
    """Piecewise-linear profile lookup: table = [(y, value), ...] sorted by y."""
    if y <= table[0][0]:
        return table[0][1]
    for (y0, a), (y1, b) in zip(table, table[1:]):
        if y <= y1:
            t = (y - y0) / (y1 - y0)
            t = t * t * (3 - 2 * t)
            return a + (b - a) * t
    return table[-1][1]


def _loft(name, stations, ring, mat, ends=((0.05, 0.8), (0.08, 0.45), (0.09, 0.12))):
    """A closed shell through cross-sections: ring(y) gives the section's points (x, z), going
    round from the bottom middle, for the station at y. Each end closes with smaller and smaller
    copies of its section ([ends]: (distance out, scale)), so it rounds off under subdivision
    instead of pinching round one big cap face."""
    bm = bmesh.new()

    def shrunk(y, dy, k):
        pts = ring(y)
        zc = sum(z for _, z in pts) / len(pts)
        return [(x * k, y + dy, zc + (z - zc) * k) for x, z in pts]

    sections = [shrunk(stations[0], -dy, k) for dy, k in reversed(ends)]
    sections += [[(x, y, z) for x, z in ring(y)] for y in stations]
    sections += [shrunk(stations[-1], dy, k) for dy, k in ends]
    rows = [[bm.verts.new(co) for co in sec] for sec in sections]
    n = len(rows[0])
    for a, b in zip(rows, rows[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((a[i], a[j], b[j], b[i]))
    bm.faces.new(list(reversed(rows[0])))
    bm.faces.new(rows[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    return ob


def _apply(ob, *mods):
    bpy.ops.object.select_all(action="DESELECT")
    bpy.context.view_layer.objects.active = ob
    ob.select_set(True)
    for kind, opts in mods:
        m = ob.modifiers.new(kind.lower(), kind)
        for k, v in opts.items():
            setattr(m, k, v)
        bpy.ops.object.modifier_apply(modifier=m.name)
    return ob


# ------------------------------------------------------------------ profiles
HALF_W = [(FRONT, 0.80), (FRONT + 0.25, 0.94), (-1.6, 0.98), (1.9, 0.98), (REAR - 0.2, 0.95), (REAR, 0.86)]
BOTTOM = [(FRONT, 0.32), (FRONT + 0.4, 0.24), (REAR - 0.4, 0.24), (REAR, 0.33)]
DECK = [(FRONT, 0.70), (FRONT + 0.35, 0.82), (-0.9, 0.9), (-0.7, 0.93), (1.25, 0.93), (1.5, 0.9), (REAR - 0.1, 0.84), (REAR, 0.74)]
FIN = [(FRONT, 0.0), (1.2, 0.0), (2.0, 0.07), (REAR - 0.05, 0.16), (REAR, 0.12)]    # tail fins rise at the back


def body_ring(y):
    w, zb, zt, fin = _lerp(HALF_W, y), _lerp(BOTTOM, y), _lerp(DECK, y), _lerp(FIN, y)
    half = [(0.0, zb - 0.01), (w * 0.8, zb), (w * 0.97, zb + 0.08), (w, zb + 0.22),
            (w * 1.005, (zb + zt) / 2 + 0.06), (w * 0.99, zt - 0.1 + fin * 0.5), (w * 0.93, zt + fin),
            (w * 0.7, zt + 0.02), (w * 0.35, zt + 0.035)]
    top = (0.0, zt + 0.04)
    left = [(-x, z) for x, z in reversed(half[1:])]
    return half + [top] + left


CAB_Y = [-0.78, -0.62, -0.3, 0.55, 0.9, 1.15]
CAB_TOP = [(-0.78, 0.92), (-0.3, 1.42), (0.55, 1.44), (1.15, 0.92)]
CAB_W = [(-0.78, 0.86), (-0.3, 0.74), (0.55, 0.75), (1.15, 0.86)]


def cab_ring(y):
    zt, wt = _lerp(CAB_TOP, y), _lerp(CAB_W, y)
    wb = 0.9
    return [(0.0, 0.9), (wb, 0.9), (wb * 0.99, 0.98), (wt + (wb - wt) * 0.25, 0.9 + (zt - 0.9) * 0.6),
            (wt, zt - 0.03), (wt * 0.6, zt), (0.0, zt + 0.01),
            (-wt * 0.6, zt), (-wt, zt - 0.03), (-(wt + (wb - wt) * 0.25), 0.9 + (zt - 0.9) * 0.6),
            (-wb * 0.99, 0.98), (-wb, 0.9)]


def _glaze(ob, paint_idx, glass_idx):
    """Window band to glass: side windows (with a B-pillar), windscreen and rear window."""
    me = ob.data
    for p in me.polygons:
        c, n = p.center, p.normal
        glass = False
        if 1.0 < c.z < 1.36:
            if abs(n.x) > 0.55:
                glass = -0.5 < c.y < 0.95 and not (0.18 < c.y < 0.3)
            elif n.y < -0.35:
                glass = abs(c.x) < 0.64
            elif n.y > 0.35:
                glass = abs(c.x) < 0.58
        p.material_index = glass_idx if glass else paint_idx


def sedan(M, paint, roof, name="car"):
    body = _loft(f"{name}_body", [FRONT + i * LENGTH / 15 for i in range(16)], body_ring, M[paint])
    _apply(body, ("SUBSURF", {"levels": 2, "render_levels": 2}))
    for ay in AXLES:                                    # wheel arches
        bpy.ops.mesh.primitive_cylinder_add(radius=WHEEL_R + 0.07, depth=2.4, vertices=32,
                                            location=(0, ay, WHEEL_R - 0.02), rotation=(0, math.pi / 2, 0))
        cut = bpy.context.active_object
        cut.data.materials.append(M["tyre"])         # the wheel well's inside: dark, and no empty slot
        _apply(body, ("BOOLEAN", {"operation": "DIFFERENCE", "object": cut}))
        bpy.data.objects.remove(cut)
    cab = _loft(f"{name}_cab", CAB_Y, cab_ring, M[roof])
    _apply(cab, ("SUBSURF", {"levels": 2, "render_levels": 2}))
    cab.data.materials.append(M["glass"])
    _glaze(cab, 0, 1)
    b = K.Builder(f"{name}_trim")
    ch, rub = M["chrome"], M["tyre"]
    for ay in AXLES:                                    # whitewall tyres, chrome hubcaps
        for s in (-1, 1):
            x = s * 0.86
            b.rod((x - 0.12, ay, WHEEL_R), (x + 0.12, ay, WHEEL_R), WHEEL_R, rub, segs=28)
            b.rod((x + s * 0.12, ay, WHEEL_R), (x + s * 0.124, ay, WHEEL_R), WHEEL_R * 0.8, M["whitewall"], segs=28)
            b.rod((x + s * 0.124, ay, WHEEL_R), (x + s * 0.128, ay, WHEEL_R), WHEEL_R * 0.55, rub, segs=28)
            b.rod((x + s * 0.128, ay, WHEEL_R), (x + s * 0.16, ay, WHEEL_R), WHEEL_R * 0.45, ch, segs=24, r2=0.05)
    for y, z in ((FRONT - 0.04, 0.42), (REAR + 0.04, 0.44)):            # wraparound bumpers
        b.rod((-0.86, y, z), (0.86, y, z), 0.075, ch, segs=14)
        for s in (-1, 1):
            b.rod((s * 0.86, y, z), (s * 1.0, y + (0.35 if y < 0 else -0.35), z), 0.07, ch, segs=12)
    for s in (-1, 1):                                    # bumper guards ("Dagmars"), headlights
        b.rod((s * 0.42, FRONT - 0.08, 0.42), (s * 0.42, FRONT - 0.2, 0.44), 0.06, ch, segs=12, r2=0.035)
        b.rod((s * 0.68, FRONT + 0.12, 0.7), (s * 0.68, FRONT + 0.02, 0.7), 0.13, ch, segs=24)
        b.rod((s * 0.68, FRONT + 0.03, 0.7), (s * 0.68, FRONT - 0.01, 0.7), 0.105, M["lens"], segs=24, r2=0.08)
        b.rod((s * 0.84, REAR - 0.12, 0.76), (s * 0.84, REAR + 0.01, 0.77), 0.055, M["tail"], segs=16)   # fin lights
        b.rod((s * 0.995, FRONT + 0.5, 0.66), (s * 0.995, REAR - 0.4, 0.68), 0.016, ch, segs=8)       # side spear
    b.box((1.15, 0.08, 0.2), (0, FRONT + 0.02, 0.56), M["grille_back"], bevel=0.04)  # grille
    for k in range(4):
        b.rod((-0.56, FRONT - 0.02, 0.48 + k * 0.055), (0.56, FRONT - 0.02, 0.48 + k * 0.055), 0.012, ch, segs=8)
    b.rod((0, FRONT + 0.4, 0.86), (0, FRONT + 0.15, 0.84), 0.03, ch, segs=10, r2=0.012)   # bonnet ornament
    trim = b.build()
    return K.join([body, cab, trim], name)


def materials():
    """Car paints and parts, merged into build_drivein.py's material dict."""
    paint = lambda n, c: K.material(n, c, rough=0.14, metal=0.25)   # noqa: E731
    return {
        "p_turq": paint("paint_turquoise", (0.06, 0.38, 0.36)),
        "p_red": paint("paint_red", (0.45, 0.02, 0.03)),
        "p_pink": paint("paint_pink", (0.75, 0.33, 0.4)),
        "p_mint": paint("paint_mint", (0.35, 0.6, 0.45)),
        "p_yellow": paint("paint_yellow", (0.8, 0.62, 0.22)),
        "p_black": paint("paint_black", (0.015, 0.015, 0.018)),
        "p_blue": paint("paint_blue", (0.05, 0.12, 0.4)),
        "p_white": paint("paint_white", (0.8, 0.78, 0.72)),
        "whitewall": K.material("whitewall", (0.82, 0.8, 0.76), rough=0.7),
        "lens": K.material("headlamp_lens", (0.7, 0.72, 0.7), rough=0.08),
        "grille_back": K.material("grille_back", (0.01, 0.01, 0.01), rough=0.6),
    }
