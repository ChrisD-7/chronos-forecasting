# Plan: Clean-room open inkjet printer (Open Printer-inspired), A4 sheet-fed, linear rail, 3D-printable

## Context
Goal: build an inkjet printer inspired by Open Tools' "Open Printer", but with (a) linear rails instead of rods, (b) A4 sheets instead of roll, (c) a mostly 3D-printed frame. Decisions from user: new repo (not chronos-forecasting, which is unrelated), clean-room own design, HP 45 (51645A) printhead, manual single-sheet feed first.

## Research findings (with sources and confidence)
Confidence tags: [S] seen in a search-result snippet from the cited page; [I] my inference; [X] unverified/conflicting. Direct page fetches of crowdsupply, hackaday.io, opentools.studio, tomshardware, techpowerup were blocked by the sandbox egress proxy, so nothing below was read from the primary source page.

Open Printer (Open Tools, Paris)
- Raspberry Pi Zero W main board + STM32 cartridge board; HP 63 (US) / HP 302 (EU) refillable cartridges; 600 dpi mono, 1200 dpi colour claimed; CUPS, no proprietary driver; A3 sheets or 297 mm roll with cutter. [S] https://linuxiac.com/open-printer-promises-freedom-from-proprietary-cartridges/ , https://www.crowdsupply.com/open-tools/openprinter
- License: CC BY-NC-SA 4.0 for electronics, mechanics, firmware, BOM. NC clause means source-available, not OSI/FSF open source; criticised on HN/Reddit. [S] https://www.techpowerup.com/350824/open-printer-previewed-as-open-source-drm-free-printer
- Status: campaign planned Autumn 2026, no price/ship date/funding goal as of 2026-09-17. [S] https://www.crowdsupply.com/open-tools/openprinter/updates
- [X] Whether design files are already downloadable: one search summary said "released", but Crowd Supply text says "will use" the license. Not verified; the clean-room choice makes this non-blocking.
- [S] Rod vs rail internals of Open Printer were not found in any snippet. Do not assume.

HP 45 / 51645A (chosen printhead)
- 300 nozzles at 600 dpi spacing, swath 12.7 mm, 12 V, 52 contacts, ~30 ohm heater resistor, ~2 us fire pulse, max ~18 kHz, recommended 300 dpi. [S] https://ytec3d.com/hp45-inkjet-printhead/
- Controllable by fast MCUs with many pins (Arduino Mega/Due class); prior art: MagicPaintBrush (Sprite_tm), Ink Shield, Hackaday cartridge control module. [S] https://hackaday.io/project/176931-hp-printer-cartridge-control-module
- Still sold new/remanufactured by many vendors (no discontinuation found). [S] https://www.cartridgepros.com/hp-45-hp-51645a-51645a-detail.htm
- Risk [I]: legacy cartridge, black only, single-nozzle-column pair. Long-term supply depends on remanufacturers; keep a printhead-abstraction layer so HP 302/63 can be added later.

Linear rail choice
- MGN12 (12 mm rail) is the stiffer default for XY; MGN9 lighter, rail can "sing" under load; H (long) carriage stiffer than C. [S] https://cncrouterinfo.com/guides/mgn9-vs-mgn12-vs-mgn15/
- Inkjet carriage is light (cartridge ~40-60 g [I]), so MGN9H is likely enough and cheaper/lighter; benchmark both. [I]

Derived design numbers [I, my arithmetic]
- A4 = 210 x 297 mm. Carriage travels across 210 mm width plus margins (~260 mm rail; MGN 250/300 stock lengths). Paper feeds along 297 mm: 297 / 12.7 ~ 24 swaths per page at full swath.
- 300 dpi dot pitch = 84.7 um. Fire timing must be encoder-driven (linear optical encoder strip), not time-based, to avoid banding.

## Architecture (recommended)
- Carriage: printed carriage on 1x MGN9H/MGN12H rail, GT2 belt + NEMA17 (or NEMA14), linear encoder strip + reader on carriage.
- Paper path: manual single-sheet feed; stepper-driven feed roller pair (rubber roller + idler), platen with vacuum-free flat guide; paper-present sensor; later upgrade to tray pickup.
- Electronics: RP2040/RP2350 (PIO for deterministic fire timing) or STM32 as printhead controller; separate MOSFET/driver stage for 12 V heater rows and address lines; Pi Zero 2 W (or ESP32) as CUPS host. Mirrors Open Printer's split (SBC + MCU) without copying it.
- Software: CUPS filter (raster to 1-bit halftoned swaths) -> serial/USB to MCU -> encoder-synced fire. Reuse prior art logic from MagicPaintBrush for pulse timing (check its license before copying anything).
- Maintenance: capping station + wipe/spit routine (HP45 dries out; must be in v1 or nozzles die). [I]
- License of our output: CERN-OHL-S (hardware) + GPL-3.0/MIT (firmware), permits commercial manufacture, addressing the NC criticism.
- 3D-print rules: keep parts printable on a 220 mm bed (split the 300+ mm frame), PETG/ASA, only metal = rail, rods for feed roller, screws, bearings, motors.

## Phases
1. Repo + docs: create new repo, research notes, BOM draft, license. (Nothing goes in chronos-forecasting.)
2. Printhead bench: HP45 breakout board, drive one swath statically on a fixed test rig, verify pinout empirically with a multimeter/scope (do not trust one source).
3. Carriage + encoder: rail, belt, encoder, closed timing loop; test print of vertical lines to measure registration.
4. Paper feed: roller drive, step calibration, skew test pattern.
5. Full page: CUPS filter, 300 dpi A4 test, margin/banding tuning.
6. Maintenance (cap/wipe), enclosure, tray pickup as stretch.

## Verification
- Bench: scope trace of fire pulse (~2 us) and address/primitive timing vs datasheet values above.
- Print tests: 1-pixel line registration across 210 mm, bidirectional alignment, banding at swath joins, ruler test on 297 mm feed accuracy (target under 0.2 mm cumulative, my proposed target).
- Repeatability: 50-page run, nozzle-check pattern before and after.

## Open questions still worth confirming later
- Colour is out of scope with HP 45 black-only; is monochrome acceptable, or add HP 41/78 tri-colour (also documented) later?
- Motor/MCU preferences (RP2040 vs STM32), and a target BOM budget.
- Whether to fetch Open Printer's files from a browser yourself; the sandbox could not reach opentools.studio/hackaday.io/crowdsupply.
