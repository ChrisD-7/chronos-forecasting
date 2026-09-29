#include <stdlib.h>
#define assert(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)
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
    assert(oi_sched_start(&s, +1) == OI_OK);
    for (int32_t p = 90; p <= 120; p++) oi_sched_on_position(&s, p);
    assert(s.fired == 5 && s.missed == 0 && n_log == 5);
    for (int i = 0; i < 5; i++) assert(log_first[i] == 10 + i);

    /* forward, column 0 fires only once pos>=100, not before */
    s = make(cols, &h, 5); n_log = 0; assert(oi_sched_start(&s, +1) == OI_OK);
    oi_sched_on_position(&s, 99); assert(n_log == 0);
    oi_sched_on_position(&s, 100); assert(n_log == 1 && log_first[0] == 10);

    /* reverse: last column first, with bidir offset (+1 count) */
    s = make(cols, &h, 5); n_log = 0; assert(oi_sched_start(&s, -1) == OI_OK);
    oi_sched_on_position(&s, 110); assert(n_log == 0); /* not yet: col4 target = 109 */
    oi_sched_on_position(&s, 109);
    assert(n_log == 1 && log_first[0] == 14);
    for (int32_t p = 110; p >= 90; p--) oi_sched_on_position(&s, p);
    assert(s.fired == 5 && log_first[4] == 10);

    /* encoder jump past a whole dot: that column is counted as missed, not fired late */
    s = make(cols, &h, 5); n_log = 0; assert(oi_sched_start(&s, +1) == OI_OK);
    oi_sched_on_position(&s, 105);       /* col0@100 late 5>=2 missed, col1@102 missed, col2@104 late1 fires */
    assert(s.missed == 2 && s.fired == 1 && log_first[0] == 12);

    /* boundary: exactly one dot late is MISSED (late >= counts_per_dot), one count late fires */
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, +1);
    oi_sched_on_position(&s, 101);                  /* col0 late by 1 (<2) fires; col1@102 not reached */
    assert(s.fired == 1 && s.missed == 0);
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, +1);
    oi_sched_on_position(&s, 102);                  /* col0 late by exactly 2 -> missed; col1 exactly on time fires */
    assert(s.missed == 1 && s.fired == 1 && log_first[0] == 11);

    /* reverse jump: overshoot past columns walking left counts them as missed */
    s = make(cols, &h, 5); n_log = 0; oi_sched_start(&s, -1);
    oi_sched_on_position(&s, 100);                  /* col4@109 late 9, col3@107 late 7, col2@105 late 5, col1@103 late 3 -> missed; col0@101 late 1 fires */
    assert(s.missed == 4 && s.fired == 1 && log_first[0] == 10);

    /* multi-byte columns: stride must be bytes_per_col */
    uint8_t wide[6] = {1, 2, 3, 4, 5, 6};
    oi_head_t h16 = {"fake16", 16, fake_fire, 0};
    oi_sched_t w; memset(&w, 0, sizeof w);
    w.head = &h16; w.columns = wide; w.n_columns = 3; w.bytes_per_col = 2; w.counts_per_dot = 1; w.origin_counts = 0;
    n_log = 0; assert(oi_sched_start(&w, +1) == OI_OK);
    for (int32_t p = 0; p < 4; p++) oi_sched_on_position(&w, p);
    assert(n_log == 3 && log_first[0] == 1 && log_first[1] == 3 && log_first[2] == 5);

    /* config validation and hang guards */
    s = make(cols, &h, 5); assert(oi_sched_start(&s, 0) == OI_ERR_CONFIG);
    oi_sched_on_position(&s, 100000); assert(s.fired == 0);          /* disarmed: returns, does not hang */
    s = make(cols, &h, 5); s.counts_per_dot = 0; assert(oi_sched_start(&s, 1) == OI_ERR_CONFIG);
    s = make(cols, &h, 5); s.counts_per_dot = -2; assert(oi_sched_start(&s, 1) == OI_ERR_CONFIG);
    s = make(cols, &h, 5); s.bytes_per_col = 0; assert(oi_sched_start(&s, 1) == OI_ERR_CONFIG);   /* 8 nozzles need 1 byte */
    s = make(cols, &h, 5); s.n_columns = 0x80000000u; assert(oi_sched_start(&s, 1) == OI_ERR_CONFIG);
    s = make(cols, &h, 5); s.head = 0; assert(oi_sched_start(&s, 1) == OI_ERR_CONFIG);
    s = make(cols, &h, 5); assert(oi_sched_start(&s, 7) == OI_OK && s.dir == 1);  /* nonzero coerced to +1 */
    s = make(cols, &h, 0); assert(oi_sched_start(&s, 1) == OI_OK);
    oi_sched_on_position(&s, 1000); assert(s.fired == 0 && s.next_col == -1);     /* zero columns: no fire, no hang */

    /* overflow: extreme origin/counts must not be UB (UBSan) and must behave correctly */
    s = make(cols, &h, 5); s.origin_counts = INT32_MAX - 4; s.counts_per_dot = 4;
    assert(oi_sched_start(&s, 1) == OI_OK);
    oi_sched_on_position(&s, INT32_MAX);            /* col0@MAX-4 is exactly one dot late -> missed; col1@MAX on time -> fires; col2+ beyond int32, not reached */
    assert(s.fired == 1 && s.missed == 1);
    s = make(cols, &h, 5); s.origin_counts = INT32_MIN; assert(oi_sched_start(&s, 1) == OI_OK);
    oi_sched_on_position(&s, INT32_MAX);            /* pos - target = 2^32-1 fits int64: all columns missed */
    assert(s.missed == 5 && s.fired == 0);
    s = make(cols, &h, 5); s.n_columns = 5; s.counts_per_dot = 1000000000; assert(oi_sched_start(&s, 1) == OI_OK);
    oi_sched_on_position(&s, 0);                    /* col4 target 4e9+100 overflows int32 in the old code */
    assert(s.fired == 0);

    puts("sched tests OK");
    return 0;
}
