#!/usr/bin/env bash
# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
# Runs every test in the project: host (pytest), firmware (C, sanitizers, cross-language vectors), CAD.
set -euo pipefail
cd "$(dirname "$0")"
T="$(mktemp -d)"; trap 'rm -rf "$T"' EXIT      # private scratch dir (no fixed /tmp names)
( cd host && PYTHONPATH=. python3 -m pytest -q tests )
( cd host && PYTHONPATH=. python3 -c "
from PIL import Image
from openinkjet.filter import frames_for_image
open('$T/vectors.bin','wb').write(b''.join(frames_for_image(Image.new('L',(64,64),100))))" )
( cd firmware
  CF="-std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined"
  gcc $CF -o $T/t_sched tests/test_sched.c core/oi_sched.c
  gcc $CF -o $T/t_proto tests/test_proto.c core/oi_proto.c
  gcc $CF -o $T/t_modules tests/test_modules.c core/oi_head_matrix.c core/oi_motion.c core/oi_maint.c core/oi_job.c core/oi_proto.c
  gcc $CF -o $T/t_app tests/test_app.c core/oi_app.c core/oi_job.c core/oi_proto.c core/oi_sched.c core/oi_motion.c core/oi_maint.c
  $T/t_sched
  $T/t_proto $T/vectors.bin
  $T/t_modules
  $T/t_app
  gcc $CF -o $T/fuzz tests/fuzz_job.c core/oi_job.c core/oi_proto.c && $T/fuzz 300000 )
if [ "${1:-}" = "--mutate" ]; then python3 tools_mutate.py $T/vectors.bin; fi
( cd cad && python3 -m pytest -q test_cad.py && python3 assembly.py )
echo ALL TESTS PASSED
