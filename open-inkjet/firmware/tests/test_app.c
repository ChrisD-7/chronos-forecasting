/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* oi_app tests with a scripted fake HAL (no pipes, no poll). Covers action order, BUSY from an interrupt, run-in margin,
 * missed columns, stall watchdog, positioning moves, aborted-job capping, speed clamp, paper accounting, config/range errors. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#define assert(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)
#include "../core/oi_app.h"

typedef struct {
    int32_t pos; int dir; int step_per_wait; int stall;
    char ev[512]; size_t nev;
    uint32_t max_speed; uint64_t fed;
    uint8_t reply_types[64]; int n_reply; uint16_t err_codes[8]; int n_err;
    int fires; int fire_hook_calls;
    int32_t stops[16]; int n_stops; int home_calls, home_result;
    void (*wait_hook)(void *w);               /* called on every wait tick (used to emulate an ISR) */
    oi_app_t *app; int hook_fired;
} World;
static World W;

static void ev(char c) { W.ev[W.nev++] = c; W.ev[W.nev] = 0; }
static int32_t h_pos(void *c) { (void)c; return W.pos; }
static void h_drive(void *c, int dir, uint32_t v) { (void)c; W.dir = dir; if (dir == 0) { ev('s'); if (W.n_stops < 16) W.stops[W.n_stops++] = W.pos; } else { ev(dir > 0 ? '>' : '<'); if (v > W.max_speed) W.max_speed = v; } }
static void h_wait(void *c) { (void)c; if (!W.stall) W.pos += W.dir * W.step_per_wait; if (W.wait_hook) W.wait_hook(&W); }
static void h_feed(void *c, uint64_t s) { (void)c; W.fed += s; ev('F'); }
static void h_maint(void *c, oi_maint_action_t a) {
    (void)c;
    switch (a) { case A_UNCAP: ev('U'); break; case A_SPIT: ev('S'); break; case A_MOVE_TO_PAGE: ev('M'); break;
                 case A_WIPE: ev('W'); break; case A_CAP: ev('C'); break; default: ev('?'); }
}
static void h_reply(void *c, const uint8_t *f, size_t n) {
    (void)c; (void)n;
    if (W.n_reply < 64) W.reply_types[W.n_reply++] = f[1];
    if (f[1] == 8) W.err_codes[W.n_err++] = (uint16_t)(f[4] | (f[5] << 8));
}
static int h_home(void *c) { (void)c; W.home_calls++; if (W.home_result == 0) W.pos = 0; return W.home_result; }
static void h_fire(oi_head_t *h, const uint8_t *bits) { (void)h; (void)bits; W.fires++; }

static uint8_t swbuf[2048];
static oi_head_t head8 = { "fake8", 8, h_fire, 0 };
static oi_head_t head64 = { "fake64", 64, h_fire, 0 };

static oi_app_cfg_t base_cfg(void) {
    oi_app_cfg_t c; memset(&c, 0, sizeof c);
    c.counts_per_dot = 2; c.origin_counts = 200; c.bidir_offset_counts = 0; c.left_stop_counts = 0; c.margin_counts = 300;
    c.v_max = 9000; c.accel = 300000; c.max_fire_hz = 18000; c.steps_per_mm_x1000 = 157480;
    c.idle_cap_ms = 1000; c.wipe_every_pages = 1; c.spit_droplets = 3; c.stall_ticks = 50; c.page_timeout_ms = 10000;
    return c;
}
static oi_app_t app;
static void setup(const oi_app_cfg_t *cfg, oi_head_t *head) {
    static oi_hal_t hal = { 0, h_pos, h_drive, h_wait, h_feed, h_maint, h_reply, 0 };
    memset(&W, 0, sizeof W); W.step_per_wait = 1; W.app = &app;
    assert(oi_app_init(&app, &hal, cfg, head, swbuf, sizeof swbuf) == 0);
}

static void rx(const uint8_t *f, size_t n) { for (size_t i = 0; i < n; i++) oi_app_rx(&app, f[i]); }
static void send_swath(uint16_t idx, uint32_t cols, int dir) {
    uint8_t f[1100], pl[13] = { (uint8_t)idx, (uint8_t)(idx >> 8), (uint8_t)cols, (uint8_t)(cols >> 8), (uint8_t)(cols >> 16), (uint8_t)(cols >> 24),
                               1, 0, (uint8_t)dir, 0x9C, 0x31, 0, 0 };                    /* feed_um = 0x319C = 12700 */
    size_t n = oi_frame_build(f, 1, pl, 13); rx(f, n);
    uint8_t dp[1040]; memset(dp, 0xFF, sizeof dp); dp[0] = dp[1] = dp[2] = dp[3] = 0;       /* offset 0, data 0xFF */
    n = oi_frame_build(f, 2, dp, (uint16_t)(4 + cols)); rx(f, n);
    uint8_t sp[2] = { (uint8_t)idx, (uint8_t)(idx >> 8) };
    n = oi_frame_build(f, 3, sp, 2); rx(f, n);
}
static void send_page_end(void) { uint8_t f[8]; size_t n = oi_frame_build(f, 7, 0, 0); rx(f, n); }
static int has_reply(uint8_t type) { for (int i = 0; i < W.n_reply; i++) if (W.reply_types[i] == type) return 1; return 0; }

static void test_action_order_two_pages(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    send_swath(0, 10, +1); send_swath(1, 10, -1); send_page_end();
    /* uncap, spit, move; R pass (stops at its last column) feed; reposition right, L pass feed; wipe */
    assert(strcmp(W.ev, "USM>sF>s<sFW") == 0);
    send_swath(0, 10, +1); send_swath(1, 10, -1); send_page_end();          /* page 2: swath indices restart, no re-uncap */
    assert(strcmp(W.ev, "USM>sF>s<sFW" "M<s>sF>s<sFW") == 0);
    assert(app.passes == 4 && app.pass_errors == 0 && W.fires == 4 * 10);
    assert(W.max_speed <= 36000);
}

static void isr_hook(void *w) {                                              /* an ISR receiving a new HDR mid-pass */
    World *x = w;
    if (x->hook_fired) return;
    x->hook_fired = 1;
    uint8_t f[32], pl[13] = { 5, 0, 10, 0, 0, 0, 1, 0, 1, 0, 0, 0, 0 };
    size_t n = oi_frame_build(f, 1, pl, 13);
    for (size_t i = 0; i < n; i++) oi_job_feed(&x->app->job, f[i], h_reply, 0);
}
static void test_busy_from_isr(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    W.wait_hook = isr_hook;
    send_swath(0, 10, +1);
    assert(W.hook_fired && has_reply(6));                                    /* BUSY, not ACK, and the printing pass was undisturbed */
    assert(app.passes == 1 && W.fires == 10 && app.job.idx == 0);
}

static void feed_bytes_only(const uint8_t *f, size_t n) { for (size_t i = 0; i < n; i++) oi_app_feed(&app, f[i]); }

static void test_split_feed_service_answers_busy_while_pass_pending(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    uint8_t f[1100], pl[13] = { 0, 0, 10, 0, 0, 0, 1, 0, 1, 0x9C, 0x31, 0, 0 };
    feed_bytes_only(f, oi_frame_build(f, 1, pl, 13));                        /* HDR */
    uint8_t dp[14]; memset(dp, 0xFF, sizeof dp); dp[0] = dp[1] = dp[2] = dp[3] = 0;
    feed_bytes_only(f, oi_frame_build(f, 2, dp, 14));                        /* DATA */
    uint8_t sp[2] = { 0, 0 };
    feed_bytes_only(f, oi_frame_build(f, 3, sp, 2));                         /* START: ACKed, pass NOT run yet */
    assert(app.passes == 0 && W.fires == 0 && W.reply_types[W.n_reply - 1] == 4);
    uint8_t pl2[13] = { 1, 0, 10, 0, 0, 0, 1, 0, 1, 0x9C, 0x31, 0, 0 };
    feed_bytes_only(f, oi_frame_build(f, 1, pl2, 13));                       /* next HDR arrives while the pass is pending */
    assert(W.reply_types[W.n_reply - 1] == 6);                               /* BUSY, immediately, without blocking */
    assert(oi_app_service(&app) == 1 && app.passes == 1 && W.fires == 10);   /* machine context runs it */
    assert(oi_app_service(&app) == 0);                                       /* nothing more to do */
    feed_bytes_only(f, oi_frame_build(f, 1, pl2, 13));                       /* buffer free again: ACK */
    assert(W.reply_types[W.n_reply - 1] == 4);
    feed_bytes_only(f, oi_frame_build(f, 7, 0, 0));                          /* PAGE_END is accepted only after a pass finished */
    assert(W.reply_types[W.n_reply - 1] == 4 && oi_app_service(&app) == 1 && !app.page_active);
}

static void test_ramp_must_fit_both_run_ins(void) {
    oi_app_cfg_t c = base_cfg(); c.accel = 50000;                            /* ramp 810 > margin 300 */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.fires == 0 && has_reply(8) && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.origin_counts = 100; c.margin_counts = 2100; c.accel = 20000;   /* ramp 2025 fits margin but not the lead (100) */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.fires == 0 && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.origin_counts = 2100; c.margin_counts = 100; c.accel = 20000;   /* fits the lead but not the tail */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.bidir_offset_counts = 100;                                      /* offset eats 100 of the 200 lead: 100 < ramp 135 */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.bidir_offset_counts = -100; c.margin_counts = 200;             /* negative offset eats the tail: 200 - 100 < 135 */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.origin_counts = 1000; c.margin_counts = 200; c.bidir_offset_counts = 100;   /* lead 900 is plenty; ONLY the tail (200 - 100) is short */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 0 && W.err_codes[0] == OI_DEVERR_RAMP);
    c = base_cfg(); c.bidir_offset_counts = 60;                                       /* 140 >= 135 on both sides: fits */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 1 && app.pass_errors == 0);
    c = base_cfg(); c.origin_counts = 810; c.margin_counts = 810; c.accel = 50000;    /* exactly fits both (ramp 810) */
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.passes == 1 && app.pass_errors == 0);
}

static void test_missed_columns_reported_paper_still_fed(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    W.step_per_wait = 5;                                                     /* encoder skips: > 1 dot per poll */
    send_swath(0, 40, +1);
    assert(has_reply(8) && W.err_codes[0] == OI_DEVERR_MISSED && app.sched.missed > 0);
    assert(strchr(W.ev, 'F') != 0 && app.passes == 1);                       /* paper advanced so later swaths stay aligned */
}

static void test_stall_watchdog(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    W.stall = 1;
    send_swath(0, 10, +1);                                                   /* pos never changes: must not hang */
    assert(has_reply(8) && W.err_codes[0] == OI_DEVERR_STALL && app.passes == 0);
    assert(W.ev[W.nev - 1] == 's' && strchr(W.ev, 'F') == 0);                /* carriage stopped, no feed after a stall */
    c = base_cfg(); setup(&c, &head8);
    W.step_per_wait = -1;                                                    /* encoder moves the wrong way */
    send_swath(0, 10, +1);
    assert(W.err_codes[0] == OI_DEVERR_STALL);
}

static void test_positioning_before_pass_when_column_counts_differ(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    send_swath(0, 10, +1);                                                   /* ends at 200 + 20 + 300 = 520 */
    send_swath(1, 500, -1);                                                  /* leftward pass starts at 200 + 1000 + 300 = 1500 */
    assert(app.pass_errors == 0 && app.passes == 2);
    assert(W.fires == 10 + 500);                                             /* ALL 500 columns fired (used to lose 289) */
    assert(strstr(W.ev, "USM>sF>s<sF") != 0);                                /* positioning move (> to 1500) before the leftward pass */
}

static void test_aborted_job_is_capped(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    send_swath(0, 10, +1);                                                   /* no PAGE_END ever arrives */
    oi_app_idle(&app, 9999);
    assert(app.page_active && strchr(W.ev, 'C') == 0);
    oi_app_idle(&app, 1);                                                    /* page timeout reached: page ends (wipe), timer restarts */
    assert(!app.page_active && app.maint.state == M_READY && strchr(W.ev, 'C') == 0);
    oi_app_idle(&app, 998);                                                  /* 1 + 998 = 999 ms idle since the page ended: not yet */
    assert(strchr(W.ev, 'C') == 0);
    oi_app_idle(&app, 1);                                                    /* 1000 ms = idle_cap_ms: head capped */
    assert(strchr(W.ev, 'C') != 0 && app.maint.state == M_CAPPED);
    setup(&c, &head8);                                                       /* any received byte restarts the page-idle timer */
    send_swath(0, 10, +1); oi_app_idle(&app, 9000);
    { uint8_t f[8]; size_t n = oi_frame_build(f, 7, 0, 0); (void)n; oi_app_rx(&app, f[0]); }   /* one stray byte of a new frame */
    oi_app_idle(&app, 9000);
    assert(app.page_active);                                                 /* 9000 + 9000 ms in total, but the timer restarted */
    oi_app_cfg_t c0 = base_cfg(); c0.page_timeout_ms = 0; setup(&c0, &head8);
    send_swath(0, 10, +1); oi_app_idle(&app, 100000);
    assert(app.page_active && app.maint.state == M_PRINTING);                 /* 0 disables the page timeout */
}

static void test_fault_is_reported_and_recovers(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    app.maint.state = M_FAULT;                                               /* white-box: the FSM cannot reach FAULT via the app flow */
    send_swath(0, 10, +1);
    assert(app.faults == 1 && W.err_codes[0] == OI_DEVERR_FAULT && W.fires == 0);
    assert(app.maint.state == M_CAPPED && !app.page_active);                 /* recovered: head position unknown -> treat as capped */
    send_swath(0, 10, +1);                                                   /* next attempt uncaps and prints */
    assert(strchr(W.ev, 'U') != 0 && W.fires == 10 && app.passes == 1);
}

static void test_braking_starts_at_last_column_not_at_run_out_end(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    send_swath(0, 10, +1);                                                   /* last column index 9 at 200 + 9*2 = 218; x1 would be 520 */
    assert(W.n_stops == 1 && W.stops[0] == 218);
    send_swath(1, 10, -1);                                                   /* positioning stop at x0 = 520, then the pass stops at column 0 = 200 */
    assert(W.n_stops == 3 && W.stops[1] == 520 && W.stops[2] == 200);
}

static void test_homing_once_and_failure_blocks_printing(void) {
    static oi_hal_t hal = { 0, h_pos, h_drive, h_wait, h_feed, h_maint, h_reply, h_home };
    oi_app_cfg_t c = base_cfg(); c.left_stop_counts = 40;                    /* room to brake a vmax/2 positioning move (34 counts) before the switch */
    memset(&W, 0, sizeof W); W.step_per_wait = 1; W.pos = 777;               /* power-up position is arbitrary */
    assert(oi_app_init(&app, &hal, &c, &head8, swbuf, sizeof swbuf) == 0);
    send_swath(0, 10, +1); send_swath(1, 10, -1); send_page_end();
    send_swath(0, 10, +1); send_page_end();
    assert(W.home_calls == 1 && app.homed && app.pass_errors == 0);          /* homed before the first pass only */
    memset(&W, 0, sizeof W); W.step_per_wait = 1; W.home_result = -1;        /* switch never found */
    assert(oi_app_init(&app, &hal, &c, &head8, swbuf, sizeof swbuf) == 0);
    send_swath(0, 10, +1);
    assert(W.err_codes[0] == OI_DEVERR_HOME && app.passes == 0 && W.fires == 0 && !app.homed);
    W.home_result = 0; send_swath(0, 10, +1);                                 /* retry after the fault is cleared */
    assert(app.homed && W.fires == 10);
}

static void test_left_stop_must_leave_room_to_brake_before_the_home_switch(void) {
    static oi_hal_t hal = { 0, h_pos, h_drive, h_wait, h_feed, h_maint, h_reply, h_home };
    oi_app_cfg_t c = base_cfg(); c.left_stop_counts = 20;                    /* positioning ramp at vmax/2 is 34 counts > 20 */
    memset(&W, 0, sizeof W); W.step_per_wait = 1;
    assert(oi_app_init(&app, &hal, &c, &head8, swbuf, sizeof swbuf) == 0);
    send_swath(0, 10, +1);
    assert(W.err_codes[0] == OI_DEVERR_RAMP && app.passes == 0 && W.fires == 0);
    c.left_stop_counts = 34;                                                 /* exactly enough */
    memset(&W, 0, sizeof W); W.step_per_wait = 1;
    assert(oi_app_init(&app, &hal, &c, &head8, swbuf, sizeof swbuf) == 0);
    send_swath(0, 10, +1);
    assert(app.passes == 1 && app.pass_errors == 0);
}

static void test_speed_clamped_to_head_limit(void) {
    oi_app_cfg_t c = base_cfg(); c.v_max = 1000000000u; c.accel = 3000000; c.origin_counts = 300; c.margin_counts = 300;
    setup(&c, &head8); send_swath(0, 10, +1);
    assert(app.pass_errors == 0 && W.max_speed == 36000);                    /* 18000 Hz * 2 counts/dot */
}

static void test_paper_accounting(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head8);
    send_swath(0, 10, +1); send_swath(1, 10, -1);
    assert(app.paper_steps == W.fed && app.paper_steps == 3999);             /* 2 x 12.7 mm x 157.48 steps/mm = 3999.99 -> carry keeps 3999 */
}

static void test_config_and_range_errors(void) {
    oi_app_cfg_t c = base_cfg(); setup(&c, &head64);                          /* 64 nozzles need 8 bytes per column, job sends 1 */
    send_swath(0, 10, +1);
    assert(W.err_codes[0] == OI_DEVERR_CONFIG && app.passes == 0 && W.fires == 0);
    c = base_cfg(); c.counts_per_dot = 1 << 30; setup(&c, &head8);            /* 5 * 2^30 overflows int32 */
    send_swath(0, 5, +1);
    assert(W.err_codes[0] == OI_DEVERR_RANGE && app.passes == 0);
    oi_app_cfg_t bad = base_cfg(); bad.stall_ticks = 0;
    static oi_hal_t hal = { 0, h_pos, h_drive, h_wait, h_feed, h_maint, h_reply, 0 };
    assert(oi_app_init(&app, &hal, &bad, &head8, swbuf, sizeof swbuf) == -1);
    bad = base_cfg(); bad.steps_per_mm_x1000 = 0;
    assert(oi_app_init(&app, &hal, &bad, &head8, swbuf, sizeof swbuf) == -1);
}

int main(void) {
    test_action_order_two_pages(); test_busy_from_isr(); test_ramp_must_fit_both_run_ins();
    test_missed_columns_reported_paper_still_fed(); test_stall_watchdog();
    test_positioning_before_pass_when_column_counts_differ(); test_aborted_job_is_capped();
    test_speed_clamped_to_head_limit(); test_paper_accounting(); test_config_and_range_errors();
    test_fault_is_reported_and_recovers(); test_split_feed_service_answers_busy_while_pass_pending();
    test_braking_starts_at_last_column_not_at_run_out_end(); test_homing_once_and_failure_blocks_printing();
    test_left_stop_must_leave_room_to_brake_before_the_home_switch();
    puts("app tests OK");
    return 0;
}
