#!/bin/sh
# Bakes every BuzzTorrent VR room (base + screen-light layer) and exports the GLBs.
# Give room names (e.g. ./run_all.sh space walk) to bake only those.
B="/c/Program Files/Blender Foundation/Blender 5.1/blender.exe"
ONLY=" $* "
run() { name="$1"; shift; [ "$ONLY" = "  " ] || case "$ONLY" in *" $name "*) ;; *) return ;; esac; echo "== $name $(date +%H:%M)"; "$B" -b -P "$@" > "$TEMP/bake_$name.log" 2>&1; grep -E "Traceback|Error:|exported|decimated" "$TEMP/bake_$name.log" | grep -v HIPEW | tail -4; }
run fire     make_fire.py                     # live flames' flipbook frames (assets/models/fire)
run lounge   build_halls.py   -- --hall lounge --bake 4096 --samples 256
run grand    build_halls.py   -- --hall grand  --bake 4096 --samples 256
run imax     build_halls.py   -- --hall imax   --bake 4096 --samples 256
run palace   build_halls.py   -- --hall palace --bake 4096 --samples 256
run space    build_space.py   -- --bake 4096 --samples 256
run jungle   build_jungle.py  -- --bake 4096 --samples 256
run drivein  build_drivein.py -- --bake 4096 --samples 256
run terrace  build_outdoor.py -- --scene terrace  --bake 4096 --samples 256
run stargaze build_outdoor.py -- --scene stargaze --bake 4096 --samples 256
run walk     build_walk.py                    # where you can stand in each room
echo "== done $(date +%H:%M)"
