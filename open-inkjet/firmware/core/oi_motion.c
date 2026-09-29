/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
#include "oi_motion.h"

int oi_traj_plan(oi_traj_t *t, uint32_t dist, uint32_t v_max, uint32_t a) {
    if (v_max == 0 || a == 0) return -1;
    uint64_t ad = (uint64_t)v_max * v_max / (2ull * a);      /* accel distance to reach v_max */
    if (2 * ad <= dist) {
        t->accel_counts = t->decel_counts = (uint32_t)ad;
        t->cruise_counts = dist - 2 * (uint32_t)ad;
        t->v_cruise = v_max;
    } else {                                                  /* triangular: peak below v_max */
        t->accel_counts = dist / 2; t->decel_counts = dist - dist / 2; t->cruise_counts = 0;
        uint64_t v2 = 2ull * a * t->accel_counts, v = 0;
        for (int bit = 31; bit >= 0; bit--) {                 /* bitwise integer sqrt: 32 iterations, no data-dependent loop */
            uint64_t cand = v | (1ull << bit);
            if (cand * cand <= v2) v = cand;
        }
        t->v_cruise = (uint32_t)v;
    }
    return 0;
}

uint32_t oi_max_cruise_for_head(uint32_t max_fire_hz, uint32_t counts_per_dot) {
    uint64_t v = (uint64_t)max_fire_hz * counts_per_dot;   /* one dot per fire period at the head's limit */
    return v > 0xFFFFFFFFull ? 0xFFFFFFFFu : (uint32_t)v;
}

int oi_feed_init(oi_feed_t *f, uint32_t steps_per_mm_x1000) {
    f->steps_per_mm_x1000 = steps_per_mm_x1000; f->carry = 0;
    return steps_per_mm_x1000 ? 0 : -1;
}

uint64_t oi_feed_steps(oi_feed_t *f, uint32_t feed_um) {
    /* steps = feed_um/1000 mm * steps_per_mm_x1000/1000 = feed_um * spm_x1000 / 1e6 */
    uint64_t num = (uint64_t)feed_um * f->steps_per_mm_x1000 + f->carry;
    f->carry = num % 1000000ull;
    return num / 1000000ull;
}
