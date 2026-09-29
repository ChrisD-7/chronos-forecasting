/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
#include "oi_sched.h"

/* All position arithmetic is int64 so origin/col/offset extremes cannot overflow (signed overflow is UB). */
static int64_t col_pos(const oi_sched_t *s, int32_t col) {
    int64_t p = (int64_t)s->origin_counts + (int64_t)col * s->counts_per_dot;
    if (s->dir < 0) p += s->bidir_offset_counts;
    return p;
}

oi_status_t oi_sched_start(oi_sched_t *s, int dir) {
    s->next_col = -1;   /* disarmed until validation passes */
    s->fired = 0;
    s->missed = 0;
    s->dir = 0;
    if (dir == 0 || !s->head || !s->head->fire_column || !s->columns) return OI_ERR_CONFIG;
    if (s->counts_per_dot <= 0) return OI_ERR_CONFIG;
    if (s->n_columns > (uint32_t)INT32_MAX) return OI_ERR_CONFIG;
    if ((uint32_t)s->bytes_per_col * 8u < s->head->nozzles) return OI_ERR_CONFIG;
    s->dir = (dir > 0) ? 1 : -1;
    s->next_col = (s->dir > 0) ? 0 : (int32_t)s->n_columns - 1;
    return OI_OK;
}

void oi_sched_on_position(oi_sched_t *s, int32_t pos) {
    if (s->dir == 0) return;   /* not armed */
    while (s->next_col >= 0 && s->next_col < (int32_t)s->n_columns) {
        int64_t target = col_pos(s, s->next_col);
        int reached = (s->dir > 0) ? ((int64_t)pos >= target) : ((int64_t)pos <= target);
        if (!reached) return;
        /* if we overshot by a full dot, this column is missed, not fired late */
        int64_t late = (s->dir > 0) ? (int64_t)pos - target : target - (int64_t)pos;
        if (late >= s->counts_per_dot) {
            s->missed++;
        } else {
            s->head->fire_column(s->head, s->columns + (size_t)s->next_col * s->bytes_per_col);
            s->fired++;
        }
        s->next_col += s->dir;
    }
    s->next_col = -1; /* ran off the end: pass complete */
}
