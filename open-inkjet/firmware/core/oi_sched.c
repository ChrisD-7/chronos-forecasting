#include "oi_sched.h"

static int32_t col_pos(const oi_sched_t *s, int32_t col) {
    int32_t p = s->origin_counts + col * s->counts_per_dot;
    if (s->dir < 0) p += s->bidir_offset_counts;
    return p;
}

void oi_sched_start(oi_sched_t *s, int8_t dir) {
    s->dir = dir;
    s->next_col = (dir > 0) ? 0 : (int32_t)s->n_columns - 1;
    s->fired = 0;
    s->missed = 0;
}

void oi_sched_on_position(oi_sched_t *s, int32_t pos) {
    while (s->next_col >= 0 && s->next_col < (int32_t)s->n_columns) {
        int32_t target = col_pos(s, s->next_col);
        int reached = (s->dir > 0) ? (pos >= target) : (pos <= target);
        if (!reached) return;
        /* if we overshot by a full dot, this column is missed, not fired late */
        int32_t late = (s->dir > 0) ? pos - target : target - pos;
        if (late >= s->counts_per_dot) {
            s->missed++;
        } else {
            s->head->fire_column(s->head, s->columns + (uint32_t)s->next_col * s->bytes_per_col);
            s->fired++;
        }
        s->next_col += s->dir;
    }
    s->next_col = -1; /* ran off the end: pass complete */
}
