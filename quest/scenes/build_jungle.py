"""The "Jungle camp" room: a clearing at dusk with a campfire in a stone pit, a brass diya on a crate,
a tent, a fallen trunk to sit on and the screen hung between wooden posts. The forest photo
(Rooms.kt's sky) stays as the backdrop; this builds what's near you, lit by the fire and the
dusk sky, and bakes it into GLBs. Plants keep their own leaf textures (with cut-outs) and are
exported unbaked.

  blender -b -P quest/scenes/build_jungle.py -- --preview out.png
  blender -b -P quest/scenes/build_jungle.py -- --bake 4096 --samples 384

Models: Poly Haven (CC0). Viewer at the origin, screen towards -Y (Rooms.kt: Jungle spot).
"""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402
import screens as S  # noqa: E402

SCREEN_W, SCREEN_D, SCREEN_Z = 6.0, 7.5, 2.4
SKY = K.HERE.parent / "app" / "src" / "main" / "res" / "drawable-nodpi" / "sky_jungle.jpg"
FIRE = (1.9, -1.5, 0.0)


def ground():
    soil = K.material("forest_floor", (0.032, 0.026, 0.016), rough=0.95, noise=0.55, scale=6)
    canvas = K.material("tent_canvas", (0.20, 0.27, 0.15), rough=0.85, noise=0.15, scale=30)
    canvas_dark = K.material("tent_inside", (0.02, 0.025, 0.02), rough=0.95)
    wood = K.material("posts", (0.13, 0.08, 0.045), rough=0.8, noise=0.35, scale=12)
    cloth = K.material("screen_backing", (0.02, 0.02, 0.02), rough=0.95)
    rope = K.material("rope", (0.35, 0.28, 0.18), rough=0.9)
    b = K.Builder("jungle_ground")
    b.cyl(16.0, 0.3, (0, 0, -0.15), soil, segs=96)
    # Screen between two rough posts, a crossbar, ropes and a dark backing
    hw = SCREEN_W / 2
    h = SCREEN_W * 9 / 16
    for s in (-1, 1):
        b.cyl(0.11, SCREEN_Z + h / 2 + 0.6, (s * (hw + 0.25), -SCREEN_D - 0.15, (SCREEN_Z + h / 2 + 0.6) / 2), wood)
        b.box((0.02, 0.02, 1.2), (s * (hw + 0.25), -SCREEN_D + 0.6, SCREEN_Z + h / 2 - 0.1), rope, rot=(-38, 0, 0))
    b.box((SCREEN_W + 0.9, 0.16, 0.16), (0, -SCREEN_D - 0.15, SCREEN_Z + h / 2 + 0.25), wood, bevel=0.03)
    b.box((SCREEN_W + 0.2, 0.03, h + 0.2), (0, -SCREEN_D - 0.08, SCREEN_Z), cloth)
    camp_screen(b, wood, rope, hw, h)
    # A-frame tent to the left, door open towards you
    tx, ty = -3.6, -0.4
    for s in (-1, 1):
        b.box((1.25, 2.6, 0.03), (tx + s * 0.55, ty, 0.62), canvas, rot=(0, s * -48, 10), bevel=0.01)
    b.box((1.6, 0.02, 1.1), (tx, ty + 1.28, 0.5), canvas_dark, rot=(0, 0, 10))
    b.cyl(0.03, 1.5, (tx, ty + 1.35, 0.75), wood, segs=8)
    return b.build()


def camp_screen(b, wood, rope, hw, h):
    """The sheet laced into a pole frame: masking hem, ropes through grommets to the poles,
    lashed joints, guy ropes to stakes, hanging lanterns and two wooden speakers on crates."""
    sm = S.mats()
    sheet = K.material("camp_sheet", (0.08, 0.08, 0.075), rough=0.95, noise=0.2, scale=40)
    lantern = K.material("lantern_glow", (1, 0.7, 0.35), emit=(1, 0.62, 0.3), emit_strength=12)
    y = -SCREEN_D
    border = 0.1
    S.masking(b, {**sm, "screen": sheet}, SCREEN_W, h, y, SCREEN_Z, border, depth=0.03)
    px = hw + 0.25
    top, bottom = SCREEN_Z + h / 2 + 0.25, SCREEN_Z - h / 2 - 0.35
    S.beam(b, (-px - 0.3, y - 0.15, bottom), (px + 0.3, y - 0.15, bottom), (0.12, 0.12), wood)
    sx, sz = hw + border, h / 2 + border
    n = 12
    for i in range(n + 1):                          # lacing: grommets to the poles
        x = -sx + 2 * sx * i / n
        S.beam(b, (x, y - 0.07, SCREEN_Z + sz), (x * 1.02, y - 0.15, top - 0.08), (0.012, 0.012), rope)
        S.beam(b, (x, y - 0.07, SCREEN_Z - sz), (x * 1.02, y - 0.15, bottom + 0.06), (0.012, 0.012), rope)
    for i in range(7):
        z = SCREEN_Z - sz + 2 * sz * i / 6
        for s_ in (-1, 1):
            S.beam(b, (s_ * sx, y - 0.07, z), (s_ * (px - 0.1), y - 0.15, z), (0.012, 0.012), rope)
    for s_ in (-1, 1):
        for z in (top, bottom):                     # lashings where the poles cross
            b.cyl(0.14, 0.18, (s_ * px, y - 0.15, z), rope, segs=12)
        stake = (s_ * (px + 1.6), y - 2.6, 0.0)
        S.beam(b, (s_ * px, y - 0.15, top + 0.3), stake, (0.014, 0.014), rope)
        b.box((0.05, 0.05, 0.25), (stake[0], stake[1], 0.08), wood, rot=(20, 0, 0))
        b.box((0.04, 0.04, 0.35), (s_ * px, y + 0.05, SCREEN_Z), rope)                # lantern hook
        b.box((0.16, 0.16, 0.24), (s_ * px, y + 0.12, SCREEN_Z - 0.3), lantern, bevel=0.04)
        b.box((0.2, 0.2, 0.04), (s_ * px, y + 0.12, SCREEN_Z - 0.16), sm["black_metal"], bevel=0.01)
        cx = s_ * (px + 0.9)
        b.box((0.7, 0.55, 0.45), (cx, y + 0.6, 0.225), wood, bevel=0.02)            # crate
        S.cabinet(b, sm, cx, y + 0.6, 0.45, 0.42, 0.34, 0.62, [(0.42, 0.08), (0.18, 0.11)])


def campfire():
    """A burning campfire in the pit: a bed of glowing coals, a teepee of logs charred and
    cracked with embers where the fire has them, and three big logs pushed in from the sides.
    The flames themselves are live in the app (Kit.fire)."""
    import random
    rnd = random.Random(3)
    fx, fy, _ = FIRE
    b = K.Builder("campfire")
    bark = K.material("bark", (0.04, 0.024, 0.014), rough=0.95, noise=0.7, scale=60)
    char = K.glowing("charred", (0.012, 0.01, 0.009), (1.0, 0.24, 0.03), threshold=0.56, strength=3)
    coals = K.glowing("coals", (0.015, 0.012, 0.01), (1.0, 0.25, 0.03), threshold=0.46, strength=7, scale=9)
    ash = K.material("ash", (0.06, 0.055, 0.05), rough=1.0, noise=0.5, scale=18)
    b.cyl(0.42, 0.03, (fx, fy, 0.015), ash, segs=32)
    for _ in range(46):                                     # the coal bed
        a, r = rnd.uniform(0, 6.283), 0.36 * math.sqrt(rnd.random())
        s = rnd.uniform(0.045, 0.09)
        b.box((s, s * rnd.uniform(0.7, 1.2), s * 0.7), (fx + r * math.cos(a), fy + r * math.sin(a), 0.04 + s * 0.2),
              coals, rot=(rnd.uniform(-25, 25), rnd.uniform(-25, 25), rnd.uniform(0, 90)), bevel=s * 0.25)
    for i in range(7):                                      # the teepee
        a = i / 7 * 6.283 + rnd.uniform(-0.2, 0.2)
        r = rnd.uniform(0.045, 0.06)
        foot = (fx + 0.38 * math.cos(a), fy + 0.38 * math.sin(a), 0.05)
        top = (fx + 0.05 * math.cos(a + 2), fy + 0.05 * math.sin(a + 2), rnd.uniform(0.6, 0.7))
        knee = tuple(foot[k] + (top[k] - foot[k]) * 0.5 for k in range(3))
        b.rod(foot, knee, r, bark, segs=10, r2=r * 0.95)      # outside of the log: bark
        b.rod(knee, top, r * 0.95, char, segs=10, r2=r * 0.6)  # burnt through where the flames lick
    for i in range(3):                                      # big logs pushed in from the sides
        a = i / 3 * 6.283 + 0.5
        inner = (fx + 0.12 * math.cos(a), fy + 0.12 * math.sin(a), 0.08)
        mid = (fx + 0.42 * math.cos(a), fy + 0.42 * math.sin(a), 0.08)
        outer = (fx + 0.85 * math.cos(a), fy + 0.85 * math.sin(a), 0.07)
        b.rod(inner, mid, 0.07, char, segs=12)
        b.rod(mid, outer, 0.07, bark, segs=12)
    return b.build()


def props():
    parts = []
    pit = K.polyhaven("stone_fire_pit")
    K.place(pit, FIRE, 0, 1.0)
    parts += pit
    crate = K.polyhaven("wooden_crate_01")
    K.place(crate, (0.95, -0.15, 0), 15, 0.9)
    parts += crate
    diya = K.polyhaven("brass_diya_lantern")
    K.place(diya, (0.95, -0.15, 0.55), 0, 1.0)
    parts += diya
    trunk = K.polyhaven("dead_tree_trunk_02")
    K.place(trunk, (0.0, 0.55, 0), 90, 0.6)                 # behind you: the log you sit on
    parts += trunk
    for i, (x, y, r, s) in enumerate([(4.5, -3.5, 30, 1.2), (-5.2, -5.5, 80, 1.5), (6.5, 2.0, 140, 1.0)]):
        rock = K.polyhaven("boulder_01")
        K.place(rock, (x, y, 0), r, s)
        parts += rock
    stump = K.polyhaven("tree_stump_01")                  # a seat by the fire
    K.place(stump, (FIRE[0] + 1.25, FIRE[1] - 0.9, 0), 40, 0.8)
    parts += stump
    axe = K.polyhaven("wooden_axe")
    K.place(axe, (2.8, -0.6, 0.05), 70, 1.0)
    parts += axe
    things = K.decimate(K.join(parts, "jungle_scans"), 220000)   # the campfire is low-poly: kept whole
    return K.join([things, campfire()], "jungle_props")


def plants():
    parts = []                       # trees come from the forest photo; ferns up close
    for x, y in [(-2.5, -4), (3.5, -5), (-5, 2), (4.5, 3), (-1.5, 3.5), (6, -6.5), (-6.5, -6)]:
        fern = K.polyhaven("fern_02", res="1k")
        K.place(fern, (x, y, 0), x * 40, 1.6)
        parts += fern
    return K.decimate(K.join(parts, "jungle_plants"), 60000)


def lighting():
    K.add_light("POINT", (FIRE[0], FIRE[1], 0.7), 380, (1.0, 0.48, 0.16), 0.35)   # the flames
    K.screen_light(SCREEN_W, SCREEN_D, SCREEN_Z, 3500)
    K.add_light("POINT", (0.95, -0.15, 0.75), 25, (1.0, 0.65, 0.3), 0.05)
    for s_ in (-1, 1):
        K.add_light("POINT", (s_ * (SCREEN_W / 2 + 0.25), -SCREEN_D + 0.12, SCREEN_Z - 0.3), 30, (1.0, 0.62, 0.3), 0.08)
    world = bpy.data.worlds.new("dusk")
    bpy.context.scene.world = world
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = bpy.data.images.load(str(SKY))
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.5
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])


def main():
    K.reset()
    lighting()
    floor = ground()
    things = props()
    green = plants()
    print("triangles:", sum(len(o.data.polygons) for o in (floor, things, green)))
    if "--preview" in K.ARGS:
        K.setup_cycles(int(K.arg("--samples", 64)))
        K.dim_screens()
        cam = bpy.data.cameras.new("cam")
        cam.lens = 16
        ob = bpy.data.objects.new("cam", cam)
        ob.location = (0.0, 0.0, 1.15)
        ob.rotation_euler = (math.radians(84), 0, math.radians(180 + float(K.arg("--yaw", 0))))
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        r.resolution_x, r.resolution_y = 1600, 900
        r.filepath = K.arg("--preview")
        bpy.ops.render.render(write_still=True)
        return
    size = int(K.arg("--bake", 4096))
    samples = int(K.arg("--samples", 384))
    K.bake_all([floor, things], size, samples)
    K.export([floor, things], "jungle")
    K.export([green], "jungle_plants")


main()
