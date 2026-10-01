# open-inkjet

Open, 3D-printable, A4 sheet-fed inkjet printer. Linear-rail carriage, HP 45 (51645A) printhead in v1,
printhead-abstracted firmware (`oi_head_t`, plus an address/primitive matrix driver) so other heads can be added.
Clean-room design: nothing is copied from Open Printer (Open Tools), which is CC BY-NC-SA 4.0.

**Status: a well-tested software model of the printer, board firmware that compiles for an RP2040, a block-level electronics design and a CAD kit sized from guessed dimensions. It is NOT yet a working printer:** no analog head-driver circuit, no schematic or PCB, no measured parts, nothing printed or powered. Read `docs/VERIFICATION.md`
for exactly what is tested, simulated, sourced-but-unverified, and untested, and `docs/BENCH.md` for the procedures
that turn placeholders into measurements. `docs/PLAN.md` holds the original plan and sources.

| Path | Contents | License |
|---|---|---|
| `cad/`, `bom/` | parametric CadQuery parts (side plate, carriage plate + bracket, cartridge holder, roller block, cap base, platen halves, motor/sensor/encoder mounts), stack and layout checks, BOM | CERN-OHL-S-2.0 |
| `firmware/core` | C99: protocol parser, job controller (ACK/NAK/BUSY/page end), encoder-synced fire scheduler, matrix head driver, motion + feed planner, maintenance FSM, board-independent application core (`oi_app`, HAL-based) | GPL-3.0-only |
| `firmware/tests` | unit tests, fuzzer, full printer simulator (`sim.c`) | GPL-3.0-only |
| `host/openinkjet` | geometry, slicer, halftone, protocol, sender, serial link, CUPS filter/backend | GPL-3.0-only |
| `host/bin`, `host/cups`, `host/install_cups.sh` | CUPS executables, PPD, installer (untested on real CUPS) | GPL-3.0-only |
| `firmware/board/rp2040` | Pico SDK board layer: encoder IRQ, step generation, 74HC595 head interface, servos, USB CDC, dual-core main. Compiles (dry and armed variants); never run on hardware. DRY by default | GPL-3.0-only |
| `electronics/` | head-drive budgets and block-level netlist with ERC rules, pin kinds and firmware bit-order simulation (no schematic/PCB yet) | CERN-OHL-S-2.0 |
| `docs/` | plan, verification log, bench procedures, electronics design, measurements template | CC-BY-4.0 |

Repository root (chronos-forecasting) is Apache-2.0 and unrelated; this folder is licensed independently, see `NOTICE.md`, `REUSE.toml` and `licenses/` (SPDX headers are in every source file). Provenance: `docs/PROVENANCE.md`.
"HP" is a trademark of HP Inc.; this project is "compatible with HP 45", not affiliated.

## Run everything
    pip install numpy pillow pytest cadquery      # gcc required for the firmware and end-to-end tests
    ./run_tests.sh                                # host + firmware (ASan/UBSan) + fuzz + simulator + CAD
    ./run_tests.sh --mutate                       # additionally: 53 firmware mutants must all be killed
    export PICO_SDK_PATH=/path/to/pico-sdk        # 2.x with submodules; also builds the RP2040 firmware (needs gcc-arm-none-eabi, cmake, ninja)
