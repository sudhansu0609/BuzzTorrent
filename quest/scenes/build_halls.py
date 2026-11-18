"""Three luxury cinema halls for BuzzTorrent VR, modelled in code, light-baked in Cycles and
exported as GLBs (one texture per part, 4K each, so they stay sharp up close).

  blender -b -P quest/scenes/build_halls.py -- --hall grand  --preview out.png
  blender -b -P quest/scenes/build_halls.py -- --hall palace --bake 4096 --samples 384

  grand   Grand IMAX: 32 m wide, 20 m screen, leather recliners on steep stadium rows,
          acoustic panels with LED lines, fibre-optic star ceiling.
  imax    IMAX Laser: a giant-screen auditorium, 44 m wide and 40 m long, 23 steep rows, a
          28 m x 19.6 m screen in the tall 1.43:1 IMAX shape set into a black acoustic front
          wall (speakers hidden behind it, as in a real IMAX). Films (16:9 or wider) fill its
          width, standing on its bottom edge (Rooms.kt ScreenSpot.grounded).
  palace  Royal Palace: 1920s picture palace, gilded proscenium arch, red velvet, balcony boxes
          with gold rails, columns, wall lights and a crystal chandelier.
  lounge  Private Lounge: VIP screening room, plush sofas on two levels, walnut panelling,
          side tables with lamps, patterned carpet.

Viewer's seat at the origin, floor of the viewer's row at z = 0, screen towards -Y.
The SPOTS below must match Rooms.kt (width, distance, centre height of the screen).
"""
import math
import sys
from pathlib import Path

import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bakekit as K  # noqa: E402
import screens as S  # noqa: E402

# Grand and Palace screens sit low over their stages (2026-10-17: they were 2.1 m and 0.8 m higher,
# a bare black wall under them and their middles 9-11 degrees above a seated eye). Grand's stage
# is low (40 cm) so its screen comes down near eye level, as on a home-cinema wall.
SPOTS = {"grand": (20.0, 18.0, 2.5), "imax": (28.0, 17.0, 5.4), "palace": (13.0, 15.0, 2.8),
         "lounge": (5.6, 6.2, 1.75)}
HALL = K.arg("--hall", "grand")
SW, SD, SZ = SPOTS[HALL]
SH = SW * 9 / 16                                    # the picture (16:9), lit by the screen light
SCREEN_H = SW / 1.43 if HALL == "imax" else SH      # the screen itself, masked round its edge


# ------------------------------------------------------------------ materials
def M():
    m = {}
    m["leather_black"] = K.material("leather_black", (0.025, 0.022, 0.022), rough=0.42, noise=0.12, scale=90)
    m["leather_tan"] = K.material("leather_tan", (0.32, 0.15, 0.06), rough=0.45, noise=0.12, scale=90)
    m["velvet_red"] = K.material("velvet_red", (0.32, 0.012, 0.025), rough=0.85, sheen=0.9, noise=0.25, scale=140)
    m["velvet_blue"] = K.material("velvet_blue", (0.008, 0.02, 0.075), rough=0.8, sheen=0.35, noise=0.25, scale=140)
    m["fabric_grey"] = K.material("fabric_grey", (0.11, 0.11, 0.12), rough=0.9, sheen=0.4, noise=0.2, scale=110)
    m["carpet_dark"] = K.material("carpet_dark", (0.035, 0.03, 0.045), rough=0.97, noise=0.4, scale=70)
    m["carpet_red"] = K.material("carpet_red", (0.2, 0.02, 0.03), rough=0.97, noise=0.5, scale=18)
    m["carpet_pattern"] = K.material("carpet_pattern", (0.14, 0.05, 0.03), rough=0.97, noise=0.6, scale=9)
    m["wall_acoustic"] = K.material("wall_acoustic", (0.03, 0.03, 0.04), rough=0.95, noise=0.15, scale=35)
    m["wall_damask"] = K.material("wall_damask", (0.22, 0.03, 0.04), rough=0.8, noise=0.45, scale=14)
    m["walnut"] = K.material("walnut", (0.12, 0.055, 0.025), rough=0.45, noise=0.45, scale=5)
    m["gold"] = K.material("gold", (0.83, 0.6, 0.26), rough=0.33, metal=1.0, noise=0.15, scale=30)
    m["marble"] = K.material("marble", (0.78, 0.74, 0.68), rough=0.18, noise=0.25, scale=3)
    m["black"] = K.material("matte_black", (0.006, 0.006, 0.007), rough=0.95)
    m["screen"] = K.material("screen", (0.07, 0.07, 0.075), rough=0.9)
    m["ceiling"] = K.material("ceiling_dark", (0.012, 0.012, 0.018), rough=0.95)
    m["ceiling_cream"] = K.material("ceiling_cream", (0.55, 0.45, 0.32), rough=0.7, noise=0.2, scale=6)
    m["ceiling_plum"] = K.material("ceiling_plum", (0.018, 0.01, 0.014), rough=0.9, noise=0.15, scale=6)
    m["led_blue"] = K.material("led_blue", (0.3, 0.6, 1), emit=(0.2, 0.5, 1.0), emit_strength=10)
    m["led_warm"] = K.material("led_warm", (1, 0.7, 0.4), emit=(1, 0.62, 0.32), emit_strength=8)
    m["step"] = K.material("step_light", (1, 0.7, 0.4), emit=(1, 0.6, 0.3), emit_strength=6)
    m["lamp"] = K.material("lamp_shade", (1, 0.85, 0.6), emit=(1, 0.75, 0.45), emit_strength=6)
    m["crystal"] = K.material("crystal", (1, 0.95, 0.85), emit=(1, 0.9, 0.7), emit_strength=14)
    m["star"] = K.material("star", (1, 1, 1), emit=(0.85, 0.9, 1.0), emit_strength=25)
    m["stage_top"] = K.material("stage_top", (0.01, 0.01, 0.012), rough=0.15, metal=0.2)
    m["velvet_plum"] = K.material("velvet_plum", (0.09, 0.012, 0.045), rough=0.85, sheen=0.8, noise=0.25, scale=140)
    m["exit"] = K.material("exit", (0.1, 1, 0.3), emit=(0.1, 1, 0.35), emit_strength=8)
    m["steel"] = K.material("brushed_steel", (0.5, 0.5, 0.52), rough=0.3, metal=1.0)
    m["glass"] = K.material("drink", (0.5, 0.15, 0.05), rough=0.05)
    return m


# ---------------------------------------------------------------------- seats
def recliner(b, m, x, y, z, cover="leather_black", near=True):
    """Luxury power recliner, facing -Y, base on the floor at z. Far seats (near=False) get
    plain chamfers instead of rounded bevels: the IMAX hall has 759 of them, and the Quest runs
    out of memory drawing them all rounded."""
    c = m[cover]
    s3, s2 = (3, 2) if near else (1, 1)
    b.box((0.70, 0.62, 0.20), (x, y - 0.05, z + 0.42), c, rot=(-3, 0, 0), bevel=0.08, segs=s3)     # cushion
    b.box((0.66, 0.30, 0.12), (x, y - 0.42, z + 0.30), c, rot=(-70, 0, 0), bevel=0.05, segs=s2)    # leg rest
    b.box((0.70, 0.22, 0.80), (x, y + 0.30, z + 0.86), c, rot=(-16, 0, 0), bevel=0.09, segs=s3)    # backrest
    b.box((0.62, 0.16, 0.22), (x, y + 0.33, z + 1.22), c, rot=(-16, 0, 0), bevel=0.07, segs=s3)    # headrest
    b.box((0.70, 0.66, 0.24), (x, y, z + 0.12), m["black"], bevel=0.04, segs=s2)                    # plinth


def console(b, m, x, y, z, cover="leather_black", near=True):
    """Armrest console between recliners: padded top, cup holder, glowing base strip."""
    s2 = 2 if near else 1
    b.box((0.20, 0.78, 0.55), (x, y + 0.02, z + 0.28), m["black"], bevel=0.04, segs=s2)
    b.box((0.24, 0.74, 0.08), (x, y + 0.0, z + 0.60), m[cover], bevel=0.035, segs=3 if near else 1)
    b.cyl(0.05, 0.03, (x, y - 0.26, z + 0.645), m["steel"], segs=16 if near else 8)
    b.box((0.18, 0.02, 0.02), (x, y - 0.38, z + 0.06), m["step"])


def velvet_seat(b, m, x, y, z):
    """Classic theatre seat with gold-capped arms."""
    b.box((0.50, 0.50, 0.13), (x, y - 0.03, z + 0.45), m["velvet_red"], rot=(-4, 0, 0), bevel=0.05)
    b.box((0.52, 0.11, 0.66), (x, y + 0.27, z + 0.88), m["velvet_red"], rot=(-14, 0, 0), bevel=0.05)
    b.box((0.52, 0.05, 0.70), (x, y + 0.33, z + 0.86), m["walnut"], rot=(-14, 0, 0), bevel=0.02)


def velvet_arm(b, m, x, y, z):
    b.box((0.06, 0.52, 0.62), (x, y + 0.02, z + 0.31), m["walnut"], bevel=0.02)
    b.box((0.09, 0.52, 0.05), (x, y - 0.0, z + 0.64), m["walnut"], bevel=0.02)
    b.cyl(0.035, 0.03, (x, y - 0.26, z + 0.66), m["gold"], segs=12)


def sofa(b, m, x, y, z, width, cover="velvet_blue"):
    """Plush deep sofa (two or three seats) facing -Y."""
    c = m[cover]
    b.box((width, 0.85, 0.24), (x, y, z + 0.32), c, bevel=0.1, segs=3)
    n = max(1, round(width / 0.8))
    for i in range(n):
        cx = x - width / 2 + (i + 0.5) * width / n
        b.box((width / n - 0.04, 0.70, 0.14), (cx, y - 0.05, z + 0.50), c, bevel=0.07, segs=3)     # cushions
        b.box((width / n - 0.06, 0.22, 0.52), (cx, y + 0.34, z + 0.78), c, rot=(-12, 0, 0), bevel=0.1, segs=3)
    for s in (-1, 1):
        b.box((0.22, 0.9, 0.62), (x + s * (width / 2 + 0.11), y, z + 0.38), c, bevel=0.1, segs=3)
    b.box((width + 0.4, 0.9, 0.1), (x, y, z + 0.05), m["walnut"], bevel=0.02)


# ------------------------------------------------------------------ screen ends
# The Quest's depth buffer can't tell apart two surfaces a few centimetres apart 15 m or more
# away: whichever wins changes from frame to frame and the far one flashes through (an LED line
# 3 cm proud of the stage, a plate 8 mm over the stage top, a second screen surface 2 cm behind
# the first). So at the screen end, trim is set flush into the surface it lights (stacked
# bands with one shared front face) and anything in front of another surface stands well clear.
def stack(b, w, y0, y1, x, bands):
    """A block from y0 (back) to y1 (front), its front face one flat plane: bands of
    [(z0, z1, material)] stacked bottom to top, e.g. a black front with a flush LED line."""
    for z0, z1, mat in bands:
        b.box((w, y1 - y0, z1 - z0), (x, (y0 + y1) / 2, (z0 + z1) / 2), mat)


def grand_screen(m, front_y, front_z, half, ceil, height=1.0):
    """Premium screen end: velvet masking, a black stage with a glowing nose and lit steps,
    navy velvet drapes and a pleated valance (the speakers are behind the screen, as in a real
    cinema)."""
    sm = S.mats()
    b = K.Builder("grand_stage")
    S.masking(b, sm, SW, SCREEN_H, -SD, SZ, 0.55)
    depth = 2.6
    top = front_z + height
    w = 2 * half - 0.6
    # Black front with a blue line along the floor and a warm one under the lip, flush
    stack(b, w, front_y, front_y + depth, 0, [
        (front_z, front_z + 0.085, m["black"]), (front_z + 0.085, front_z + 0.115, m["led_blue"]),
        (front_z + 0.115, top - 0.07, m["black"]), (top - 0.07, top - 0.05, m["led_warm"]),
        (top - 0.05, top - 0.04, m["black"])])
    b.box((w, depth + 0.04, 0.04), (0, front_y + depth / 2 + 0.02, top - 0.02), m["stage_top"], bevel=0.01)
    for s in (-1, 1):                                       # steps up at both ends, lit noses
        for i in range(3):
            h = height - height / 4 * (i + 1)
            y = front_y + depth + 0.35 * i
            x = s * (half - 1.4)
            z = front_z + h
            stack(b, 1.6, y, y + 0.35, x, [(front_z, z - 0.04, m["black"]), (z - 0.02, z, m["black"])])
            stack(b, 0.1, y, y + 0.35, x - 0.75, [(z - 0.04, z - 0.02, m["black"])])
            stack(b, 0.1, y, y + 0.35, x + 0.75, [(z - 0.04, z - 0.02, m["black"])])
            stack(b, 1.4, y, y + 0.35, x, [(z - 0.04, z - 0.02, m["step"])])
    curtain_w = half - 0.15 - (SW / 2 + 0.55 + 0.25)
    for s in (-1, 1):
        S.drape(b, m["velvet_blue"], s * (half - 0.15 - curtain_w / 2), -SD + 0.35, (ceil + top) / 2,
                curtain_w, ceil - top, folds=9, depth=0.2)
    # The valance hangs clear in front of the drapes' folds (it used to cut through them)
    S.drape(b, m["velvet_blue"], 0, -SD + 0.8, ceil - 0.75, 2 * half - 0.4, 1.5, folds=46, depth=0.08)
    lights = []
    for s in (-1, 1):
        lights.append(("AREA", (s * (half - 0.15 - curtain_w / 2), -SD + 1.8, ceil - 0.6), 3500, (0.6, 0.7, 1.0),
                       (curtain_w, 0.4), (-15, 0, 0)))
    lights.append(("AREA", (0, front_y + depth + 0.6, front_z + 0.05), 500, (1.0, 0.65, 0.4), (2 * half - 4, 0.2), (180, 0, 0)))
    return b.build(), lights


def lounge_screen(m, front_y, half, ceil, floor_z):
    """Private-cinema media wall: walnut slats either side of a wall-mounted screen in velvet
    masking, a low credenza with a centre speaker, tower speakers and plum drapes."""
    sm = S.mats()
    b = K.Builder("lounge_screenwall")
    border = 0.14
    S.masking(b, sm, SW, SH, -SD, SZ, border)
    box_d = -SD - 0.12 - front_y
    b.box((SW + 2 * border, box_d, SH + 2 * border), (0, front_y + box_d / 2, SZ), m["black"])
    x = SW / 2 + border + 0.12
    while x < half - 0.1:                                   # walnut slats on black felt
        for s in (-1, 1):
            b.box((0.05, 0.04, ceil - floor_z), (s * x, front_y + 0.02, (ceil + floor_z) / 2), m["walnut"])
        x += 0.11
    for z in (floor_z + 0.02, ceil - 0.02):                 # top and bottom rails
        b.box((2 * half, 0.06, 0.04), (0, front_y + 0.04, z), m["walnut"])
    # Credenza: four doors with brass pulls, warm light underneath
    cy, cw, ch = -SD + 0.3, 4.6, 0.5
    b.box((cw, 0.5, ch), (0, cy, floor_z + 0.1 + ch / 2), m["walnut"], bevel=0.02)
    for i in range(4):
        dx = -cw / 2 + (i + 0.5) * cw / 4
        b.box((cw / 4 - 0.03, 0.01, ch - 0.06), (dx, cy + 0.255, floor_z + 0.1 + ch / 2), m["walnut"], bevel=0.005)
        b.box((0.12, 0.02, 0.015), (dx, cy + 0.27, floor_z + 0.1 + ch - 0.08), m["gold"], bevel=0.005)
    for dx in (-cw / 2 + 0.15, cw / 2 - 0.15):
        b.box((0.05, 0.4, 0.1), (dx, cy, floor_z + 0.05), m["black"])
    b.box((cw - 0.4, 0.02, 0.02), (0, cy - 0.15, floor_z + 0.08), m["led_warm"])
    S.cabinet(b, sm, 0, cy + 0.05, floor_z + 0.1 + ch, 0.9, 0.3, 0.2, [(0.1, 0.07)])
    # Tower speakers with walnut cheeks
    for s in (-1, 1):
        tx = s * (SW / 2 + border + 0.55)
        S.cabinet(b, sm, tx, -SD + 0.1, floor_z + 0.05, 0.3, 0.38, 1.15, [(1.0, 0.035), (0.8, 0.07), (0.55, 0.08), (0.28, 0.08)])
        for k in (-1, 1):
            b.box((0.02, 0.4, 1.2), (tx + k * 0.16, -SD + 0.1, floor_z + 0.6), m["walnut"], bevel=0.005)
        S.drape(b, m["velvet_plum"], s * (half - 0.5), front_y + 0.35, (ceil + floor_z) / 2, 0.9, ceil - floor_z, folds=4, depth=0.1)
    lights = [("AREA", (s * (half + SW / 2 + border) / 2, front_y + 0.25, floor_z + 0.05), 70, (1, 0.7, 0.45),
               (half - SW / 2 - border - 0.2, 0.1), (180, 0, 0)) for s in (-1, 1)]
    return b.build(), lights


def palace_screen(m, front_y, front_z):
    """Velvet masking and footlights along the stage edge."""
    sm = S.mats()
    b = K.Builder("palace_stage")
    S.masking(b, sm, SW, SH, -SD, SZ, 0.3)
    n = 26
    for i in range(n):
        x = -(SW + 2.6) / 2 + (i + 0.5) * (SW + 2.6) / n
        b.box((0.16, 0.12, 0.08), (x, front_y + 1.92, front_z + 1.15), m["gold"], bevel=0.03)
        b.box((0.08, 0.06, 0.06), (x, front_y + 1.86, front_z + 1.2), m["lamp"], bevel=0.025)
    return b.build(), [("AREA", (0, front_y + 1.9, front_z + 1.25), 300, (1, 0.75, 0.45), (SW + 2, 0.1), (-150, 0, 0))]


# ---------------------------------------------------------------------- halls
def screen_wall(b, m, front_y, floor_front, width, ceil):
    """The black wall behind the screen. The screen surface itself is S.masking's: a second one
    2 cm behind it (and a black board 2 cm behind that) flashed through it from 15 m on."""
    b.box((width + 0.4, 0.2, ceil - floor_front), (0, front_y - 0.1, (ceil + floor_front) / 2), m["black"])


def imax_screen(m, front_z, half, ceil):
    """IMAX Laser screen end: the screen set into a black acoustic front wall that runs wall to
    wall and floor to ceiling, fabric panels with slim light lines either side, a low ledge with
    a warm floor wash along the bottom. No stage, no visible speakers (they are behind the
    perforated screen)."""
    sm = S.mats()
    b = K.Builder("imax_front")
    border = 0.3
    S.masking(b, sm, SW, SCREEN_H, -SD, SZ, border)
    # Front face of the wall: well behind the screen surface (it was 4 cm behind and flashed
    # through round the picture)
    wall_y = -SD - 0.3
    b.box((2 * half, 0.2, ceil - front_z), (0, wall_y - 0.1, (ceil + front_z) / 2), m["wall_acoustic"])
    edge = SW / 2 + border + 0.5
    n = max(1, round((half - 0.4 - edge) / 2.4))
    w = (half - 0.4 - edge) / n
    z0, z1 = front_z + 0.9, ceil - 0.6
    for s in (-1, 1):                                       # fabric panels and light lines either side
        for i in range(n):
            x = s * (edge + (i + 0.5) * w)
            b.box((w - 0.12, 0.12, z1 - z0), (x, wall_y + 0.06, (z0 + z1) / 2), m["fabric_grey"], bevel=0.04)
        for i in range(n + 1):                          # slim fins standing 14 cm off the wall
            b.box((0.04, 0.14, z1 - z0), (s * (edge + i * w), wall_y + 0.07, (z0 + z1) / 2), m["led_blue"])
    b.box((2 * half - 0.8, 0.14, 0.03), (0, wall_y + 0.07, ceil - 0.3), m["led_blue"])        # line under the ceiling
    # Low ledge along the screen line: a flush warm line along its foot, a thick top
    lw = 2 * half - 0.6
    stack(b, lw, wall_y, wall_y + 0.7, 0, [(front_z, front_z + 0.05, m["black"]), (front_z + 0.07, front_z + 0.377, m["black"])])
    for s in (-1, 1):
        stack(b, 0.1, wall_y, wall_y + 0.7, s * (lw / 2 - 0.05), [(front_z + 0.05, front_z + 0.07, m["black"])])
    stack(b, lw - 0.2, wall_y, wall_y + 0.7, 0, [(front_z + 0.05, front_z + 0.07, m["led_warm"])])
    b.box((lw, 0.74, 0.1), (0, wall_y + 0.37, front_z + 0.427), m["stage_top"], bevel=0.008)
    lights = []
    for s in (-1, 1):
        lights.append(("AREA", (s * (edge + (half - edge) / 2), -SD + 1.4, ceil - 0.8), 2600, (0.55, 0.65, 1.0),
                       (half - edge - 0.5, 0.4), (-20, 0, 0)))
    lights.append(("AREA", (0, wall_y + 1.1, front_z + 0.05), 450, (1.0, 0.65, 0.4), (2 * half - 4, 0.2), (180, 0, 0)))
    return b.build(), lights


def surround_speakers(b, sm, half, front_y, back_y, row, rise, ceil):
    """Cinema surround speakers high on the side walls, angled down to the seats."""
    y = front_y + 5.0
    while y < back_y - 2.0:
        floor_z = rise * y / row                            # the stadium floor under this spot
        z = min(floor_z + 4.6, ceil - 1.2)
        for s in (-1, 1):
            x = s * (half - 0.09 - 0.2)
            b.box((0.4, 0.46, 0.68), (x, y, z), sm["cabinet"], rot=(0, s * 12, 0), bevel=0.02)
            b.box((0.02, 0.42, 0.62), (x - s * 0.205, y, z), sm["grille"], rot=(0, s * 12, 0))
            b.box((0.12, 0.06, 0.3), (s * (half - 0.09 - 0.04), y, z + 0.1), sm["black_metal"])
        y += 4.2


def grand():
    m = M()
    imax = HALL == "imax"
    if imax:            # giant screen: wider, taller, steeper; the stage is lower so the screen meets it
        ROW, RISE, half, rows, ceil, stage_h, side = 1.5, 0.6, 22.0, range(-14, 9), 19.0, 0.6, 11
    else:
        ROW, RISE, half, rows, ceil, stage_h, side = 1.65, 0.48, 16.0, range(-4, 9), 12.5, 0.4, 6
    front_z = -RISE * (max(rows) + 1)
    back_y, front_y = -min(rows) * ROW + 0.9, -SD - 1.2
    shell, floor, seats = K.Builder("grand_shell"), K.Builder("grand_floor"), K.Builder("grand_seats")
    for k in rows:                                              # stadium rows of recliners
        y, z = -k * ROW, -RISE * k
        floor.box((2 * half, ROW, 0.6), (0, y, z - 0.3), m["carpet_dark"])
        for x in (-6.0, 6.0):
            floor.box((1.1, 0.02, 0.05), (x, y - ROW / 2 - 0.011, z - 0.2), m["step"])
        xs = [-5.0 + 1.0 * i for i in range(11)] + [7.2 + i for i in range(side)] + [-7.2 - i for i in range(side)]
        near = not imax or abs(k) <= 3                      # IMAX: rounded seats only round yours
        for x in xs:
            recliner(seats, m, x, y, z, near=near)
        for x in sorted(xs):
            console(seats, m, x - 0.5, y, z, near=near)
        for edge in (5.5, 6.7 + side, -6.7):                # the outer arm of each block
            console(seats, m, edge, y, z, near=near)
    front_y0 = -(max(rows) + 0.5) * ROW
    floor.box((2 * half, front_y0 - front_y, 0.6), (0, (front_y0 + front_y) / 2, front_z - 0.3), m["carpet_dark"])
    floor.box((2 * half, 0.5, 4.0), (0, back_y - 0.8, -RISE * min(rows) + 1.2), m["wall_acoustic"])
    for s in (-1, 1):                                           # walls: panels with LED lines
        x = s * half
        shell.box((0.3, back_y - front_y, ceil - front_z), (x + s * 0.15, (back_y + front_y) / 2, (ceil + front_z) / 2), m["wall_acoustic"])
        y = back_y - 1.0
        while y > front_y + 2:
            shell.box((0.08, 3.2, ceil - front_z - 3), (x - s * 0.05, y - 1.7, (ceil + front_z) / 2 + 0.5), m["fabric_grey"], bevel=0.05)
            shell.box((0.05, 0.05, ceil - front_z - 3), (x - s * 0.06, y + 0.0, (ceil + front_z) / 2 + 0.5), m["led_blue"])
            y -= 3.6
        shell.box((0.06, back_y - front_y, 0.05), (x - s * 0.12, (back_y + front_y) / 2, 0.9), m["led_warm"])
    shell.box((2 * half + 0.6, 0.3, ceil - front_z), (0, back_y + 0.15, (ceil + front_z) / 2), m["wall_acoustic"])
    shell.box((2.2, 0.06, 0.6), (0, back_y - 0.02, -RISE * min(rows) + 3.6), m["exit"])
    screen_wall(shell, m, front_y, front_z, 2 * half, ceil)
    ceiling = K.Builder("grand_ceiling")
    ceiling.box((2 * half + 0.6, back_y - front_y + 0.6, 0.3), (0, (back_y + front_y) / 2, ceil + 0.15), m["ceiling"])
    import random
    rnd = random.Random(7)
    for _ in range(1800 if imax else 900):                      # fibre-optic star ceiling
        ceiling.box((0.03, 0.03, 0.01), (rnd.uniform(-half + 0.5, half - 0.5), rnd.uniform(front_y + 1, back_y - 0.5), ceil - 0.006), m["star"])
    for s in (-1, 1):
        ceiling.box((0.4, back_y - front_y - 2, 0.05), (s * (half - 1.2), (back_y + front_y) / 2, ceil - 0.5), m["led_blue"])
    lights = [("AREA", (0, -SD + 0.08, SZ), 9000 * SW * SH / 225, (0.8, 0.85, 1.0), (SW, SH), (90, 0, 0))]
    for s in (-1, 1):
        lights.append(("AREA", (s * (half - 0.6), (back_y + front_y) / 2, ceil - 0.8), 900 * (1.4 if imax else 1), (0.4, 0.6, 1.0), (0.3, back_y - front_y - 4), (0, s * 55, 0)))
    for y in range(int(back_y) - 2, int(front_y) + 2, -6):
        lights.append(("POINT", (0, y, ceil - 1.0), 200 if imax else 120, (1, 0.8, 0.6), 0.5, (0, 0, 0)))
    surround_speakers(shell, S.mats(), half, front_y, back_y, ROW, RISE, ceil)
    if imax:
        stage, more = imax_screen(m, front_z, half, ceil)
    else:
        stage, more = grand_screen(m, front_y, front_z, half, ceil, stage_h)
    return [shell.build(), floor.build(), seats.build(), ceiling.build(), stage], lights + more


def palace():
    m = M()
    ROW, RISE, half = 1.0, 0.27, 11.0
    rows = range(-6, 11)
    front_z = -RISE * 11
    back_y, front_y, ceil = 7.5, -SD - 2.5, 13.0
    shell, floor, seats, deco = (K.Builder("palace_shell"), K.Builder("palace_floor"),
                                 K.Builder("palace_seats"), K.Builder("palace_deco"))
    for k in rows:
        y, z = -k * ROW, -RISE * k
        floor.box((2 * half, ROW, 0.4), (0, y, z - 0.2), m["carpet_red"])
        blocks = [[-3.9 + 0.6 * i for i in range(14)], [4.9 + 0.6 * i for i in range(7)], [-4.9 - 0.6 * i for i in range(7)]]
        for xs in blocks:
            for x in xs:
                velvet_seat(seats, m, x, y, z)
            for x in sorted(xs):
                velvet_arm(seats, m, x - 0.3, y, z)
            velvet_arm(seats, m, max(xs) + 0.3, y, z)
    front_y0 = -(max(rows) + 0.5) * ROW
    floor.box((2 * half, front_y0 - front_y, 0.4), (0, (front_y0 + front_y) / 2, front_z - 0.2), m["carpet_red"])
    floor.box((SW + 3, 2.0, 1.1), (0, front_y + 1.0, front_z + 0.55), m["walnut"], bevel=0.03)    # stage
    # gold nosing 10 cm proud of the stage front (3 cm proud, it flashed against it at 15 m)
    floor.box((SW + 3.1, 0.2, 0.08), (0, front_y + 2.0, front_z + 1.1), m["gold"])
    # Walls: damask with marble columns, gold trims and wall lights
    for s in (-1, 1):
        x = s * half
        shell.box((0.3, back_y - front_y, ceil - front_z), (x + s * 0.15, (back_y + front_y) / 2, (ceil + front_z) / 2), m["wall_damask"])
        shell.box((0.12, back_y - front_y, 1.2), (x - s * 0.06, (back_y + front_y) / 2, front_z + 0.6 + 1.4), m["walnut"])
        y = back_y - 2.0
        while y > front_y + 3:
            deco.cyl(0.32, ceil - front_z, (x - s * 0.35, y, (ceil + front_z) / 2), m["marble"], segs=24)
            deco.box((0.9, 0.9, 0.35), (x - s * 0.35, y, ceil - 0.2), m["gold"], bevel=0.08)
            deco.box((0.9, 0.9, 0.35), (x - s * 0.35, y, front_z + 0.2), m["gold"], bevel=0.08)
            deco.box((0.18, 0.3, 0.45), (x - s * 0.12, y - 1.6, 3.4), m["lamp"], bevel=0.06, segs=3)
            deco.box((0.06, 0.08, 0.5), (x - s * 0.05, y - 1.6, 3.0), m["gold"], bevel=0.02)
            y -= 4.0
        # Balcony boxes on the side walls, gold railings
        for by in (-3.0, 2.0):
            deco.box((2.2, 3.0, 0.35), (x - s * 1.1, by, 5.2), m["walnut"], bevel=0.05)
            deco.box((0.1, 3.0, 0.9), (x - s * 2.2, by, 5.8), m["velvet_red"], bevel=0.03)
            deco.box((0.12, 3.05, 0.08), (x - s * 2.2, by, 6.3), m["gold"], bevel=0.03)
            for py in (-1.4, -0.7, 0.0, 0.7, 1.4):
                deco.cyl(0.03, 0.9, (x - s * 2.2, by + py, 5.8), m["gold"], segs=8)
        shell.box((0.08, back_y - front_y, 0.18), (x - s * 0.05, (back_y + front_y) / 2, ceil - 1.2), m["gold"])
    shell.box((2 * half + 0.6, 0.3, ceil - front_z), (0, back_y + 0.15, (ceil + front_z) / 2), m["wall_damask"])
    shell.box((1.8, 0.06, 0.5), (0, back_y - 0.02, 2.6), m["exit"])
    screen_wall(shell, m, front_y, front_z, 2 * half, ceil)
    # Proscenium arch: gilded frame, red velvet curtains with folds, a pelmet. All of it stands
    # at least 40 cm in front of the screen (the app masks the picture 25 cm in front of it)
    pw = SW + 2.4
    top = SZ + SH / 2 + 1.4
    for i, (grow, depth, mat) in enumerate([(2.2, 0.25, "walnut"), (1.6, 0.35, "gold"), (1.1, 0.45, "velvet_red"), (0.7, 0.55, "gold")]):
        deco.box((pw + grow, depth, 0.5), (0, -SD + 0.6 + depth / 2, top + grow / 2 - 0.3), m[mat], bevel=0.08, segs=3)
        z1 = SZ + 0.6 + (SH + 3.6 + grow) / 2
        z0 = max(SZ + 0.6 - (SH + 3.6 + grow) / 2, front_z)        # standing on the floor at most
        for s in (-1, 1):
            deco.box((0.5, depth, z1 - z0), (s * (pw / 2 + grow / 2), -SD + 0.6 + depth / 2, (z0 + z1) / 2), m[mat], bevel=0.08, segs=3)
    deco.box((2.4, 0.5, 1.5), (0, -SD + 1.0, top + 1.6), m["gold"], bevel=0.3, segs=4)       # crest
    c1 = SZ + 0.2 + (SH + 4.5) / 2
    c0 = max(SZ + 0.2 - (SH + 4.5) / 2, front_z + 0.15)              # hems well clear of the floor
    for s in (-1, 1):
        cx = s * (pw / 2 - 0.6)
        deco.grid(2.6, c1 - c0, (cx, -SD + 0.55, (c0 + c1) / 2), m["velvet_red"], 40, 4,
                  wave=lambda x: 0.12 * math.sin(x * 14.0))
    deco.grid(pw, 1.6, (0, -SD + 0.6, SZ + SH / 2 + 0.6), m["velvet_red"], 80, 6,
              wave=lambda x: 0.08 * math.sin(x * 10.0))
    ceiling = K.Builder("palace_ceiling")
    ceiling.box((2 * half + 0.6, back_y - front_y + 0.6, 0.3), (0, (back_y + front_y) / 2, ceil + 0.15), m["ceiling_cream"])
    for gx in range(-3, 4):                                         # coffers with gold ribs
        ceiling.box((0.18, back_y - front_y, 0.25), (gx * 3.0, (back_y + front_y) / 2, ceil - 0.12), m["gold"])
    for gy in range(int(back_y), int(front_y), -3):
        ceiling.box((2 * half, 0.18, 0.25), (0, gy, ceil - 0.12), m["gold"])
    # Crystal chandelier in the middle of the ceiling
    cy = (back_y + front_y) / 2 + 2
    ceiling.cyl(0.03, 2.0, (0, cy, ceil - 1.0), m["gold"], segs=8)
    for ring, (r, zz, n) in enumerate([(1.4, ceil - 2.4, 24), (1.0, ceil - 2.1, 18), (0.6, ceil - 1.8, 12)]):
        ceiling.cyl(r, 0.06, (0, cy, zz), m["gold"], segs=48)
        for i in range(n):
            a = 2 * math.pi * i / n
            ceiling.box((0.06, 0.06, 0.32), (r * math.cos(a), cy + r * math.sin(a), zz - 0.2), m["crystal"], rot=(0, 0, math.degrees(a)), bevel=0.02)
    lights = [("AREA", (0, -SD + 0.08, SZ), 5000, (0.8, 0.85, 1.0), (SW, SH), (90, 0, 0)),
              ("POINT", (0, cy, ceil - 2.4), 900, (1, 0.85, 0.6), 0.8, (0, 0, 0))]
    for s in (-1, 1):
        y = back_y - 2.0
        while y > front_y + 3:
            lights.append(("POINT", (s * (half - 0.35), y - 1.6, 3.5), 60, (1, 0.75, 0.45), 0.1, (0, 0, 0)))
            y -= 4.0
        lights.append(("AREA", (s * (pw / 2 - 0.5), -SD + 3.0, SZ + SH / 2 + 2.5), 600, (1, 0.6, 0.4), (1.0, 1.0), (60, 0, s * 20)))
    stage, more = palace_screen(m, front_y, front_z)
    return [shell.build(), floor.build(), seats.build(), deco.build(), ceiling.build(), stage], lights + more


def lounge():
    m = M()
    half, back_y, front_y, ceil = 5.0, 3.0, -SD - 1.0, 3.6
    shell, furn = K.Builder("lounge_shell"), K.Builder("lounge_furniture")
    shell.box((2 * half, back_y + 0.9, 0.3), (0, (back_y - 0.9) / 2, -0.15), m["carpet_pattern"])           # your row
    shell.box((2 * half, -3.3 - front_y, 0.3), (0, (-3.3 + front_y) / 2, -0.7 - 0.15), m["carpet_pattern"])  # by the screen
    shell.box((2 * half, 0.04, 0.03), (0, -3.32, -0.39), m["step"])
    # Walnut panelling with warm LED reveals, a coffered ceiling
    for s in (-1, 1):
        x = s * half
        shell.box((0.2, back_y - front_y, ceil + 0.3), (x + s * 0.1, (back_y + front_y) / 2, ceil / 2), m["walnut"])
        y = back_y - 0.4
        while y > front_y + 0.8:
            shell.box((0.05, 1.3, ceil - 0.9), (x - s * 0.03, y - 0.7, ceil / 2 + 0.1), m["walnut"], bevel=0.02)
            shell.box((0.03, 0.03, ceil - 0.9), (x - s * 0.04, y - 1.4, ceil / 2 + 0.1), m["led_warm"])
            y -= 1.5
    shell.box((2 * half + 0.4, 0.2, ceil + 0.3), (0, back_y + 0.1, ceil / 2), m["walnut"])
    screen_wall(shell, m, front_y, 0.0, 2 * half, ceil)
    shell.box((2 * half + 0.4, back_y - front_y + 0.4, 0.2), (0, (back_y + front_y) / 2, ceil + 0.1), m["ceiling_plum"])
    for gx in (-2.5, 0, 2.5):
        shell.box((0.12, back_y - front_y, 0.2), (gx, (back_y + front_y) / 2, ceil - 0.1), m["walnut"])
        shell.box((0.04, back_y - front_y - 0.6, 0.02), (gx, (back_y + front_y) / 2, ceil - 0.21), m["led_warm"])
    # You: the raised back row on a tan leather sofa; the front row two steps down ahead of you
    shell.box((2 * half, 2.4, 0.35), (0, -2.1, -0.35 - 0.175), m["carpet_pattern"])
    shell.box((2 * half, 0.04, 0.03), (0, -0.92, -0.04), m["step"])
    sofa(furn, m, 0.0, 0.1, 0.0, 3.0, cover="leather_tan")
    sofa(furn, m, -1.6, -2.1, -0.35, 2.4)
    sofa(furn, m, 1.6, -2.1, -0.35, 2.4)
    for x in (-2.15, 2.15):
        furn.box((0.5, 0.5, 0.55), (x, 0.05, 0.275), m["walnut"], bevel=0.03)
        furn.cyl(0.07, 0.35, (x, 0.0, 0.72), m["gold"], segs=12)
        furn.cyl(0.18, 0.25, (x, 0.0, 1.0), m["lamp"], segs=24)
        furn.cyl(0.035, 0.14, (x + 0.15, 0.15, 0.62), m["glass"], segs=12)
    lights = [("AREA", (0, -SD + 0.06, SZ), 900, (0.8, 0.85, 1.0), (SW, SH), (90, 0, 0)),
              ("POINT", (-2.15, 0.0, 1.05), 40, (1, 0.75, 0.45), 0.12, (0, 0, 0)),
              ("POINT", (2.15, 0.0, 1.05), 40, (1, 0.75, 0.45), 0.12, (0, 0, 0))]
    for gx in (-2.5, 0, 2.5):
        lights.append(("AREA", (gx, (back_y + front_y) / 2, ceil - 0.25), 12, (1, 0.7, 0.4), (0.1, back_y - front_y - 1), (0, 0, 0)))
    wall, more = lounge_screen(m, front_y, half, ceil, -0.7)
    return [shell.build(), furn.build(), wall], lights + more


def main():
    K.reset()
    objs, lights = {"grand": grand, "imax": grand, "palace": palace, "lounge": lounge}[HALL]()
    for i, (kind, loc, energy, color, size, rot) in enumerate(lights):
        # lights[0] is the screen: a white frame (x2.5 of an average film), baked on its own
        K.add_light(kind, loc, energy * (2.5 if i == 0 else 1), (1, 1, 1) if i == 0 else color, size, rot, screen=(i == 0))
    world = bpy.data.worlds.new("dark")
    bpy.context.scene.world = world
    world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.0
    print("triangles:", sum(len(o.data.polygons) for o in objs))
    if "--preview" in K.ARGS:
        K.setup_cycles(int(K.arg("--samples", 64)))
        K.dim_screens()
        cam = bpy.data.cameras.new("cam")
        cam.lens = float(K.arg("--lens", 14))
        ob = bpy.data.objects.new("cam", cam)
        ob.location = tuple(float(v) for v in K.arg("--cam", "0,0.1,1.15").split(","))   # x,y,z: your seat
        ob.rotation_euler = (math.radians(float(K.arg("--pitch", 88))), 0, math.radians(180 + float(K.arg("--yaw", 0))))
        bpy.context.scene.collection.objects.link(ob)
        bpy.context.scene.camera = ob
        r = bpy.context.scene.render
        r.resolution_x, r.resolution_y = 1600, 900
        r.filepath = K.arg("--preview")
        bpy.ops.render.render(write_still=True)
        return
    K.bake_all(objs, int(K.arg("--bake", 4096)), int(K.arg("--samples", 320)))
    K.export(objs, f"hall_{HALL}")


main()
