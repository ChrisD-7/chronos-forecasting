/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* HP45 nozzle -> (address << 8 | primitive) map. SAFE DEFAULT: unverified, so the firmware runs DRY (moves everything,
 * never pulses the head). To arm the head: measure the map per docs/BENCH.md, define OI_HEAD_MAP as an initialiser list of
 * 300 uint16_t entries, set OI_HEAD_MAP_VERIFIED to 1, and record the measurement in docs/MEASUREMENTS.md.
 * oi_matrix_head_init() additionally rejects duplicate/out-of-range entries. */
#ifndef OI_HEAD_MAP_H
#define OI_HEAD_MAP_H
#ifndef OI_HEAD_MAP_VERIFIED
#define OI_HEAD_MAP_VERIFIED 0
#endif
/* #define OI_HEAD_MAP { ... 300 entries ... } */
#endif
