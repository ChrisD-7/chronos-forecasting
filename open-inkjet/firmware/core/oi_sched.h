/* Encoder-synchronised fire scheduler (position based, not time based). */
#ifndef OI_SCHED_H
#define OI_SCHED_H
#include <stdint.h>
#include "oi_head.h"

typedef struct {
    oi_head_t *head;
    const uint8_t *columns;      /* columns * bytes_per_col packed bits */
    uint32_t n_columns;
    uint16_t bytes_per_col;
    int32_t counts_per_dot;      /* encoder counts between dots (>0) */
    int32_t origin_counts;       /* encoder position of column 0 (left-to-right) */
    int32_t bidir_offset_counts; /* alignment trim applied to right-to-left pass */
    /* state */
    int32_t next_col;            /* next column to fire, -1 when done */
    int8_t  dir;                 /* +1 or -1 */
    uint32_t fired;
    uint32_t missed;             /* columns skipped because encoder jumped past them */
} oi_sched_t;

void oi_sched_start(oi_sched_t *s, int8_t dir);
/* Call on every encoder update with the absolute position. Fires 0..n columns. */
void oi_sched_on_position(oi_sched_t *s, int32_t pos_counts);
#endif
