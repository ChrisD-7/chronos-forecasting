# open-inkjet

Open, 3D-printable, A4 sheet-fed inkjet printer. Linear-rail carriage, HP 45 (51645A) printhead in v1,
printhead-abstracted firmware (`oi_head_t`, plus an address/primitive matrix driver) so other heads can be added.
Clean-room design: nothing is copied from Open Printer (Open Tools), which is CC BY-NC-SA 4.0.

**Status: complete in software and simulation; no hardware has been built or measured.** Read `docs/VERIFICATION.md`
for exactly what is tested, simulated, sourced-but-unverified, and untested, and `docs/BENCH.md` for the procedures
that turn placeholders into measurements. `docs/PLAN.md` holds the original plan and sources.

| Path | Contents | License |
|---|---|---|
| `cad/`, `bom/` | parametric CadQuery parts (side plate, carriage plate, cartridge holder, roller block, cap base), assembly checks, BOM | CERN-OHL-S-2.0 |
| `firmware/core` | C99: protocol parser, job controller (ACK/NAK/BUSY), encoder-synced fire scheduler, matrix head driver, motion + feed planner, maintenance FSM | GPL-3.0-only |
| `firmware/tests` | unit tests, fuzzer, full printer simulator (`sim.c`) | GPL-3.0-only |
| `host/openinkjet` | geometry, slicer, halftone, protocol, sender, serial link, CUPS filter/backend | GPL-3.0-only |
| `host/bin`, `host/cups`, `host/install_cups.sh` | CUPS executables, PPD, installer (untested on real CUPS) | GPL-3.0-only |
| `docs/` | plan, verification log, bench procedures, measurements template | CC-BY-4.0 |

Repository root (chronos-forecasting) is Apache-2.0 and unrelated; this folder carries its own licenses in `licenses/`.
"HP" is a trademark of HP Inc.; this project is "compatible with HP 45", not affiliated.

## Run everything
    pip install numpy pillow pytest cadquery      # gcc required for the firmware and end-to-end tests
    ./run_tests.sh                                # host + firmware (ASan/UBSan) + fuzz + simulator + CAD
    ./run_tests.sh --mutate                       # additionally: 32 firmware mutants must all be killed
