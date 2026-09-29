# open-inkjet

Open, 3D-printable, A4 sheet-fed inkjet printer. Linear-rail carriage, HP 45 (51645A) printhead in v1,
printhead-abstracted firmware so other heads can be added. Clean-room design: nothing is copied from
Open Printer (Open Tools), which is CC BY-NC-SA 4.0.

Status: software core + parametric CAD stub + docs. **No hardware has been built or measured yet.**
See `docs/VERIFICATION.md` for what is verified vs. still assumed, and `docs/PLAN.md` for the plan and sources.

| Path | Contents | License |
|---|---|---|
| `cad/`, `bom/` | parametric CadQuery parts, bill of materials | CERN-OHL-S-2.0 |
| `firmware/` | encoder-synced fire scheduler, head abstraction (C99) | GPL-3.0-only |
| `host/` | geometry math, raster-to-swath slicer (Python) | GPL-3.0-only |
| `docs/` | plan, verification log | CC-BY-4.0 |

The repository root (chronos-forecasting) is Apache-2.0 and unrelated; this folder carries its own licenses in `licenses/`.
"HP" is a trademark of HP Inc.; this project is "compatible with HP 45", not affiliated.

## Run the tests
    cd host && python3 -m pip install numpy pytest && PYTHONPATH=. python3 -m pytest -q tests
    cd firmware && gcc -std=c99 -Wall -Wextra -Werror -fsanitize=address,undefined -o /tmp/t tests/test_sched.c core/oi_sched.c && /tmp/t
    cd cad && python3 -m pip install cadquery && python3 carriage_plate.py
