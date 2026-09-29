/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Printer simulator (POSIX test harness, not device code).
 * Reads protocol frames on stdin, writes ACK/NAK/BUSY frames on stdout, and at EOF writes the printed page as a
 * PBM (P4) to argv[1]. Runs the REAL oi_app (job controller, maintenance FSM, motion planner, fire scheduler,
 * matrix head driver) against a simulated HAL: 1-count carriage steps with ink-flight lag, paper feed with
 * fractional steps, a cap that blocks the head, and a matrix head whose address/primitive pulses are decoded back to
 * nozzles through the inverse of the nozzle map (a PLACEHOLDER map, not the real HP45 wiring).
 * usage: sim out.pbm [lag_counts] [bidir_offset_counts] */
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../core/oi_app.h"
#include "../core/oi_head_matrix.h"

#define NOZ 300
#define NADDR 22
#define NPRIM 14
#define MAXCOLS 2600
#define MAXSWATH 200
#define VDPI_DIV 2                    /* 300 vdpi on a 600 npi head: even nozzles only */
#define COUNTS_PER_DOT 2
#define NOMINAL_ORIGIN 400            /* column 0 lands here (counts); left margin holds the accel ramp */
#define MARGIN 400

static uint16_t nozzle_map[NOZ];
static int16_t inv[NADDR][NPRIM];
static uint8_t canvas[MAXSWATH * 150][MAXCOLS / 8 + 1];
static int rows_used, cols_used;
static long errors_odd_nozzle, errors_oob, fired_while_capped, fired_during_spit;

/* simulated machine state */
static int32_t car_pos; static int car_dir, lag;
static uint64_t total_steps;
static int cur_addr; static uint32_t cur_prim;
static int capped = 1, spitting;                     /* head starts parked in the cap */
static long n_uncap, n_cap, n_spit, n_wipe, n_move;
static uint32_t max_speed_cmd;

static void hal_addr(void *hw, uint8_t a) { (void)hw; cur_addr = a; }
static void hal_prim(void *hw, uint32_t m) { (void)hw; cur_prim = m; }
static void hal_idle(void *hw) { (void)hw; cur_prim = 0; }
static void hal_pulse(void *hw) {
    (void)hw;
    if (spitting) { fired_during_spit++; return; }        /* spit droplets land in the cap, not on paper */
    if (capped) { fired_while_capped++; return; }         /* firing into a closed cap must never happen while printing */
    int32_t landing = car_pos + (car_dir > 0 ? lag : -lag);   /* drop is carried with the carriage */
    int32_t rel = landing - NOMINAL_ORIGIN;
    int col = (rel >= 0 ? rel + COUNTS_PER_DOT / 2 : rel - COUNTS_PER_DOT / 2) / COUNTS_PER_DOT;
    uint64_t paper_nm = total_steps * 1000000000ull / 157480ull;      /* steps_per_mm_x1000 = 157480 */
    for (int p = 0; p < NPRIM; p++) if (cur_prim & (1u << p)) {
        int n = inv[cur_addr][p];
        if (n < 0) { errors_oob++; continue; }
        if (n % VDPI_DIV) { errors_odd_nozzle++; continue; }
        long units600 = (long)(paper_nm * 600ull / 25400000ull) + n;      /* 1/600 inch units */
        int row = (int)((units600 + VDPI_DIV / 2) / VDPI_DIV);
        if (row < 0 || row >= MAXSWATH * 150 || col < 0 || col >= MAXCOLS) { errors_oob++; continue; }
        canvas[row][col >> 3] |= (uint8_t)(0x80 >> (col & 7));
        if (row + 1 > rows_used) rows_used = row + 1;
        if (col + 1 > cols_used) cols_used = col + 1;
    }
}
static const oi_matrix_hal_t MHAL = { hal_addr, hal_prim, hal_pulse, hal_idle, 0 };
static oi_matrix_head_t mhead;

/* HAL for oi_app */
static int32_t h_pos(void *c) { (void)c; return car_pos; }
static void h_drive(void *c, int dir, uint32_t v) { (void)c; car_dir = dir; if (v > max_speed_cmd) max_speed_cmd = v; }
static void h_wait(void *c) { (void)c; car_pos += car_dir; }
static void h_feed(void *c, uint64_t steps) { (void)c; total_steps += steps; }
static void h_maint(void *c, oi_maint_action_t a) {
    (void)c;
    switch (a) {
    case A_UNCAP: capped = 0; n_uncap++; break;
    case A_CAP: capped = 1; n_cap++; break;
    case A_SPIT: spitting = 1; { uint8_t all[38]; memset(all, 0xFF, sizeof all); all[37] = 0x0F; mhead.head.fire_column(&mhead.head, all); } spitting = 0; n_spit++; break;
    case A_WIPE: n_wipe++; break;
    case A_MOVE_TO_PAGE:                            /* start of a page = a fresh sheet; keep only the LAST page's output */
        n_move++; total_steps = 0;
        if (n_move > 1) { memset(canvas, 0, sizeof canvas); rows_used = cols_used = 0; }
        break;
    default: break;
    }
}
static void h_reply(void *c, const uint8_t *f, size_t n) { (void)c; fwrite(f, 1, n, stdout); fflush(stdout); }

static uint8_t swath_buf[MAXCOLS * 38];
static oi_app_t app;

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    lag = argc > 2 ? atoi(argv[2]) : 0;
    int bidir = argc > 3 ? atoi(argv[3]) : 0;
    for (int n = 0; n < NOZ; n++) nozzle_map[n] = (uint16_t)(((n % NADDR) << 8) | (n / NADDR));
    memset(inv, -1, sizeof inv);
    for (int n = 0; n < NOZ; n++) inv[nozzle_map[n] >> 8][nozzle_map[n] & 0xFF] = (int16_t)n;
    if (oi_matrix_head_init(&mhead, &MHAL, nozzle_map, NOZ, NADDR, NPRIM)) return 3;
    oi_hal_t hal = { 0, h_pos, h_drive, h_wait, h_feed, h_maint, h_reply };
    oi_app_cfg_t cfg = {
        .counts_per_dot = COUNTS_PER_DOT, .origin_counts = NOMINAL_ORIGIN - lag, .bidir_offset_counts = bidir,
        .left_stop_counts = 0, .margin_counts = MARGIN, .v_max = oi_max_cruise_for_head(18000, COUNTS_PER_DOT) / 4,
        .accel = 300000, .max_fire_hz = 18000, .steps_per_mm_x1000 = 157480,    /* deliberately fractional */
        .idle_cap_ms = 2000, .wipe_every_pages = 1, .spit_droplets = 5 };
    if (oi_app_init(&app, &hal, &cfg, &mhead.head, swath_buf, sizeof swath_buf)) return 3;
    struct pollfd pf = { 0, POLLIN, 0 };
    for (;;) {
        int r = poll(&pf, 1, 50);
        if (r == 0) { oi_app_idle(&app, 50); continue; }              /* silence: parser reset + idle timer */
        uint8_t chunk[4096]; ssize_t n = read(0, chunk, sizeof chunk);
        if (n <= 0) break;
        for (ssize_t i = 0; i < n; i++) oi_app_rx(&app, chunk[i]);
    }
    oi_app_idle(&app, 5000);                                          /* long idle after the job: head must be capped */
    FILE *f = fopen(argv[1], "wb");
    if (!f) return 4;
    fprintf(f, "P4\n%d %d\n", cols_used, rows_used);
    int stride = (cols_used + 7) / 8;
    for (int y = 0; y < rows_used; y++) fwrite(canvas[y], 1, (size_t)stride, f);
    fclose(f);
    fprintf(stderr, "passes=%u cols=%d rows=%d naks=%u dups=%u busys=%u odd=%ld oob=%ld pass_err=%u faults=%u crc_err=%u "
            "uncap=%ld cap=%ld spit=%ld wipe=%ld capped_fire=%ld final_capped=%d max_speed=%u\n",
            app.passes, cols_used, rows_used, app.job.naks, app.job.dup_acks, app.job.busys, errors_odd_nozzle, errors_oob,
            app.pass_errors, app.faults, app.job.parser.crc_errors, n_uncap, n_cap, n_spit, n_wipe, fired_while_capped, capped,
            max_speed_cmd);
    return (errors_odd_nozzle || errors_oob || app.pass_errors || app.faults || fired_while_capped) ? 5 : 0;
}
