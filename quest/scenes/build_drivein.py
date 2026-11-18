"""The "Drive-in" room: you sit in an open 1950s convertible (dashboard, steering wheel, glowing
dials, long red bonnet) facing a huge outdoor screen on a steel tower with a neon sign. Two-tone
1950s sedans (cars.py) with speaker posts are parked ahead, street lamps and strings of festoon
bulbs light the tarmac, and fire barrels burn between the rows (their flames are live in the app,
Rooms.kt). Lit by the night sky, the screen's glow, the lamps, bulbs, fires and the neon, baked
into a GLB.

  blender -b -P quest/scenes/build_drivein.py -- --preview out.png
  blender -b -P quest/scenes/build_drivein.py -- --bake 4096 --samples 384

Viewer at the origin (eye about 1.15 m), screen towards -Y (Rooms.kt: DriveIn spot).
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Matrix, Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402
import cars as C  # noqa: E402
import screens as S  # noqa: E402

SCREEN_W, SCREEN_D, SCREEN_Z = 18.0, 30.0, 8.5
BARRELS = [(-3.6, -2.2), (5.4, -10.8), (-5.6, -17.5)]     # fire barrels: Rooms.kt DriveIn fires
BARREL_TOP = 0.86
SKY = K.HERE.parent / "app" / "src" / "main" / "res" / "drawable-nodpi" / "sky_drivein.jpg"


def mats():
    return {
        "tarmac": K.material("tarmac", (0.045, 0.045, 0.05), rough=0.85, noise=0.4, scale=9),
        "line": K.material("paint_line", (0.75, 0.72, 0.6), rough=0.7),
        "red": K.material("car_red", (0.42, 0.02, 0.025), rough=0.18, metal=0.35),
        "cream": K.material("car_cream", (0.75, 0.68, 0.5), rough=0.2, metal=0.3),
        "teal": K.material("car_teal", (0.05, 0.3, 0.3), rough=0.2, metal=0.35),
        "black": K.material("car_black", (0.02, 0.02, 0.022), rough=0.25, metal=0.4),
        "blue": K.material("car_blue", (0.04, 0.09, 0.3), rough=0.2, metal=0.35),
        "chrome": K.material("chrome", (0.85, 0.85, 0.88), rough=0.08, metal=1.0),
        "tyre": K.material("tyre", (0.015, 0.015, 0.015), rough=0.8),
        "glass": K.material("glass_dark", (0.02, 0.025, 0.03), rough=0.05),
        "dash": K.material("dashboard", (0.30, 0.04, 0.04), rough=0.4),
        "seat": K.material("leather_cream", (0.7, 0.62, 0.48), rough=0.5, noise=0.08, scale=40),
        "dial": K.material("dials", (0.9, 0.85, 0.6), emit=(1.0, 0.8, 0.45), emit_strength=2.5),
        "tail": K.material("tail_light", (1, 0.05, 0.03), emit=(1, 0.04, 0.02), emit_strength=4),
        "steel": K.material("steel", (0.25, 0.26, 0.28), rough=0.4, metal=0.9),
        "trim": K.material("painted_trim", (0.78, 0.76, 0.7), rough=0.6, noise=0.2, scale=6),
        "deco": K.material("deco_render", (0.6, 0.55, 0.48), rough=0.8, noise=0.3, scale=3),
        "concrete": K.material("concrete", (0.3, 0.3, 0.29), rough=0.9, noise=0.4, scale=5),
        "flood": K.material("floodlight", (1, 0.95, 0.85), emit=(1, 0.92, 0.8), emit_strength=6),
        "screen": K.material("screen_face", (0.55, 0.55, 0.56), rough=0.9),
        "neon": K.material("neon_pink", (1, 0.2, 0.6), emit=(1, 0.15, 0.55), emit_strength=18),
        "neon2": K.material("neon_blue", (0.2, 0.6, 1), emit=(0.2, 0.6, 1.0), emit_strength=14),
        "post": K.material("speaker_post", (0.25, 0.27, 0.25), rough=0.5, metal=0.6),
        "bulb": K.material("festoon_bulb", (1, 0.85, 0.6), emit=(1, 0.72, 0.4), emit_strength=30),
        "wire": K.material("wire", (0.02, 0.02, 0.02), rough=0.6),
        "wood_pole": K.material("wood_pole", (0.12, 0.08, 0.05), rough=0.85, noise=0.3, scale=10),
        "coals": K.glowing("barrel_coals", (0.02, 0.015, 0.012), (1.0, 0.3, 0.05), threshold=0.42, strength=8, scale=10),
        **C.materials(),
    }


def own_car(b, M):
    """The convertible you sit in: no roof, so the sky is all yours."""
    b.rod((0, -2.9, 0.9), (0, -0.6, 0.94), 0.018, M["chrome"], segs=8)                   # bonnet trim
    b.rod((0, -2.95, 0.9), (0, -2.75, 0.93), 0.035, M["chrome"], segs=10, r2=0.012)       # ornament
    b.box((1.86, 0.32, 0.26), (0, -0.48, 0.70), M["dash"], bevel=0.1, segs=3)            # dashboard
    for sx in (-0.88, 0.88):
        b.box((0.16, 3.6, 0.55), (sx * 1.02, 0.2, 0.62), M["red"], bevel=0.07, segs=3)   # doors / sides
    for dx in (-0.55, -0.32):
        b.cyl(0.07, 0.02, (dx, -0.31, 0.88), M["dial"], segs=24)                         # glowing dials
    b.cyl(0.19, 0.03, (-0.38, -0.25, 0.92), M["black"], segs=32)                        # steering wheel
    b.cyl(0.16, 0.035, (-0.38, -0.25, 0.92), M["dash"], segs=32)
    b.box((1.7, 0.6, 0.18), (0, 0.15, 0.42), M["seat"], bevel=0.07, segs=3)             # bench seat
    b.box((1.7, 0.16, 0.6), (0, 0.48, 0.72), M["seat"], rot=(-12, 0, 0), bevel=0.07, segs=3)


BONNET_W = [(-3.15, 0.8), (-2.9, 0.92), (-0.5, 0.96)]
BONNET_TOP = [(-3.15, 0.66), (-2.85, 0.8), (-0.5, 0.9)]


def bonnet_ring(y):
    """Your convertible's long bonnet: raised fenders either side of a lower centre."""
    w, zt = C._lerp(BONNET_W, y), C._lerp(BONNET_TOP, y)
    half = [(0.0, 0.3), (w * 0.85, 0.3), (w, 0.48), (w * 1.01, 0.68), (w * 0.97, zt + 0.02),
            (w * 0.82, zt + 0.06), (w * 0.62, zt), (w * 0.3, zt - 0.015)]
    return half + [(0.0, zt - 0.01)] + [(-x, z) for x, z in reversed(half[1:])]


def own_bonnet(M):
    ob = C._loft("own_bonnet", [-3.15 + i * 2.65 / 10 for i in range(11)], bonnet_ring, M["red"])
    C._apply(ob, ("SUBSURF", {"levels": 2, "render_levels": 2}))
    b = K.Builder("own_front")
    for s_ in (-1, 1):                                               # headlights, bumper
        b.rod((s_ * 0.74, -3.0, 0.72), (s_ * 0.74, -3.14, 0.72), 0.13, M["chrome"], segs=24)
        b.rod((s_ * 0.74, -3.13, 0.72), (s_ * 0.74, -3.17, 0.72), 0.105, M["lens"], segs=24, r2=0.08)
    b.rod((-0.9, -3.22, 0.42), (0.9, -3.22, 0.42), 0.075, M["chrome"], segs=14)
    return K.join([ob, b.build()], "own_bonnet")


def parked_cars(M):
    """Two rows of two-tone sedans facing the screen, the middle lane kept clear."""
    combos = [("p_turq", "p_white"), ("p_pink", "p_white"), ("p_black", "p_black"), ("p_yellow", "p_white"),
              ("p_red", "p_white"), ("p_mint", "p_white"), ("p_blue", "p_white"), ("p_white", "p_red")]
    out, i = [], 0
    for y in (-7.5, -14.0):
        for x in (-12, -8, 8, 12):
            paint, roof = combos[i % len(combos)]
            car = C.sedan(M, paint, roof, f"car{i}")
            car.matrix_world = Matrix.Translation((x + (0.6 if y < -10 else 0), y, 0)) @                 Matrix.Rotation(math.radians((i * 37 % 7) - 3), 4, "Z")   # not parked quite straight
            out.append(car)
            i += 1
    return K.join(out, "drivein_cars")


def festoon(b, M, p, q, sag=0.45, spacing=0.75):
    """A string of warm bulbs hanging from p to q, dipping [sag] in the middle."""
    p, q = Vector(p), Vector(q)
    n = max(2, round((q - p).length / spacing))
    pts = [p.lerp(q, t / n) - Vector((0, 0, sag * 4 * (t / n) * (1 - t / n))) for t in range(n + 1)]
    for a, c in zip(pts, pts[1:]):
        b.rod(a, c, 0.006, M["wire"], segs=5)
    for a in pts[1:-1]:
        b.rod(a, a - Vector((0, 0, 0.1)), 0.035, M["bulb"], segs=8, r2=0.02)


def string_lights(b, M):
    """Festoon lights on wooden poles down both sides of the lot and behind you: kept out of the
    line between your seat and the screen."""
    ys = [4.0 - k * 6.8 for k in range(5)]
    for x in (-15.0, 15.0):
        for y in ys:
            b.rod((x, y, 0), (x, y, 4.3), 0.07, M["wood_pole"], segs=10)
        for y0, y1 in zip(ys, ys[1:]):
            festoon(b, M, (x, y0, 4.1), (x, y1, 4.1))
    xs = [-15.0 + k * 6.0 for k in range(6)]
    for x in xs[1:-1]:
        b.rod((x, 4.0, 0), (x, 4.0, 4.3), 0.07, M["wood_pole"], segs=10)
    for x0, x1 in zip(xs, xs[1:]):
        festoon(b, M, (x0, 4.0, 4.1), (x1, 4.0, 4.1))


def barrels(M):
    parts = []
    b = K.Builder("barrel_coals")
    for x, y in BARRELS:
        drum = K.polyhaven("barrel_stove")
        K.place(drum, (x, y, 0), x * 25, 1.0)
        parts += drum
        b.cyl(0.27, 0.06, (x, y, BARREL_TOP - 0.08), M["coals"], segs=24)          # glowing inside
        K.add_light("POINT", (x, y, BARREL_TOP + 0.35), 260, (1.0, 0.5, 0.17), 0.3)
    parts.append(b.build())
    return K.join(parts, "drivein_barrels")


def build():
    M = mats()
    b = K.Builder("drivein")
    b.cyl(90.0, 0.2, (0, 0, -0.1), M["tarmac"], segs=128)
    for row in range(-1, 4):                                         # parking bays
        y = -6 - row * 6.5
        for x in range(-20, 21, 4):
            b.box((0.1, 4.8, 0.005), (x, y, 0.003), M["line"])
    own_car(b, M)
    for y in (-7.5, -14.0):                                          # speaker posts by the parked cars
        for x in (-12, -8, 8, 12):
            b.cyl(0.04, 1.1, (x - 1.5, y - 1.0, 0.55), M["post"], segs=8)
            b.box((0.24, 0.1, 0.3), (x - 1.5, y - 1.0, 1.15), M["post"], bevel=0.03)
    string_lights(b, M)
    b.cyl(0.04, 1.1, (-1.4, -0.4, 0.55), M["post"], segs=8)                           # your speaker
    b.box((0.24, 0.1, 0.3), (-1.2, -0.4, 1.0), M["post"], bevel=0.03)
    # Screen tower: white-trimmed face on a steel tower, lattice trusses behind, art-deco pylons
    # with neon either side, floodlights on arms along the top, the neon sign below
    hw, hh = SCREEN_W / 2, SCREEN_W * 9 / 32
    y = -SCREEN_D
    b.box((SCREEN_W + 1.6, 0.4, 2 * hh + 1.6), (0, y - 0.5, SCREEN_Z), M["steel"])
    b.box((SCREEN_W + 0.1, 0.05, 2 * hh + 0.1), (0, y - 0.28, SCREEN_Z), M["screen"])
    for z in (SCREEN_Z + hh + 0.3, SCREEN_Z - hh - 0.3):                 # painted trim
        b.box((SCREEN_W + 1.4, 0.16, 0.5), (0, y - 0.3, z), M["trim"], bevel=0.04)
    for s_ in (-1, 1):
        b.box((0.5, 0.16, 2 * hh + 1.1), (s_ * (hw + 0.45), y - 0.3, SCREEN_Z), M["trim"], bevel=0.04)
    top = SCREEN_Z + hh + 0.8
    for x in (-hw * 0.8, -hw * 0.27, hw * 0.27, hw * 0.8):                 # lattice towers behind
        S.truss(b, (x, y - 1.3, 0.05), (x, y - 1.3, top), M["steel"], size=0.6, chord=0.08, lace=0.04)
        S.beam(b, (x, y - 1.3, top - 1.0), (x, y - 5.5, 0.05), (0.14, 0.14), M["steel"])
        b.box((1.0, 1.0, 0.3), (x, y - 1.3, 0.15), M["concrete"])
        b.box((0.6, 0.6, 0.25), (x, y - 5.5, 0.12), M["concrete"])
    S.truss(b, (-hw * 0.8, y - 1.3, top - 0.3), (hw * 0.8, y - 1.3, top - 0.3), M["steel"], size=0.6, chord=0.08, lace=0.04)
    S.truss(b, (-hw * 0.8, y - 1.3, 3.0), (hw * 0.8, y - 1.3, 3.0), M["steel"], size=0.6, chord=0.08, lace=0.04)
    for s_ in (-1, 1):                                                      # art-deco pylons
        px = s_ * (hw + 1.9)
        ph = SCREEN_Z + hh + 1.4
        b.box((1.5, 1.3, ph), (px, y - 0.4, ph / 2), M["deco"], bevel=0.05)
        b.box((1.1, 1.0, 1.0), (px, y - 0.4, ph + 0.5), M["deco"], bevel=0.05)
        b.box((0.7, 0.7, 0.8), (px, y - 0.4, ph + 1.4), M["deco"], bevel=0.05)
        for k in (-1, 0, 1):
            b.box((0.07, 0.05, ph - 1.5), (px + k * 0.38, y + 0.27, ph / 2 + 0.4), M["neon2"])
        b.box((1.7, 1.5, 0.4), (px, y - 0.4, 0.2), M["concrete"], bevel=0.03)
    for i in range(6):                                                      # floodlights on arms
        fx = -hw + (i + 0.5) * SCREEN_W / 6
        S.beam(b, (fx, y - 0.3, SCREEN_Z + hh + 0.55), (fx, y + 1.2, SCREEN_Z + hh + 1.0), (0.08, 0.08), M["steel"])
        b.box((0.45, 0.35, 0.3), (fx, y + 1.3, SCREEN_Z + hh + 1.0), M["black"], rot=(35, 0, 0), bevel=0.04)
        b.box((0.36, 0.02, 0.22), (fx, y + 1.42, SCREEN_Z + hh + 0.88), M["flood"], rot=(35, 0, 0))
    b.box((9.0, 0.3, 1.2), (0, y + 0.6, SCREEN_Z - hh - 1.5), M["black"], bevel=0.1)
    b.box((9.4, 0.2, 0.08), (0, y + 0.6, SCREEN_Z - hh - 0.86), M["chrome"], bevel=0.02)
    b.box((9.4, 0.2, 0.08), (0, y + 0.6, SCREEN_Z - hh - 2.14), M["chrome"], bevel=0.02)
    return b.build(), M


def sign(M):
    """Neon "BUZZ DRIVE-IN" lettering under the screen."""
    hh = SCREEN_W * 9 / 32
    bpy.ops.object.text_add(location=(0, -SCREEN_D + 0.42, SCREEN_Z - hh - 1.5))
    t = bpy.context.active_object
    t.data.body = "BUZZ DRIVE-IN"
    t.data.align_x = "CENTER"
    t.data.align_y = "CENTER"
    t.data.size = 0.85
    t.data.extrude = 0.04
    t.rotation_euler = (math.radians(90), 0, 0)
    t.data.materials.append(M["neon"])
    bpy.ops.object.convert(target="MESH")
    t.name = "sign"
    return t


def lamps():
    parts = []
    for x, y in [(-18, -4), (18, -4), (-18, -18), (18, -18)]:
        lamp = K.polyhaven("street_lamp_01", res="1k")
        K.place(lamp, (x, y, 0), 90 if x < 0 else -90, 1.0)
        parts += lamp
        K.add_light("POINT", (x + (1.2 if x < 0 else -1.2), y, 5.8), 900, (1.0, 0.72, 0.42), 0.15)
    return K.join(parts, "drivein_lamps") if parts else None


def lighting():
    hh = SCREEN_W * 9 / 32
    K.screen_light(SCREEN_W, SCREEN_D - 0.25, SCREEN_Z, 100000)
    K.add_light("AREA", (0, -SCREEN_D + 1.0, SCREEN_Z - hh - 1.5), 600, (1, 0.25, 0.6), (8, 1), rot=(-90, 0, 0))
    world = bpy.data.worlds.new("night")
    bpy.context.scene.world = world
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(SKY))
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.6
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])


def main():
    K.reset()
    lighting()
    lot, M = build()
    neon = sign(M)
    lamp = lamps()
    lot = K.join([lot, neon, own_bonnet(M)], "drivein")
    objs = [o for o in (lot, lamp, parked_cars(M), barrels(M)) if o]
    print("triangles:", sum(len(o.data.polygons) for o in objs))
    if "--preview" in K.ARGS:
        K.setup_cycles(int(K.arg("--samples", 64)))
        K.dim_screens()
        cam = bpy.data.cameras.new("cam")
        cam.lens = 16
        ob = bpy.data.objects.new("cam", cam)
        ob.location = (0.0, 0.0, 1.15)
        ob.rotation_euler = (math.radians(float(K.arg("--pitch", 96))), 0, math.radians(180 + float(K.arg("--yaw", 0))))
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        r.resolution_x, r.resolution_y = 1600, 900
        r.filepath = K.arg("--preview")
        bpy.ops.render.render(write_still=True)
        return
    K.bake_all(objs, int(K.arg("--bake", 4096)), int(K.arg("--samples", 320)))
    K.export(objs, "drivein")


main()
