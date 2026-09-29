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
  CF="-std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined"
  gcc $CF -o /tmp/oi_test_sched tests/test_sched.c core/oi_sched.c
  gcc $CF -o /tmp/oi_test_proto tests/test_proto.c core/oi_proto.c
  gcc $CF -o /tmp/oi_test_modules tests/test_modules.c core/oi_head_matrix.c core/oi_motion.c core/oi_maint.c core/oi_job.c core/oi_proto.c
  /tmp/oi_test_sched
  /tmp/oi_test_proto /tmp/oi_vectors.bin
  /tmp/oi_test_modules )
( cd cad && python3 -m pytest -q test_cad.py && python3 assembly.py )
echo ALL TESTS PASSED
