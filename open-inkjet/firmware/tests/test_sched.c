#include <assert.h>
#include <stdio.h>
#include <string.h>
#include "../core/oi_sched.h"

static uint8_t log_first[64]; static int n_log;
static void fake_fire(oi_head_t *h, const uint8_t *bits) { (void)h; log_first[n_log++] = bits[0]; }

static oi_sched_t make(uint8_t *cols, oi_head_t *h, uint32_t n) {
    oi_sched_t s; memset(&s, 0, sizeof s);
    s.head = h; s.columns = cols; s.n_columns = n; s.bytes_per_col = 1;
    s.counts_per_dot = 2; s.origin_counts = 100; s.bidir_offset_counts = 1;
    return s;
}

int main(void) {
    uint8_t cols[5] = {10, 11, 12, 13, 14};
    oi_head_t h = {"fake", 8, fake_fire, 0};

    /* forward, every count visited: each column fires exactly once, in order */
    oi_sched_t s = make(cols, &h, 5); n_log = 0;
    oi_sched_start(&s, +1);
    for (int32_t p = 90; p <= 120; p++) oi_sched_on_position(&s, p);
    assert(s.fired == 5 && s.missed == 0 && n_log == 5);
    for (int i = 0; i < 5; i++) assert(log_first[i] == 10 + i);

    /* forward, column 0 fires only once pos>=100, not before */
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, +1);
    oi_sched_on_position(&s, 99); assert(n_log == 0);
    oi_sched_on_position(&s, 100); assert(n_log == 1 && log_first[0] == 10);

    /* reverse: last column first, with bidir offset (+1 count) */
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, -1);
    oi_sched_on_position(&s, 110); assert(n_log == 0); /* not yet: col4 target = 109 */
    oi_sched_on_position(&s, 109);
    assert(n_log == 1 && log_first[0] == 14);
    for (int32_t p = 110; p >= 90; p--) oi_sched_on_position(&s, p);
    assert(s.fired == 5 && log_first[4] == 10);

    /* encoder jump past a whole dot: that column is counted as missed, not fired late */
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, +1);
    oi_sched_on_position(&s, 105);       /* col0@100 late 5>=2 missed, col1@102 missed, col2@104 late1 fires */
    assert(s.missed == 2 && s.fired == 1 && log_first[0] == 12);

    puts("sched tests OK");
    return 0;
}
