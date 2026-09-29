/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Fuzz the protocol parser + job controller with random and mutated frames under ASan/UBSan.
 * Invariants: no OOB, received <= total <= cap, pass_ready only for a complete swath of the matching idx. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../core/oi_job.h"
#define CHECK(c) do { if (!(c)) { fprintf(stderr, "INVARIANT FAIL %s:%d %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)

static uint64_t rng = 88172645463325252ull;
static uint32_t rnd(void) { rng ^= rng << 13; rng ^= rng >> 7; rng ^= rng << 17; return (uint32_t)(rng >> 16); }
static void sink(void *c, const uint8_t *f, size_t n) { (void)c; (void)f; (void)n; }

int main(int argc, char **argv) {
    long iters = argc > 1 ? atol(argv[1]) : 2000000;
    enum { CAP = 4096 };
    uint8_t *buf = malloc(CAP);                       /* heap so ASan sees overruns */
    oi_job_t j; oi_job_init(&j, buf, CAP);
    uint8_t frame[1100]; long passes = 0, dupstarts = 0;
    /* what a well-behaved host would send next: keeps sequences coherent so complete passes actually happen */
    uint16_t idx = 0; uint32_t cols = 1, sent = 0, total = 1; uint16_t bpc = 1;
    for (long i = 0; i < iters; i++) {
        size_t n; uint32_t k = rnd() % 100; uint8_t pl[64];
        if (k < 20) {                                 /* noise */
            n = rnd() % 64; for (size_t x = 0; x < n; x++) frame[x] = (uint8_t)rnd();
        } else if (k < 35) {                          /* new header (sometimes reusing the idx) */
            if (rnd() % 3) idx = (uint16_t)(rnd() % 4);
            cols = 1 + rnd() % 8; bpc = (uint16_t)(1 + rnd() % 4); total = cols * bpc; sent = 0;
            memset(pl, 0, 13); pl[0] = (uint8_t)idx; pl[1] = (uint8_t)(idx >> 8); pl[2] = (uint8_t)cols;
            pl[6] = (uint8_t)bpc; pl[8] = (rnd() & 1) ? 1 : 0xFF;
            n = oi_frame_build(frame, 1, pl, 13);
        } else if (k < 65) {                          /* data chunk at the right offset (10% wrong offset) */
            uint32_t off = (rnd() % 10 == 0) ? rnd() % (total + 2) : sent;
            uint32_t chunk = 1 + rnd() % 8; if (off + chunk > total && rnd() % 8) chunk = total > off ? total - off : 1;
            pl[0] = (uint8_t)off; pl[1] = (uint8_t)(off >> 8); pl[2] = pl[3] = 0;
            for (uint32_t x = 0; x < chunk; x++) pl[4 + x] = (uint8_t)rnd();
            n = oi_frame_build(frame, 2, pl, (uint16_t)(4 + chunk));
            if (off == sent && off + chunk <= total) sent += chunk;
        } else if (k < 85) {                          /* start (10% wrong idx) */
            uint16_t si = (rnd() % 10 == 0) ? (uint16_t)(idx + 1) : idx;
            pl[0] = (uint8_t)si; pl[1] = (uint8_t)(si >> 8);
            n = oi_frame_build(frame, 3, pl, 2);
        } else {                                      /* header/data/start with a flipped bit or truncation */
            pl[0] = (uint8_t)idx; pl[1] = 0; n = oi_frame_build(frame, 3, pl, 2);
            frame[rnd() % n] ^= (uint8_t)(1u << (rnd() % 8));
            if (rnd() % 3 == 0) n -= 1 + rnd() % (n - 1);
        }
        for (size_t x = 0; x < n; x++) oi_job_feed(&j, frame[x], sink, 0);
        CHECK(j.received <= j.total && j.total <= CAP);
        CHECK(!(j.pass_ready && j.busy));             /* a pass is either waiting or running, never both */
        if (j.pass_ready) CHECK(j.received == j.total && j.have_hdr && j.started);
        if (oi_job_take_pass(&j)) {
            CHECK(j.received == j.total && j.have_hdr && j.started && j.busy);
            passes++;
            if (rnd() & 1) oi_job_pass_done(&j);      /* sometimes leave the machine "busy" to fuzz BUSY handling */
        } else if (j.busy && rnd() % 4 == 0) oi_job_pass_done(&j);
        if (j.dup_acks) dupstarts = j.dup_acks;
    }
    printf("fuzz_job OK: %ld iterations, %ld passes, naks=%u busys=%u dups=%ld crc_errors=%u\n", iters, passes, j.naks, j.busys, dupstarts, j.parser.crc_errors);
    CHECK(passes > iters / 2000);                    /* the fuzzer must actually reach complete passes */
    CHECK(j.busys > 0 && j.naks > 0 && j.dup_acks > 0);
    free(buf);
    return 0;
}
