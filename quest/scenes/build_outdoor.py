"""Foregrounds for the photo-sky rooms, light-baked to GLBs:

  terrace   "Sunset hills": a stone cliff terrace with a brass cable railing, wooden sun loungers,
            planters, string lights on posts, an armchair for you and a side table with a lantern.
  stargaze  "Night sky": a wooden stargazing deck on a meadow, an outdoor sofa with cushions,
            fairy lights, lanterns and a telescope pointing at the Milky Way.

  blender -b -P quest/scenes/build_outdoor.py -- --scene terrace --preview out.png
  blender -b -P quest/scenes/build_outdoor.py -- --scene stargaze --bake 4096 --samples 384

Models: Poly Haven (CC0). Viewer at the origin, screen towards -Y. The 360° photo stays the sky.
"""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402
import screens as S  # noqa: E402

SCENE = K.arg("--scene", "terrace")
# Screens (width, distance, centre height) - must match Rooms.kt
TERRACE_SCREEN = (4.8, 4.6, 1.9)       # a rooftop-cinema screen standing on the terrace
STARGAZE_SCREEN = (9.0, 10.0, 3.2)     # a truss screen standing in the meadow
RES = K.HERE.parent / "app" / "src" / "main" / "res" / "drawable-nodpi"


def world(image, strength):
    w = bpy.data.worlds.new("sky")
    bpy.context.scene.world = w
    nt = w.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(RES / image))
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = strength
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])


def string_lights(b, bulb, wire, a, c, n=18, sag=0.45):
    """A sagging string of glowing bulbs from point a to point c."""
    pts = []
    for i in range(n + 1):
        t = i / n
        x = a[0] + (c[0] - a[0]) * t
        y = a[1] + (c[1] - a[1]) * t
        z = a[2] + (c[2] - a[2]) * t - sag * 4 * t * (1 - t)
        pts.append((x, y, z))
    for p, q in zip(pts, pts[1:]):
        mid = [(p[i] + q[i]) / 2 for i in range(3)]
        length = math.dist(p, q)
        yaw = math.degrees(math.atan2(q[1] - p[1], q[0] - p[0]))
        pitch = math.degrees(math.atan2(q[2] - p[2], math.hypot(q[0] - p[0], q[1] - p[1])))
        b.box((length, 0.012, 0.012), mid, wire, rot=(0, -pitch, yaw))
    for p in pts[1:-1]:
        b.cyl(0.035, 0.07, (p[0], p[1], p[2] - 0.06), bulb, segs=10)
    return pts[1:-1]


def lounger(b, wood, cushion, x, y, yaw):
    r = math.radians(yaw)
    def at(dx, dy):
        return (x + dx * math.cos(r) - dy * math.sin(r), y + dx * math.sin(r) + dy * math.cos(r))
    for i in range(9):                                            # slatted bed
        px, py = at(0, -0.9 + i * 0.2)
        b.box((0.62, 0.14, 0.04), (px, py, 0.32), wood, rot=(0, 0, yaw), bevel=0.01)
    for dx in (-0.3, 0.3):
        for dy in (-0.85, 0.75):
            px, py = at(dx, dy)
            b.box((0.05, 0.05, 0.3), (px, py, 0.15), wood)
    px, py = at(0, -0.15)
    b.box((0.6, 1.45, 0.08), (px, py, 0.39), cushion, rot=(0, 0, yaw), bevel=0.035, segs=3)
    px, py = at(0, 0.85)
    b.box((0.6, 0.55, 0.08), (px, py, 0.6), cushion, rot=(-40, 0, yaw), bevel=0.035, segs=3)


def terrace():
    stone = K.material("limestone", (0.55, 0.5, 0.42), rough=0.7, noise=0.25, scale=4)
    grout = K.material("grout", (0.25, 0.23, 0.2), rough=0.9)
    brass = K.material("brass", (0.8, 0.6, 0.3), rough=0.3, metal=1.0)
    teak = K.material("teak", (0.32, 0.17, 0.08), rough=0.55, noise=0.4, scale=8)
    canvas = K.material("cushion_cream", (0.75, 0.7, 0.6), rough=0.85, noise=0.1, scale=60)
    iron = K.material("black_iron", (0.03, 0.03, 0.03), rough=0.5, metal=0.7)
    bulb = K.material("bulb", (1, 0.85, 0.6), emit=(1, 0.75, 0.45), emit_strength=20)
    b = K.Builder("terrace")
    b.box((14.4, 10.4, 0.5), (0, -0.6, -0.27), grout)
    for ix in range(-12, 12):                                      # stone tiles
        for iy in range(-9, 8):
            b.box((0.58, 0.58, 0.05), (ix * 0.6 + 0.3, iy * 0.6 - 0.3, -0.02), stone, bevel=0.01, segs=1)
    b.box((14.4, 0.4, 0.45), (0, -5.75, 0.2), stone, bevel=0.03)                 # parapet at the edge
    for x in [i * 1.2 for i in range(-6, 7)]:                      # brass cable railing
        b.box((0.05, 0.05, 0.6), (x, -5.75, 0.72), brass)
    for z in (0.62, 0.8, 0.98):
        b.box((14.4, 0.012, 0.012), (0, -5.75, z), brass)
    b.box((14.4, 0.07, 0.04), (0, -5.75, 1.04), brass, bevel=0.015)
    S.outdoor_screen(b, S.mats(), *TERRACE_SCREEN, ground=0.0, tower_extra=0.35, guys=False, foot=0.75)
    lounger(b, teak, canvas, -3.0, -1.0, 15)
    lounger(b, teak, canvas, 3.0, -1.0, -15)
    lounger(b, teak, canvas, 4.6, 1.2, -25)
    posts = [(-6.5, -5.2), (6.5, -5.2), (-6.5, 3.8), (6.5, 3.8)]
    for x, y in posts:
        b.box((0.1, 0.1, 3.2), (x, y, 1.6), iron)
    bulbs = []
    for a, c in [(posts[0], posts[3]), (posts[1], posts[2]), (posts[0], posts[1]), (posts[2], posts[3])]:
        bulbs += string_lights(b, bulb, iron, (a[0], a[1], 3.15), (c[0], c[1], 3.15), n=16, sag=0.5)
    floor = b.build()
    parts = []
    chair = K.polyhaven("ArmChair_01")
    K.place(chair, (0, 0.1, 0), 0, 1.0)
    parts += chair
    table = K.polyhaven("side_table_01")
    K.place(table, (0.9, 0.0, 0), 0, 1.0)
    parts += table
    lamp = K.polyhaven("wooden_lantern_01")
    K.place(lamp, (0.9, 0.0, 0.55), 30, 1.0)
    parts += lamp
    for x, y in [(-6.2, -4.6), (6.2, -4.6), (-6.2, 3.2), (6.2, 3.2)]:
        box = K.polyhaven("planter_box_01")
        K.place(box, (x, y, 0), 90, 1.4)
        parts += box
    props = K.join(parts, "terrace_props")
    plants = []
    for x, y in [(-6.2, -4.6), (6.2, -4.6), (-6.2, 3.2), (6.2, 3.2)]:
        p = K.polyhaven("calathea_orbifolia_01", res="1k")
        K.place(p, (x, y, 0.45), x * 20, 1.6)
        plants += p
    green = K.join(plants, "terrace_plants")
    for p in bulbs[::4]:
        K.add_light("POINT", (p[0], p[1], p[2] - 0.1), 6, (1, 0.75, 0.45), 0.05)
    K.add_light("POINT", (0.9, 0.0, 0.85), 15, (1, 0.7, 0.4), 0.05)
    data = bpy.data.lights.new("sun", "SUN")
    data.energy = 2.2
    data.color = (1.0, 0.62, 0.38)
    sun = bpy.data.objects.new("sun", data)
    sun.rotation_euler = (math.radians(80), 0, math.radians(180))     # low, from ahead: golden backlight
    bpy.context.scene.collection.objects.link(sun)
    world("sky_sunset.jpg", 1.1)
    K.screen_light(*TERRACE_SCREEN, 2000)
    return [floor, props], [green]


def stargaze():
    grass = K.material("earth", (0.05, 0.035, 0.025), rough=0.95, noise=0.55, scale=4)
    plank = K.material("deck_wood", (0.22, 0.13, 0.07), rough=0.7, noise=0.45, scale=10)
    dark = K.material("deck_frame", (0.08, 0.05, 0.03), rough=0.8)
    iron = K.material("black_iron", (0.03, 0.03, 0.03), rough=0.5, metal=0.7)
    bulb = K.material("fairy_bulb", (1, 0.85, 0.6), emit=(1, 0.75, 0.45), emit_strength=25)
    brass = K.material("brass", (0.8, 0.6, 0.3), rough=0.3, metal=1.0)
    scope = K.material("telescope", (0.85, 0.85, 0.86), rough=0.3, metal=0.2)
    wool = K.material("blanket", (0.35, 0.08, 0.06), rough=0.95, noise=0.3, scale=40)
    b = K.Builder("stargaze")
    b.cyl(30.0, 0.3, (0, 0, -0.45), grass, segs=96)
    for i in range(-20, 21):                                        # deck planks
        b.box((0.14, 7.0, 0.04), (i * 0.15, -0.8, -0.02), plank, bevel=0.005, segs=1)
    b.box((6.3, 7.2, 0.28), (0, -0.8, -0.18), dark)
    b.box((1.6, 0.9, 0.03), (0, 0.1, 0.002), wool, bevel=0.01)                 # rug under your feet
    posts = [(-3.1, -4.3), (3.1, -4.3), (-3.1, 2.7), (3.1, 2.7)]
    for x, y in posts:
        b.box((0.08, 0.08, 2.6), (x, y, 1.3), plank)
    bulbs = []
    for a, c in [(posts[0], posts[3]), (posts[1], posts[2]), (posts[2], posts[3])]:
        bulbs += string_lights(b, bulb, iron, (a[0], a[1], 2.55), (c[0], c[1], 2.55), n=22, sag=0.35)
    S.outdoor_screen(b, S.mats(), *STARGAZE_SCREEN, ground=-0.3)
    # Telescope on a tripod to the right, pointing up at the sky
    tx, ty = 2.8, -2.6
    for k in range(3):
        a = math.radians(k * 120)
        b.box((0.03, 0.03, 1.25), (tx + 0.25 * math.cos(a), ty + 0.25 * math.sin(a), 0.6), iron,
              rot=(12 * math.sin(a), -12 * math.cos(a), 0))
    b.cyl(0.07, 0.12, (tx, ty, 1.22), brass, segs=16)
    b.box((0.16, 1.1, 0.16), (tx, ty - 0.2, 1.45), scope, rot=(35, 0, 0), bevel=0.07, segs=4)
    floor = b.build()
    parts = []
    sofa = K.polyhaven("Sofa_01")
    K.place(sofa, (0, 0.25, 0), 180, 1.0)
    parts += sofa
    pillows = K.polyhaven("throw_pillows_01")
    K.place(pillows, (0, 0.25, 0.45), 180, 1.0)
    parts += pillows
    for x, y in [(-2.6, -3.8), (2.6, -3.8), (-2.6, 2.2)]:
        lamp = K.polyhaven("Lantern_01")
        K.place(lamp, (x, y, 0), x * 30, 1.0)
        parts += lamp
        K.add_light("POINT", (x, y, 0.35), 12, (1, 0.65, 0.35), 0.05)
    table = K.polyhaven("side_table_01")
    K.place(table, (-1.2, 0.15, 0), 0, 1.0)
    parts += table
    candle = K.polyhaven("wooden_lantern_01")
    K.place(candle, (-1.2, 0.15, 0.55), 0, 1.0)
    parts += candle
    K.add_light("POINT", (-1.2, 0.15, 0.85), 10, (1, 0.7, 0.4), 0.05)
    props = K.join(parts, "stargaze_props")
    for p in bulbs[::5]:
        K.add_light("POINT", (p[0], p[1], p[2] - 0.1), 4, (1, 0.75, 0.45), 0.05)
    world("sky_night.jpg", 0.9)
    K.screen_light(*STARGAZE_SCREEN, 6000)
    return [floor, props], []


def main():
    K.reset()
    baked, plain = {"terrace": terrace, "stargaze": stargaze}[SCENE]()
    print("triangles:", sum(len(o.data.polygons) for o in baked + plain))
    if "--preview" in K.ARGS:
        K.setup_cycles(int(K.arg("--samples", 64)))
        K.dim_screens()
        cam = bpy.data.cameras.new("cam")
        cam.lens = float(K.arg("--lens", 14))
        ob = bpy.data.objects.new("cam", cam)
        ob.location = (0.0, float(K.arg("--back", 0.0)), float(K.arg("--eye", 1.15)))
        ob.rotation_euler = (math.radians(float(K.arg("--pitch", 86))), 0, math.radians(180 + float(K.arg("--yaw", 0))))
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        r.resolution_x, r.resolution_y = 1600, 900
        r.filepath = K.arg("--preview")
        bpy.ops.render.render(write_still=True)
        return
    K.bake_all(baked, int(K.arg("--bake", 4096)), int(K.arg("--samples", 320)))
    K.export(baked, SCENE)
    if plain:
        K.export(plain, f"{SCENE}_plants")


main()
