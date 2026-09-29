/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Integer trapezoid planning for the carriage and paper feed (no FPU needed). */
#ifndef OI_MOTION_H
#define OI_MOTION_H
#include <stdint.h>

typedef struct {
    uint32_t accel_counts;   /* distance to accelerate 0 -> v_cruise */
    uint32_t cruise_counts;
    uint32_t decel_counts;
    uint32_t v_cruise;       /* counts/s actually reached (may be < requested for short moves) */
} oi_traj_t;

/* Plan a move of `dist` counts with max speed v_max and acceleration a (counts/s^2).
 * Returns 0 on success, -1 on invalid input (v_max or a == 0). accel+cruise+decel == dist. */
int oi_traj_plan(oi_traj_t *t, uint32_t dist, uint32_t v_max, uint32_t a);

/* Highest cruise speed (counts/s) allowed so the head never exceeds max_fire_hz at counts_per_dot (saturates at UINT32_MAX). */
uint32_t oi_max_cruise_for_head(uint32_t max_fire_hz, uint32_t counts_per_dot);

/* Paper feed: converts micrometres to motor steps carrying the fractional remainder, so the
 * cumulative error over any number of feeds stays below one step. */
typedef struct { uint32_t steps_per_mm_x1000; uint64_t carry; } oi_feed_t;
/* Returns -1 (and leaves f unusable) if steps_per_mm_x1000 == 0. */
int oi_feed_init(oi_feed_t *f, uint32_t steps_per_mm_x1000);
/* Whole steps to move for feed_um micrometres; remainder carried to the next call. */
uint64_t oi_feed_steps(oi_feed_t *f, uint32_t feed_um);
#endif
