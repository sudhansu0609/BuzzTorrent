"""What goes round the screen in the VR rooms: velvet masking, aluminium truss, PA speakers,
drapes and speaker drivers. All in Blender coordinates (viewer at the origin, screen towards -Y);
the video panel itself is drawn by the app at y = -distance, so everything here stays behind
that plane or outside the picture.
"""
import math

from mathutils import Vector

import bakekit as K


def mats():
    """Materials shared by the screen surrounds (created once per scene)."""
    return {
        "velvet": K.material("masking_velvet", (0.004, 0.004, 0.005), rough=0.9, sheen=0.6, noise=0.2, scale=160),
        "alu": K.material("truss_alu", (0.6, 0.61, 0.63), rough=0.32, metal=1.0, noise=0.08, scale=30),
        "black_metal": K.material("black_metal", (0.02, 0.02, 0.022), rough=0.4, metal=0.6),
        "grille": K.material("speaker_grille", (0.012, 0.012, 0.014), rough=0.85, noise=0.5, scale=400),
        "cabinet": K.material("speaker_cabinet", (0.018, 0.018, 0.02), rough=0.55, noise=0.1, scale=20),
        "cone": K.material("speaker_cone", (0.03, 0.03, 0.032), rough=0.6),
        "rim": K.material("speaker_rim", (0.35, 0.35, 0.37), rough=0.3, metal=0.9),
        "rubber": K.material("rubber_feet", (0.01, 0.01, 0.01), rough=0.9),
        "skirt": K.material("screen_skirt", (0.008, 0.008, 0.009), rough=0.95, sheen=0.3, noise=0.3, scale=60),
        "rope": K.material("guy_rope", (0.5, 0.45, 0.35), rough=0.9),
        "ballast": K.material("ballast", (0.12, 0.12, 0.12), rough=0.85, noise=0.3, scale=12),
        "screen": K.material("screen_surface", (0.07, 0.07, 0.075), rough=0.9),
    }


def beam(b, p, q, thick, mat, bevel=0.0):
    """A square beam from p to q; thick = (width, height)."""
    d = Vector(q) - Vector(p)
    mid = (Vector(p) + Vector(q)) / 2
    yaw = math.degrees(math.atan2(d.y, d.x))
    pitch = -math.degrees(math.atan2(d.z, math.hypot(d.x, d.y)))
    b.box((d.length, thick[0], thick[1]), tuple(mid), mat, rot=(0, pitch, yaw), bevel=bevel)


def truss(b, p, q, mat, size=0.3, chord=0.045, lace=0.022):
    """Box truss like a stage rig: four chords and zig-zag lacing on every face."""
    p, q = Vector(p), Vector(q)
    d = q - p
    n = d.normalized()
    u = n.cross(Vector((0, 0, 1)) if abs(n.z) < 0.9 else Vector((1, 0, 0))).normalized()
    v = n.cross(u).normalized()
    h = size / 2
    corners = [u * h + v * h, -u * h + v * h, -u * h - v * h, u * h - v * h]
    for c in corners:
        beam(b, p + c, q + c, (chord, chord), mat)
    steps = max(1, round(d.length / size))
    for i in range(steps):
        a = p + d * (i / steps)
        z = p + d * ((i + 1) / steps)
        for k in range(4):
            c0, c1 = corners[k], corners[(k + 1) % 4]
            if i % 2:
                beam(b, a + c0, z + c1, (lace, lace), mat)
            else:
                beam(b, a + c1, z + c0, (lace, lace), mat)
    for t in (0.0, 1.0):                                    # end plates
        c = p + d * t
        b.box((size + 0.06, size + 0.06, 0.02) if abs(n.z) > 0.9 else (0.02, size + 0.06, size + 0.06), tuple(c),
              mat, rot=(0, 0, 0) if abs(n.z) > 0.9 else (0, 0, math.degrees(math.atan2(d.y, d.x))))


def driver(b, m, x, y, z, r, facing=1.0):
    """A round speaker driver on a cabinet front facing +Y (towards the viewer)."""
    b.box((2 * r + 0.03, 0.02, 2 * r + 0.03), (x, y, z), m["rim"], bevel=r * 0.98 + 0.014, segs=6)
    b.box((2 * r, 0.03, 2 * r), (x, y + 0.012 * facing, z), m["cone"], bevel=r * 0.98, segs=6)
    b.box((r * 0.5, 0.04, r * 0.5), (x, y + 0.02 * facing, z), m["rim"], bevel=r * 0.24, segs=4)


def cabinet(b, m, x, y, z0, w, d, h, drivers):
    """Speaker cabinet standing at z0, front towards the viewer (+Y): grille cloth with the
    drivers [(height, radius)] showing through."""
    b.box((w, d, h), (x, y, z0 + h / 2), m["cabinet"], bevel=0.015)
    front = y + d / 2
    b.box((w - 0.03, 0.012, h - 0.03), (x, front + 0.004, z0 + h / 2), m["grille"])
    for dz, r in drivers:
        driver(b, m, x, front + 0.012, z0 + dz, r)


def pa_speaker(b, m, x, y, ground, yaw=0.0, height=1.9):
    """PA speaker on a tripod stand, angled towards the audience."""
    for k in range(3):
        a = math.radians(k * 120 + yaw)
        foot = (x + 0.55 * math.cos(a), y + 0.55 * math.sin(a), ground)
        beam(b, foot, (x, y, ground + 0.75), (0.03, 0.03), m["black_metal"])
        b.box((0.06, 0.06, 0.03), (foot[0], foot[1], ground + 0.015), m["rubber"])
    b.cyl(0.025, height - 0.4, (x, y, ground + (height - 0.4) / 2 + 0.2), m["black_metal"], segs=12)
    w, d, h = 0.42, 0.38, 0.68
    zc = ground + height
    b.box((w, d, h), (x, y, zc), m["cabinet"], rot=(0, 0, yaw), bevel=0.03)
    c, s = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    fx, fy = x - s * (d / 2 + 0.006), y + c * (d / 2 + 0.006)
    b.box((w - 0.04, 0.01, h - 0.04), (fx, fy, zc), m["grille"], rot=(0, 0, yaw))
    b.box((0.14, 0.04, 0.06), (x, y, zc + h / 2 + 0.03), m["black_metal"], rot=(0, 0, yaw), bevel=0.02)   # handle


def masking(b, m, w, h, y, cz, border, depth=0.08):
    """Black velvet masking round the picture, just behind the video panel's plane."""
    yb = y - depth / 2 - 0.03
    b.box((w + 2 * border, depth, border), (0, yb, cz + h / 2 + border / 2), m["velvet"], bevel=0.02)
    b.box((w + 2 * border, depth, border), (0, yb, cz - h / 2 - border / 2), m["velvet"], bevel=0.02)
    for s in (-1, 1):
        b.box((border, depth, h), (s * (w / 2 + border / 2), yb, cz), m["velvet"], bevel=0.02)
    b.box((w + 0.02, 0.02, h + 0.02), (0, y - 0.09, cz), m["screen"])          # the screen surface


def drape(b, mat, cx, y, cz, width, height, folds=7.0, depth=0.16):
    """A hanging velvet curtain with soft folds (folds = how many across its width)."""
    n = max(24, int(width * 14))
    b.grid(width, height, (cx, y, cz), mat, n, 4, wave=lambda x: depth * math.sin(x * folds * 2 * math.pi / width))


def outdoor_screen(b, m, w, distance, cz, ground, tower_extra=0.5, speakers=True, guys=True, foot=1.2):
    """A free-standing outdoor cinema screen: truss towers and header, velvet masking, a black
    skirt down to the ground, ballast, guy ropes and PA speakers either side."""
    h = w * 9 / 16
    y = -distance
    border = max(0.18, w * 0.025)
    masking(b, m, w, h, y, cz, border)
    back = y - 0.45
    b.box((w + 2 * border, 0.03, h + 2 * border), (0, back + 0.25, cz), m["skirt"])        # screen back
    bottom = cz - h / 2 - border
    b.box((w + 2 * border, 0.04, bottom - ground), (0, y - 0.12, (bottom + ground) / 2), m["skirt"])
    top = cz + h / 2 + border + tower_extra
    tx = w / 2 + border + 0.25
    for s in (-1, 1):
        truss(b, (s * tx, back, ground + 0.02), (s * tx, back, top), m["alu"], size=0.3)
        b.box((1.0, foot, 0.04), (s * tx, back - foot / 2 + 0.3, ground + 0.02), m["black_metal"])   # base plate
        for k in (-1, 1):
            b.box((0.4, 0.3, 0.3), (s * tx + k * 0.32, back - foot + 0.45, ground + 0.15), m["ballast"], bevel=0.03)
        beam(b, (s * tx, back - 0.1, ground + 0.06), (s * tx, back - foot + 0.1, ground + 0.06), (0.06, 0.06), m["alu"])
        beam(b, (s * tx, back - 0.1, ground + 1.6), (s * tx, back - foot + 0.1, ground + 0.06), (0.05, 0.05), m["alu"])
        if guys:
            for k in (-1, 1):
                stake = (s * tx + k * 2.2, back - 3.5, ground)
                beam(b, (s * tx, back, top - 0.2), stake, (0.012, 0.012), m["rope"])
                b.box((0.05, 0.05, 0.12), (stake[0], stake[1], ground + 0.05), m["black_metal"])
    truss(b, (-tx, back, top), (tx, back, top), m["alu"], size=0.3)
    for s in (-1, 1):                                     # arms holding the frame to the towers
        for z in (cz + h / 2, cz - h / 2):
            beam(b, (s * tx, back, z), (s * (w / 2 + border * 0.5), y - 0.08, z), (0.05, 0.05), m["alu"])
    if speakers:
        for s in (-1, 1):
            pa_speaker(b, m, s * (tx + 1.0), y + 0.6, ground, yaw=-s * 12)
    return top
