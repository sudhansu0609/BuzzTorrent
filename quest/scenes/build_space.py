"""The "Space" room: a 360° sky (Earth with clouds, city lights and atmosphere, the Moon, the
Milky Way) rendered in Cycles, plus an orbital auditorium around the viewer, light-baked to a GLB.

  blender -b -P quest/scenes/build_space.py -- --sky out.png [--size 8192]   the 360° sky (no deck)
  blender -b -P quest/scenes/build_space.py -- --preview out.png             camera view with the deck
  blender -b -P quest/scenes/build_space.py -- --bake 4096 --samples 256     auditorium GLB

Textures (public domain / CC BY): NASA Blue Marble and Black Marble, ESO/S. Brunier Milky Way.
Coordinates as in build_cinema.py: viewer at the origin, screen towards -Y.
"""
import math
import sys
from pathlib import Path

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402
import screens as S  # noqa: E402

TEX = Path(K.arg("--tex", str(K.HERE / "_downloads")))
SUN_DIR = Vector((-0.47, -0.88, 0.05)).normalized()      # direction the sunlight travels: side-on, half the Earth in night
EARTH_R, EARTH_AT = 400.0, Vector((0.86, -0.42, 0.03)).normalized() * 1100
MOON_R, MOON_AT = 70.0, Vector((-0.55, -0.62, 0.55)).normalized() * 2600


def image(name):
    return bpy.data.images.load(str(TEX / name))


def node(nt, kind, **inputs):
    n = nt.nodes.new(kind)
    for k, v in inputs.items():
        n.inputs[k].default_value = v
    return n


def sphere(name, radius, at, segs=192):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=segs, ring_count=segs // 2, radius=radius, location=at)
    ob = bpy.context.active_object
    ob.name = name
    bpy.ops.object.shade_smooth()
    return ob


def earth():
    ob = sphere("earth", EARTH_R, EARTH_AT)
    ob.rotation_euler = (0, 0, math.radians(200))           # India and the Indian Ocean towards the sun
    m = bpy.data.materials.new("earth")
    m.use_nodes = True
    nt = m.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    day = nt.nodes.new("ShaderNodeTexImage")
    day.image = image("bluemarble.jpg")
    nt.links.new(day.outputs["Color"], bsdf.inputs["Base Color"])
    bsdf.inputs["Roughness"].default_value = 0.8
    bsdf.inputs["Specular IOR Level"].default_value = 0.25
    # City lights only on the night side: strength from the angle between the surface and the sun
    night = nt.nodes.new("ShaderNodeTexImage")
    night.image = image("blackmarble.jpg")
    geo = nt.nodes.new("ShaderNodeNewGeometry")
    dot = node(nt, "ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    dot.inputs[1].default_value = SUN_DIR                       # facing away from the sun = night
    nt.links.new(geo.outputs["Normal"], dot.inputs[0])
    rng = node(nt, "ShaderNodeMapRange", **{"From Min": 0.0, "From Max": 0.25, "To Min": 0.0, "To Max": 4.0})
    nt.links.new(dot.outputs["Value"], rng.inputs["Value"])
    nt.links.new(night.outputs["Color"], bsdf.inputs["Emission Color"])
    nt.links.new(rng.outputs["Result"], bsdf.inputs["Emission Strength"])
    ob.data.materials.append(m)

    clouds = sphere("clouds", EARTH_R * 1.006, EARTH_AT)
    c = bpy.data.materials.new("clouds")
    c.use_nodes = True
    nt = c.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (1, 1, 1, 1)
    b.inputs["Roughness"].default_value = 1.0
    noise = node(nt, "ShaderNodeTexNoise", Scale=14.0, Detail=15.0, Roughness=0.66, Distortion=0.6)
    ramp = nt.nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.55
    ramp.color_ramp.elements[1].position = 0.78
    nt.links.new(noise.outputs["Fac"], ramp.inputs["Fac"])
    nt.links.new(ramp.outputs["Color"], b.inputs["Alpha"])
    clouds.data.materials.append(c)

    air = sphere("atmosphere", EARTH_R * 1.028, EARTH_AT, segs=96)
    a = bpy.data.materials.new("atmosphere")
    a.use_nodes = True
    nt = a.node_tree
    nt.nodes.remove(nt.nodes["Principled BSDF"])
    out = nt.nodes["Material Output"]
    lw = node(nt, "ShaderNodeLayerWeight", Blend=0.35)
    pw = node(nt, "ShaderNodeMath")
    pw.operation = "POWER"
    pw.inputs[1].default_value = 6.0
    nt.links.new(lw.outputs["Facing"], pw.inputs[0])
    em = node(nt, "ShaderNodeEmission", Color=(0.25, 0.5, 1.0, 1), Strength=2.2)
    tr = nt.nodes.new("ShaderNodeBsdfTransparent")
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(pw.outputs["Value"], mix.inputs["Fac"])
    nt.links.new(tr.outputs["BSDF"], mix.inputs[1])
    nt.links.new(em.outputs["Emission"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], out.inputs["Surface"])
    air.data.materials.append(a)


def moon():
    ob = sphere("moon", MOON_R, MOON_AT, segs=96)
    m = bpy.data.materials.new("moon")
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes["Principled BSDF"]
    b.inputs["Roughness"].default_value = 1.0
    vor = node(nt, "ShaderNodeTexVoronoi", Scale=9.0)
    noise = node(nt, "ShaderNodeTexNoise", Scale=6.0, Detail=10.0)
    mix = nt.nodes.new("ShaderNodeMix")
    mix.data_type = "RGBA"
    mix.inputs["A"].default_value = (0.42, 0.41, 0.40, 1)
    mix.inputs["B"].default_value = (0.25, 0.25, 0.25, 1)
    nt.links.new(noise.outputs["Fac"], mix.inputs["Factor"])
    nt.links.new(mix.outputs["Result"], b.inputs["Base Color"])
    bump = node(nt, "ShaderNodeBump", Strength=0.6)
    nt.links.new(vor.outputs["Distance"], bump.inputs["Height"])
    nt.links.new(bump.outputs["Normal"], b.inputs["Normal"])
    ob.data.materials.append(m)


def sun_and_stars():
    data = bpy.data.lights.new("sun", "SUN")
    data.energy = 4.5
    data.angle = math.radians(0.6)
    ob = bpy.data.objects.new("sun", data)
    ob.rotation_euler = SUN_DIR.to_track_quat("-Z", "Y").to_euler()
    bpy.context.scene.collection.objects.link(ob)
    world = bpy.data.worlds.new("space")
    bpy.context.scene.world = world
    nt = world.node_tree
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    env.image = image("eso0932a.jpg")
    bg = nt.nodes["Background"]
    bg.inputs["Strength"].default_value = 0.6
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])


SW, SD, SZ = 14.0, 14.0, 3.8          # screen width, distance, centre height (Rooms.kt: Space)
ROW, RISE, ROWS = 1.5, 0.42, range(-2, 4)   # row k: radius SD - k*ROW from the screen, floor -k*RISE
HALF = 7.5                            # half the width of each row (arc length, metres)


def row_r(k):
    return SD - k * ROW


def polar(r, a, z=0.0):
    """A point on a circle round the screen's foot (0, -SD), angle a from straight back at you."""
    return (r * math.sin(a), -SD + r * math.cos(a), z)


def recliner(b, m, x, y, z, yaw):
    """White leather recliner facing the screen (turned by yaw), on a plinth with a blue LED strip."""
    c, s = math.cos(yaw), math.sin(yaw)
    deg = math.degrees(yaw)
    for size, (dx, dy, dz), tilt, bevel, segs, mat in [
        ((0.70, 0.62, 0.20), (0, -0.05, 0.42), -3, 0.08, 3, "leather"),     # cushion
        ((0.66, 0.30, 0.12), (0, -0.42, 0.30), -70, 0.05, 2, "leather"),    # leg rest
        ((0.70, 0.22, 0.80), (0, 0.30, 0.86), -16, 0.09, 3, "leather"),     # backrest
        ((0.62, 0.16, 0.22), (0, 0.33, 1.22), -16, 0.07, 3, "leather"),     # headrest
        ((0.70, 0.66, 0.24), (0, 0.0, 0.12), 0, 0.04, 1, "plinth"),
        ((0.60, 0.02, 0.025), (0, -0.335, 0.05), 0, 0.0, 1, "led"),
    ]:
        b.box(size, (x + dx * c - dy * s, y + dx * s + dy * c, z + dz), m[mat], rot=(tilt, 0, deg), bevel=bevel, segs=segs)


def console(b, m, x, y, z, yaw):
    c, s = math.cos(yaw), math.sin(yaw)
    deg = math.degrees(yaw)
    for size, (dx, dy, dz), mat, bevel in [
        ((0.20, 0.78, 0.55), (0, 0.02, 0.28), "plinth", 0.04),
        ((0.24, 0.74, 0.08), (0, 0.0, 0.60), "leather", 0.035),
        ((0.12, 0.02, 0.02), (0, -0.39, 0.45), "led", 0.0),
    ]:
        b.box(size, (x + dx * c - dy * s, y + dx * s + dy * c, z + dz), m[mat], rot=(0, 0, deg), bevel=bevel)


def segment(b, p, q, thick, mat):
    """A beam from p to q."""
    d = Vector(q) - Vector(p)
    mid = (Vector(p) + Vector(q)) / 2
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = -math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    b.box((d.length + 0.02, thick[0], thick[1]), tuple(mid), mat, rot=(0, pitch, yaw))


def arc(b, r, end, z_top, z_bottom, depth, mat, step=math.radians(3), every=None):
    """A curved band round the screen's foot: tiers, the apron, the back wall."""
    n = int(2 * end / step) + 1
    out = []
    for i in range(n):
        a = -end + (i + 0.5) * 2 * end / n
        w = (r + depth / 2) * 2 * end / n * 1.04
        x, y, _ = polar(r, a)
        b.box((w, depth, z_top - z_bottom), (x, y, (z_top + z_bottom) / 2), mat, rot=(0, 0, -math.degrees(a)))
        out.append((a, w))
    return out


def deck():
    """Orbital auditorium: six curved, raked rows of recliners facing a screen that floats in
    space, glowing step edges, open sides (the Earth to your right, the Moon to the left),
    a panelled back wall and arched ribs overhead. You sit in the middle of the third row."""
    m = {
        "floor": K.material("aud_floor", (0.035, 0.037, 0.045), rough=0.7, noise=0.2, scale=8),
        "metal": K.material("aud_metal", (0.16, 0.165, 0.18), rough=0.3, metal=0.85, noise=0.12, scale=4),
        "dark": K.material("aud_dark", (0.02, 0.021, 0.025), rough=0.45, metal=0.5),
        "panel": K.material("aud_panel", (0.10, 0.105, 0.12), rough=0.5, metal=0.4, noise=0.1, scale=6),
        "leather": K.material("aud_leather", (0.62, 0.61, 0.6), rough=0.45, noise=0.08, scale=60),
        "plinth": K.material("aud_plinth", (0.025, 0.025, 0.03), rough=0.4, metal=0.3),
        "led": K.material("aud_led", (0.3, 0.6, 1.0), emit=(0.25, 0.55, 1.0), emit_strength=10),
        "led_soft": K.material("aud_led_soft", (0.5, 0.7, 1.0), emit=(0.55, 0.75, 1.0), emit_strength=4),
    }
    b, chairs = K.Builder("space_deck"), K.Builder("space_seats")
    base = -2.6
    rows = list(ROWS)
    for k in rows:
        r, z = row_r(k), -k * RISE
        end = (HALF + 0.9) / r
        for a, w in arc(b, r, end, z, base, ROW, m["floor"]):
            if k != rows[-1]:                   # glowing nosing on the step down to the next row
                x, y, _ = polar(r - ROW / 2 - 0.01, a)
                b.box((w, 0.03, 0.03), (x, y, z - 0.05), m["led"], rot=(0, 0, -math.degrees(a)))
                x, y, _ = polar(r - ROW / 2 + 0.03, a)
                b.box((w, 0.07, 0.025), (x, y, z + 0.005), m["metal"], rot=(0, 0, -math.degrees(a)))
        seat = 0.95
        count = int(HALF / seat)
        for i in range(-count, count + 1):
            a = i * seat / r
            x, y, _ = polar(r, a)
            recliner(chairs, m, x, y, z, -a)
            if i < count:
                a = (i + 0.5) * seat / r
                x, y, _ = polar(r, a)
                console(chairs, m, x, y, z, -a)
        for side in (-1, 1):                    # side rail at each row's end: panel, rail, light
            a = side * end
            x, y, _ = polar(r, a)
            b.box((0.05, ROW, 0.95), (x, y, z + 0.475), m["metal"], rot=(0, 0, -math.degrees(a)))
            b.box((0.09, ROW + 0.02, 0.05), (x, y, z + 0.97), m["metal"], rot=(0, 0, -math.degrees(a)), bevel=0.02)
            b.box((0.03, ROW, 0.02), (x, y, z + 0.94), m["led_soft"], rot=(0, 0, -math.degrees(a)))
    # Front apron, a step below the front row, ending at a glowing rail with space beyond
    k = rows[-1]
    z_front = -k * RISE - 0.25
    r_in, r_out = 7.0, row_r(k) - ROW / 2
    end = (HALF + 0.9) / r_out
    for i, (a, w) in enumerate(arc(b, (r_in + r_out) / 2, end, z_front, base, r_out - r_in, m["metal"])):
        x, y, _ = polar(r_out - 0.01, a)
        b.box((w, 0.03, 0.03), (x, y, -k * RISE - 0.05), m["led"], rot=(0, 0, -math.degrees(a)))
        x, y, _ = polar(r_in - 0.02, a)
        w = r_in * 2 * end / max(1, int(2 * end / math.radians(3)) + 1) * 1.04
        b.box((w, 0.04, 0.04), (x, y, z_front - 0.15), m["led"], rot=(0, 0, -math.degrees(a)))       # under-rim
        b.box((w, 0.06, 0.05), (x, y, z_front + 0.95), m["metal"], rot=(0, 0, -math.degrees(a)), bevel=0.02)
        b.box((w, 0.02, 0.02), (x, y, z_front + 0.92), m["led_soft"], rot=(0, 0, -math.degrees(a)))
        if i % 3 == 0:
            b.box((0.04, 0.04, 0.95), (x, y, z_front + 0.475), m["metal"])
    # Back wall behind the top row: dark panels with light fins
    k = rows[0]
    r_back, z_back = row_r(k) + ROW / 2 + 0.15, -k * RISE
    for i, (a, w) in enumerate(arc(b, r_back, (HALF + 1.2) / r_back, z_back + 4.2, base, 0.3, m["panel"])):
        if i % 4 == 2:
            x, y, _ = polar(r_back - 0.17, a)
            b.box((0.05, 0.04, 3.6), (x, y, z_back + 2.0), m["led_soft"], rot=(0, 0, -math.degrees(a)))
    # Ribs arching over the seats from one side rail to the other, lit underneath
    for r in RIBS:
        end = (HALF + 1.0) / r
        floor_z = -(SD - r) / ROW * RISE
        pts = [polar(r, -end + 2 * end * j / 24, floor_z + 0.9 + 6.2 * math.sin(math.pi * j / 24)) for j in range(25)]
        for p, q in zip(pts, pts[1:]):
            segment(b, p, q, (0.22, 0.30), m["dark"])
            segment(b, (p[0], p[1], p[2] - 0.16), (q[0], q[1], q[2] - 0.16), (0.05, 0.02), m["led_soft"])
    screen_frame(b, m)
    # A spine joining the ribs' crowns
    crowns = [polar(r, 0, -(SD - r) / ROW * RISE + 7.1) for r in RIBS]
    for p, q in zip(crowns, crowns[1:]):
        segment(b, p, q, (0.3, 0.3), m["dark"])
    return [b.build(), chairs.build()]


def screen_frame(b, m):
    """The screen floating beyond the apron: velvet masking in a dark metal frame with a glowing
    edge, a solid back, and a pylon with two struts dropping away into the void."""
    sm = S.mats()
    sh = SW * 9 / 16
    border = 0.35
    S.masking(b, sm, SW, sh, -SD, SZ, border)
    y = -SD - 0.32
    b.box((SW + 2 * border + 0.4, 0.4, sh + 2 * border + 0.4), (0, y, SZ), m["dark"], bevel=0.08)
    ow, oh = SW / 2 + border + 0.2, sh / 2 + border + 0.2
    # The glowing edge stands 16 cm off the frame (4 cm off, it flashed against it at 14 m)
    for z in (SZ + oh, SZ - oh):
        b.box((2 * ow, 0.16, 0.04), (0, -SD - 0.04, z), m["led"])
    for s in (-1, 1):
        b.box((0.04, 0.16, 2 * oh), (s * ow, -SD - 0.04, SZ), m["led"])
    bottom = SZ - oh
    S.beam(b, (0, y, bottom), (0, y, bottom - 9), (0.7, 0.7), m["metal"])
    for k in range(1, 6):
        b.box((0.8, 0.8, 0.05), (0, y, bottom - 1.5 * k), m["led_soft"])
    for s in (-1, 1):
        S.beam(b, (s * (SW / 2 - 0.5), y, bottom), (0, y, bottom - 4.5), (0.3, 0.3), m["metal"])


RIBS = (9.0, 12.5, 16.0)


def lighting():
    """Cool light from under the ribs and a warm wash from the back wall, besides the LEDs."""
    for r in RIBS:
        z = -(SD - r) / ROW * RISE + 6.6
        K.add_light("AREA", polar(r, 0, z), 600, (0.75, 0.85, 1.0), (10.0, 0.6))
    K.add_light("AREA", polar(row_r(-2) + 0.5, 0, 3.5), 500, (1.0, 0.8, 0.6), (12.0, 0.5), (60, 0, 0))


def main():
    K.reset()
    sun_and_stars()
    earth()
    moon()
    if "--sky" in K.ARGS:                       # the 360° sky without the deck
        K.setup_cycles(int(K.arg("--samples", 96)))
        cam = bpy.data.cameras.new("pano")
        cam.type = "PANO"
        cam.panorama_type = "EQUIRECTANGULAR"
        ob = bpy.data.objects.new("pano", cam)
        ob.location = (0, 0, 1.2)
        ob.rotation_euler = (math.radians(90), 0, math.radians(180))   # image centre = towards the screen
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        size = int(K.arg("--size", 8192))
        r.resolution_x, r.resolution_y = size, size // 2
        r.filepath = K.arg("--sky")
        bpy.ops.render.render(write_still=True)
        return
    floor = deck()
    lighting()
    K.screen_light(SW, SD, SZ, 9000)
    if "--preview" in K.ARGS:
        K.setup_cycles(int(K.arg("--samples", 64)))
        K.dim_screens()
        cam = bpy.data.cameras.new("cam")
        cam.lens = 14
        ob = bpy.data.objects.new("cam", cam)
        ob.location = (0.0, 0.05, 1.2)
        ob.rotation_euler = (math.radians(84), 0, math.radians(180 + float(K.arg("--yaw", 0))))
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        r.resolution_x, r.resolution_y = 1600, 900
        r.filepath = K.arg("--preview")
        bpy.ops.render.render(write_still=True)
        return
    K.bake_all(floor, int(K.arg("--bake", 4096)), int(K.arg("--samples", 320)))
    K.export(floor, "space_deck")


main()
