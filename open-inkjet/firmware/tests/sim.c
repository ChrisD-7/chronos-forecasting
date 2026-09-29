/* Printer simulator (POSIX test harness, not device code).
 * Reads protocol frames on stdin, writes ACK/NAK frames on stdout, and on EOF writes the printed page as a
 * PBM (P4) to argv[1]. Runs the real oi_job / oi_sched / oi_head_matrix / oi_motion code against a simulated
 * carriage (1-count steps, ink-flight lag), paper feed (fractional steps) and matrix head (address/primitive
 * pulses decoded back to nozzles through the inverse of the nozzle map).
 * usage: sim out.pbm [lag_counts] [bidir_offset_counts] */
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../core/oi_job.h"
#include "../core/oi_sched.h"
#include "../core/oi_head_matrix.h"
#include "../core/oi_motion.h"

#define NOZ 300
#define NADDR 22
#define NPRIM 14
#define MAXCOLS 2600
#define MAXSWATH 200
#define VDPI_DIV 2                    /* 300 vdpi on a 600 npi head: even nozzles only */
#define COUNTS_PER_DOT 2
#define NOMINAL_ORIGIN 400            /* column 0 lands here (counts); left margin holds the accel ramp */
#define MARGIN 400

static uint16_t nozzle_map[NOZ];      /* PLACEHOLDER map (not the real HP45 wiring) */
static int16_t inv[NADDR][NPRIM];
static uint8_t canvas[MAXSWATH * 150][MAXCOLS / 8 + 1];
static int rows_used, cols_used;
static long errors_odd_nozzle, errors_oob;

static int32_t car_pos; static int car_dir, lag;
static uint64_t paper_nm, total_steps;   /* paper position, derived from cumulative motor steps */
static int cur_addr; static uint32_t cur_prim;

static void hal_addr(void *hw, uint8_t a) { (void)hw; cur_addr = a; }
static void hal_prim(void *hw, uint32_t m) { (void)hw; cur_prim = m; }
static void hal_idle(void *hw) { (void)hw; cur_prim = 0; }
static void hal_pulse(void *hw) {
    (void)hw;
    int32_t landing = car_pos + (car_dir > 0 ? lag : -lag);           /* drop is carried with the carriage */
    int32_t rel = landing - NOMINAL_ORIGIN;
    int col = (rel >= 0 ? rel + COUNTS_PER_DOT / 2 : rel - COUNTS_PER_DOT / 2) / COUNTS_PER_DOT;
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

static const oi_matrix_hal_t HAL = { hal_addr, hal_prim, hal_pulse, hal_idle, 0 };
static oi_matrix_head_t mhead;
static uint8_t swath_buf[MAXCOLS * 38];
static oi_job_t job;
static oi_sched_t sched;
static oi_feed_t feed;
static int passes, plan_errors;

static void reply(void *ctx, const uint8_t *f, size_t n) { (void)ctx; fwrite(f, 1, n, stdout); fflush(stdout); }

static void run_pass(int bidir_offset) {
    memset(&sched, 0, sizeof sched);
    sched.head = &mhead.head; sched.columns = swath_buf; sched.n_columns = job.columns;
    sched.bytes_per_col = job.bytes_per_col; sched.counts_per_dot = COUNTS_PER_DOT;
    sched.origin_counts = NOMINAL_ORIGIN - lag;           /* forward calibration removes the ink-flight lag */
    sched.bidir_offset_counts = bidir_offset;
    if (oi_sched_start(&sched, job.dir) != OI_OK) { plan_errors++; return; }
    int32_t x0 = job.dir > 0 ? 0 : NOMINAL_ORIGIN + (int32_t)job.columns * COUNTS_PER_DOT + MARGIN;
    int32_t x1 = job.dir > 0 ? NOMINAL_ORIGIN + (int32_t)job.columns * COUNTS_PER_DOT + MARGIN : 0;
    /* the accel ramp must fit inside the margin at the head-limited cruise speed */
    oi_traj_t t; uint32_t vmax = oi_max_cruise_for_head(18000, COUNTS_PER_DOT) / 4;   /* 25% of head limit */
    if (oi_traj_plan(&t, (uint32_t)(x1 > x0 ? x1 - x0 : x0 - x1), vmax, 300000) || t.accel_counts > MARGIN) plan_errors++;
    car_dir = job.dir;
    for (car_pos = x0; car_pos != x1; car_pos += car_dir) oi_sched_on_position(&sched, car_pos);
    oi_sched_on_position(&sched, x1);
    passes++;
    total_steps += oi_feed_steps(&feed, job.feed_um);
    paper_nm = total_steps * 1000000000ull / feed.steps_per_mm_x1000;      /* nm = steps * 1e9 / (steps/mm x1000) */
}

int main(int argc, char **argv) {
    if (argc < 2) return 2;
    lag = argc > 2 ? atoi(argv[2]) : 0;
    int bidir = argc > 3 ? atoi(argv[3]) : 0;
    for (int n = 0; n < NOZ; n++) nozzle_map[n] = (uint16_t)(((n % NADDR) << 8) | (n / NADDR));
    memset(inv, -1, sizeof inv);
    for (int n = 0; n < NOZ; n++) inv[nozzle_map[n] >> 8][nozzle_map[n] & 0xFF] = (int16_t)n;
    if (oi_matrix_head_init(&mhead, &HAL, nozzle_map, NOZ, NADDR, NPRIM)) return 3;
    oi_feed_init(&feed, 157480);                          /* deliberately fractional steps/mm */
    oi_job_init(&job, swath_buf, sizeof swath_buf);
    struct pollfd pf = { 0, POLLIN, 0 };
    for (;;) {
        int r = poll(&pf, 1, 50);
        if (r == 0) { oi_parser_reset(&job.parser); continue; }        /* inter-frame silence = transport timeout */
        uint8_t chunk[4096]; ssize_t n = read(0, chunk, sizeof chunk);
        if (n <= 0) break;
        for (ssize_t i = 0; i < n; i++) {
            oi_job_feed(&job, chunk[i], reply, 0);
            if (oi_job_take_pass(&job)) run_pass(bidir);
        }
    }
    FILE *f = fopen(argv[1], "wb");
    if (!f) return 4;
    fprintf(f, "P4\n%d %d\n", cols_used, rows_used);
    int stride = (cols_used + 7) / 8;
    for (int y = 0; y < rows_used; y++) fwrite(canvas[y], 1, (size_t)stride, f);
    fclose(f);
    fprintf(stderr, "passes=%d cols=%d rows=%d naks=%u dups=%u odd=%ld oob=%ld plan_err=%d crc_err=%u\n", passes, cols_used,
            rows_used, job.naks, job.dup_acks, errors_odd_nozzle, errors_oob, plan_errors, job.parser.crc_errors);
    return (errors_odd_nozzle || errors_oob || plan_errors) ? 5 : 0;
}
