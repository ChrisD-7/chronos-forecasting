#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define assert(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)
#include "../core/oi_head_matrix.h"
#include "../core/oi_motion.h"
#include "../core/oi_maint.h"
#include "../core/oi_job.h"

/* ---- matrix head with a recording HAL ---- */
static struct { int n; uint8_t addr[64]; uint32_t prim[64]; int active_addr_violations; int cur; int idle; } rec;
static void h_addr(void *hw, uint8_t a) { (void)hw; rec.cur = a; }
static void h_prim(void *hw, uint32_t m) { (void)hw; rec.prim[rec.n] = m; rec.addr[rec.n] = (uint8_t)rec.cur; }
static void h_pulse(void *hw) { (void)hw; rec.n++; }
static void h_idle(void *hw) { (void)hw; rec.idle++; }
static const oi_matrix_hal_t HAL = { h_addr, h_prim, h_pulse, h_idle, 0 };

static void test_matrix(void) {
    uint16_t map[300];
    for (int n = 0; n < 300; n++) map[n] = (uint16_t)(((n % 22) << 8) | (n / 22));
    oi_matrix_head_t m;
    assert(oi_matrix_head_init(&m, &HAL, map, 300, 22, 14) == 0);
    uint8_t bits[38]; memset(bits, 0, sizeof bits);
    memset(&rec, 0, sizeof rec);
    m.head.fire_column(&m.head, bits);
    assert(rec.n == 0 && rec.idle == 1);                       /* nothing to fire: no pulses, lines idled */
    memset(bits, 0xFF, sizeof bits); bits[37] = 0x0F;          /* all 300 nozzles (37*8 + 4 = 300) */
    memset(&rec, 0, sizeof rec);
    m.head.fire_column(&m.head, bits);
    assert(rec.n == 22 && m.pulses == 22);                     /* one pulse per address, never two addresses at once */
    int seen[300] = {0};
    for (int i = 0; i < rec.n; i++)
        for (int p = 0; p < 14; p++) if (rec.prim[i] & (1u << p)) {
            int nz = -1; for (int n = 0; n < 300; n++) if (map[n] == ((rec.addr[i] << 8) | p)) nz = n;
            assert(nz >= 0); seen[nz]++;
        }
    for (int n = 0; n < 300; n++) assert(seen[n] == 1);        /* every nozzle exactly once */
    /* single nozzle 137 -> exactly one pulse, exactly one primitive */
    memset(bits, 0, sizeof bits); bits[137 >> 3] = (uint8_t)(1u << (137 & 7));
    memset(&rec, 0, sizeof rec); m.head.fire_column(&m.head, bits);
    assert(rec.n == 1 && rec.addr[0] == 137 % 22 && rec.prim[0] == 1u << (137 / 22));
    /* invalid maps rejected: duplicate slot, out of range */
    uint16_t dup[300]; memcpy(dup, map, sizeof map); dup[5] = dup[6];
    assert(oi_matrix_head_init(&m, &HAL, dup, 300, 22, 14) == -1);
    uint16_t oob[300]; memcpy(oob, map, sizeof map); oob[5] = (uint16_t)((22 << 8) | 0);
    assert(oi_matrix_head_init(&m, &HAL, oob, 300, 22, 14) == -1);
    assert(oi_matrix_head_init(&m, &HAL, map, 300, 0, 14) == -1);
}

/* ---- motion ---- */
static void test_motion(void) {
    oi_traj_t t;
    assert(oi_traj_plan(&t, 1000, 0, 100) == -1 && oi_traj_plan(&t, 1000, 100, 0) == -1);
    assert(oi_traj_plan(&t, 100000, 6000, 300000) == 0);
    assert(t.v_cruise == 6000 && t.accel_counts == 60 && t.cruise_counts == 100000 - 120 && t.decel_counts == 60);
    assert(t.accel_counts + t.cruise_counts + t.decel_counts == 100000);
    assert(oi_traj_plan(&t, 50, 6000, 300) == 0);              /* short move: triangular, peak below v_max */
    assert(t.cruise_counts == 0 && t.v_cruise < 6000 && t.accel_counts + t.decel_counts == 50);
    assert((uint64_t)t.v_cruise * t.v_cruise <= 2ull * 300 * t.accel_counts);
    assert(oi_traj_plan(&t, 1, 6000, 300) == 0 && t.accel_counts + t.decel_counts == 1);
    assert(oi_max_cruise_for_head(18000, 2) == 36000);
}

static void test_feed(void) {
    oi_feed_t f; oi_feed_init(&f, 157480);                       /* 157.480 steps/mm: fractional */
    uint64_t total_steps = 0;
    for (int i = 0; i < 1000; i++) total_steps += oi_feed_steps(&f, 12700);
    /* exact cumulative: 1000 * 12.7mm * 157.48 = 2000000 - fraction; error < 1 step */
    uint64_t exact_x = 1000ull * 12700 * 157480;                 /* um * (steps/mm x1000) */
    uint64_t want = exact_x / 1000000ull;
    assert(total_steps == want);
    assert(oi_feed_steps(&f, 0) <= 1);
    oi_feed_t g; oi_feed_init(&g, 1000);
    assert(oi_feed_steps(&g, 999) == 0 && oi_feed_steps(&g, 1) == 1);   /* carry: 0.999 + 0.001 -> 1 step */
}

/* ---- maintenance ---- */
static void test_maint(void) {
    oi_maint_t m; oi_maint_init(&m, 1000, 2, 5);
    assert(!oi_maint_may_fire(&m));
    assert(oi_maint_begin_job(&m) == A_UNCAP && m.state == M_UNCAPPING);
    assert(oi_maint_step(&m) == A_SPIT && !oi_maint_may_fire(&m));
    assert(oi_maint_step(&m) == A_MOVE_TO_PAGE && m.state == M_PRINTING && oi_maint_may_fire(&m));
    assert(oi_maint_page_done(&m) == A_NONE && m.state == M_READY);          /* 1st page: no wipe yet */
    assert(oi_maint_begin_job(&m) == A_MOVE_TO_PAGE && oi_maint_may_fire(&m));
    assert(oi_maint_page_done(&m) == A_WIPE && m.state == M_WIPING);        /* 2nd page: wipe due */
    assert(!oi_maint_may_fire(&m) && oi_maint_step(&m) == A_NONE && m.state == M_READY);
    assert(oi_maint_tick(&m, 600) == A_NONE && oi_maint_tick(&m, 600) == A_CAP && m.state == M_CAPPING);
    assert(oi_maint_step(&m) == A_NONE && m.state == M_CAPPED);            /* idle timeout caps the head */
    oi_maint_t z; oi_maint_init(&z, 1000, 0, 0);                            /* no spit, no wipe */
    assert(oi_maint_begin_job(&z) == A_UNCAP && oi_maint_step(&z) == A_MOVE_TO_PAGE && z.state == M_PRINTING);
    assert(oi_maint_begin_job(&z) == A_NONE && z.state == M_FAULT);          /* double start while printing */
    oi_maint_t w; oi_maint_init(&w, 1000, 0, 0);
    assert(oi_maint_page_done(&w) == A_NONE && w.state == M_FAULT);          /* page_done while capped */
    oi_maint_t t; oi_maint_init(&t, 1000, 0, 0); oi_maint_begin_job(&t); oi_maint_step(&t);
    assert(oi_maint_tick(&t, 5000) == A_NONE);                               /* never cap mid-print */
}

/* ---- job controller ---- */
static uint8_t out[64]; static size_t out_n; static int replies;
static void cap_reply(void *c, const uint8_t *f, size_t n) { (void)c; memcpy(out, f, n); out_n = n; replies++; }
static void feed_frame(oi_job_t *j, const uint8_t *f, size_t n) { for (size_t i = 0; i < n; i++) oi_job_feed(j, f[i], cap_reply, 0); }
static size_t hdr(uint8_t *f, uint16_t idx, uint32_t cols, uint16_t bpc, int8_t dir) {
    uint8_t p[13] = { (uint8_t)idx, (uint8_t)(idx >> 8), (uint8_t)cols, (uint8_t)(cols >> 8), (uint8_t)(cols >> 16), (uint8_t)(cols >> 24),
                      (uint8_t)bpc, (uint8_t)(bpc >> 8), (uint8_t)dir, 0x9C, 0x30, 0, 0 };
    return oi_frame_build(f, 1, p, 13);
}
static size_t data(uint8_t *f, uint32_t off, const uint8_t *d, uint16_t n) {
    uint8_t p[64] = { (uint8_t)off, (uint8_t)(off >> 8), (uint8_t)(off >> 16), (uint8_t)(off >> 24) }; memcpy(p + 4, d, n);
    return oi_frame_build(f, 2, p, (uint16_t)(4 + n));
}
static size_t start(uint8_t *f, uint16_t idx) { uint8_t p[2] = { (uint8_t)idx, (uint8_t)(idx >> 8) }; return oi_frame_build(f, 3, p, 2); }
static int is_ack(size_t frame_n, const uint8_t *frame) { (void)frame_n; return out[1] == 4 && out[4] == frame[frame_n - 2] && out[5] == frame[frame_n - 1]; }

static void test_job(void) {
    static uint8_t buf[64]; oi_job_t j; oi_job_init(&j, buf, sizeof buf);
    uint8_t f[128], d[8] = {1, 2, 3, 4, 5, 6, 7, 8};
    size_t n;
    n = start(f, 0); feed_frame(&j, f, n);                                      /* start before header -> NAK */
    assert(out[1] == 5 && !oi_job_take_pass(&j));
    n = hdr(f, 0, 4, 2, 1); feed_frame(&j, f, n); assert(is_ack(n, f));         /* ACK echoes the frame CRC */
    n = data(f, 0, d, 4); feed_frame(&j, f, n); assert(is_ack(n, f));
    n = start(f, 0); feed_frame(&j, f, n); assert(out[1] == 5 && !oi_job_take_pass(&j));   /* incomplete data -> NAK */
    n = data(f, 2, d + 4, 4); feed_frame(&j, f, n); assert(out[1] == 5);        /* gap (offset != received) -> NAK */
    n = data(f, 4, d + 4, 4); feed_frame(&j, f, n); assert(is_ack(n, f));
    n = data(f, 0, d, 4); feed_frame(&j, f, n); assert(is_ack(n, f) && j.dup_acks == 1);   /* duplicate chunk: ACK, no re-copy */
    assert(memcmp(buf, d, 8) == 0);
    n = start(f, 0); feed_frame(&j, f, n); assert(is_ack(n, f) && oi_job_take_pass(&j) == 1);
    n = start(f, 0); feed_frame(&j, f, n); assert(is_ack(n, f) && oi_job_take_pass(&j) == 0);   /* repeated START: idempotent */
    n = start(f, 1); feed_frame(&j, f, n); assert(out[1] == 5);                  /* wrong swath idx -> NAK */
    n = hdr(f, 1, 100000, 2, 1); feed_frame(&j, f, n); assert(out[1] == 5);      /* too big for buffer -> NAK */
    n = hdr(f, 1, 4, 2, 0); feed_frame(&j, f, n); assert(out[1] == 5);           /* dir 0 -> NAK */
    n = hdr(f, 1, 4, 0, 1); feed_frame(&j, f, n); assert(out[1] == 5);           /* bytes_per_col 0 -> NAK */
    n = hdr(f, 1, 0xFFFFFFFFu, 0xFFFF, 1); feed_frame(&j, f, n); assert(out[1] == 5);   /* 64-bit size product, no overflow */
    replies = 0; uint8_t bad[8] = {0xA5, 3, 2, 0, 0, 0, 0, 0}; feed_frame(&j, bad, 8);
    assert(replies == 0);                                                        /* CRC-invalid frame: silence, host retransmits */
}

int main(void) {
    test_matrix(); test_motion(); test_feed(); test_maint(); test_job();
    puts("module tests OK");
    return 0;
}
