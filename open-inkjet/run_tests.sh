#!/usr/bin/env bash
# Runs every test in the project: host (pytest), firmware (C, sanitizers, cross-language vectors), CAD.
set -euo pipefail
cd "$(dirname "$0")"
( cd host && PYTHONPATH=. python3 -m pytest -q tests )
( cd host && PYTHONPATH=. python3 -c "
from PIL import Image
from openinkjet.filter import frames_for_image
open('/tmp/oi_vectors.bin','wb').write(b''.join(frames_for_image(Image.new('L',(64,64),100))))" )
( cd firmware
  for t in sched proto; do
    src="core/oi_$t.c"; [ $t = sched ] && extra="" || extra=""
    gcc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined -o /tmp/oi_test_$t tests/test_$t.c $src
  done
  /tmp/oi_test_sched
  /tmp/oi_test_proto /tmp/oi_vectors.bin )
( cd cad && python3 carriage_plate.py && rm -f carriage_plate.stl )
echo ALL TESTS PASSED
