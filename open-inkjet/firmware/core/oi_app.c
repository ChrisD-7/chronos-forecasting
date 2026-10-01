/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
#include "oi_app.h"
#include <string.h>

#define T_ERROR 8

static void hal_reply(void *c, const uint8_t *f, size_t n) { oi_app_t *a = c; a->hal.reply(a->hal.ctx, f, n); }

int oi_app_init(oi_app_t *a, const oi_hal_t *hal, const oi_app_cfg_t *cfg, oi_head_t *head, uint8_t *buf, size_t cap) {
    if (!hal || !cfg || !head || !buf || !hal->encoder_pos || !hal->carriage_drive || !hal->wait_encoder_change ||
        !hal->feed_steps || !hal->maint || !hal->reply) return -1;
    if (cfg->counts_per_dot <= 0 || cfg->v_max == 0 || cfg->accel == 0 || cfg->margin_counts <= 0 || cfg->stall_ticks == 0)
        return -1;
    memset(a, 0, sizeof *a);
    a->hal = *hal; a->cfg = *cfg; a->head = head;
    if (oi_feed_init(&a->feed, cfg->steps_per_mm_x1000)) return -1;
    oi_job_init(&a->job, buf, cap);
    oi_maint_init(&a->maint, cfg->idle_cap_ms, cfg->wipe_every_pages, cfg->spit_droplets);
    return 0;
}

/* Tell the host a pass did not print correctly. START was already ACKed, so this is the only way it can find out. */
static void send_error(oi_app_t *a, uint16_t code) {
    uint8_t pl[4] = { (uint8_t)code, (uint8_t)(code >> 8), (uint8_t)a->job.idx, (uint8_t)(a->job.idx >> 8) }, f[16];
    a->pass_errors++; a->last_error = code;
    a->hal.reply(a->hal.ctx, f, oi_frame_build(f, T_ERROR, pl, 4));
}

/* Perform maintenance actions until the FSM has nothing more to do (ends in PRINTING when uncapping/positioning). */
static void maint_run(oi_app_t *a, oi_maint_action_t act) {
    for (int guard = 0; guard < 8 && act != A_NONE && act != A_BUSY && a->maint.state != M_FAULT; guard++) {
        a->hal.maint(a->hal.ctx, act);
        act = oi_maint_step(&a->maint);
    }
}

/* Drive toward target (dir = +1/-1) until reached. Feeds every position to the scheduler when sched != NULL.
 * Returns 0 when reached, -1 if the carriage made no progress in the requested direction for stall_ticks polls
 * (carriage is stopped before returning). */
static int move_until(oi_app_t *a, int dir, int32_t target, uint32_t speed, oi_sched_t *sched) {
    int32_t last = a->hal.encoder_pos(a->hal.ctx);
    uint32_t stalled = 0;
    a->hal.carriage_drive(a->hal.ctx, dir, speed);
    for (;;) {
        int32_t pos = a->hal.encoder_pos(a->hal.ctx);
        if (sched) oi_sched_on_position(sched, pos);
        if (dir > 0 ? pos >= target : pos <= target) break;
        if (dir > 0 ? pos > last : pos < last) { stalled = 0; last = pos; }
        else if (++stalled > a->cfg.stall_ticks) { a->hal.carriage_drive(a->hal.ctx, 0, 0); return -1; }
        a->hal.wait_encoder_change(a->hal.ctx);
    }
    a->hal.carriage_drive(a->hal.ctx, 0, 0);
    return 0;
}

static void run_pass(oi_app_t *a) {
    oi_job_t *j = &a->job;
    if (!a->page_active) {                                           /* first swath of a page: uncap, spit, park at page */
        a->page_active = 1;
        oi_maint_action_t act = oi_maint_begin_job(&a->maint);
        if (act == A_BUSY) { a->page_active = 0; send_error(a, OI_DEVERR_FAULT); return; }   /* cannot happen synchronously */
        maint_run(a, act);
    }
    if (!a->homed && a->hal.home) {                                  /* unknown carriage position after power-up: find the switch first */
        if (a->hal.home(a->hal.ctx) != 0) { send_error(a, OI_DEVERR_HOME); return; }
        a->homed = 1;
    }
    if (!oi_maint_may_fire(&a->maint)) {                             /* never fire while capped/faulted */
        a->faults++; send_error(a, OI_DEVERR_FAULT);
        oi_maint_clear_fault(&a->maint); a->page_active = 0;         /* head position unknown: back to CAPPED, next page re-uncaps */
        return;
    }

    int dir = j->dir;
    int64_t last_col = (int64_t)a->cfg.origin_counts + (int64_t)j->columns * a->cfg.counts_per_dot;
    int64_t right64 = last_col + a->cfg.margin_counts;
    int64_t left64 = a->cfg.left_stop_counts;
    if (right64 > INT32_MAX || right64 < INT32_MIN || left64 > right64) { send_error(a, OI_DEVERR_RANGE); return; }
    int32_t left = (int32_t)left64, right = (int32_t)right64;
    int32_t x0 = dir > 0 ? left : right, x1 = dir > 0 ? right : left;
    uint32_t vmax = a->cfg.v_max;
    uint32_t vlim = oi_max_cruise_for_head(a->cfg.max_fire_hz, (uint32_t)a->cfg.counts_per_dot);
    if (vmax > vlim) vmax = vlim;                                    /* never exceed the head's fire-rate limit */
    oi_traj_t t;
    uint32_t dist = (uint32_t)((int64_t)x1 > x0 ? (int64_t)x1 - x0 : (int64_t)x0 - x1);   /* <= 2^32-1, exact in uint32 */
    /* The ramp must fit in BOTH real run-in distances: origin - left_stop (before column 0) and margin (after the last column). */
    int64_t bidir = a->cfg.bidir_offset_counts < 0 ? -(int64_t)a->cfg.bidir_offset_counts : a->cfg.bidir_offset_counts;
    int64_t run_lead = (int64_t)a->cfg.origin_counts - a->cfg.left_stop_counts - bidir;   /* the offset eats room on one side or the other */
    int64_t run_tail = (int64_t)a->cfg.margin_counts - bidir;
    if (oi_traj_plan(&t, dist, vmax, a->cfg.accel) || (int64_t)t.accel_counts > run_lead || (int64_t)t.accel_counts > run_tail) {
        send_error(a, OI_DEVERR_RAMP);
        return;
    }

    if (a->hal.home) {                                                /* a real machine with a hard stop at the home switch */
        oi_traj_t tp;                                                 /* positioning moves run at vmax/2 and coast this far past x0 */
        if (oi_traj_plan(&tp, dist, vmax / 2 ? vmax / 2 : 1, a->cfg.accel) || (int64_t)tp.accel_counts > (int64_t)a->cfg.left_stop_counts) {
            send_error(a, OI_DEVERR_RAMP);                            /* left_stop must leave room to brake before the switch */
            return;
        }
    }
    a->sched.head = a->head; a->sched.columns = j->buf; a->sched.n_columns = j->columns;
    a->sched.bytes_per_col = j->bytes_per_col; a->sched.counts_per_dot = a->cfg.counts_per_dot;
    a->sched.origin_counts = a->cfg.origin_counts; a->sched.bidir_offset_counts = a->cfg.bidir_offset_counts;
    if (oi_sched_start(&a->sched, dir) != OI_OK) { send_error(a, OI_DEVERR_CONFIG); return; }

    /* Position at the start of the pass first: the previous pass may have ended somewhere else (different column count). */
    int32_t pos0 = a->hal.encoder_pos(a->hal.ctx);
    if (pos0 != x0 && move_until(a, pos0 < x0 ? 1 : -1, x0, vmax / 2 ? vmax / 2 : 1, 0)) { send_error(a, OI_DEVERR_STALL); return; }
    /* Stop requested when the LAST COLUMN is reached (not at x1): braking then uses the run-out margin, whose size was checked
     * against the ramp above. For a rightward pass the last column is index n-1; for a leftward pass it is column 0. */
    int64_t end64 = dir > 0 ? last_col - a->cfg.counts_per_dot : (int64_t)a->cfg.origin_counts + a->cfg.bidir_offset_counts;
    int32_t end_pos = (int32_t)end64;
    if (move_until(a, dir, end_pos, t.v_cruise, &a->sched)) { send_error(a, OI_DEVERR_STALL); return; }
    if (a->sched.missed) send_error(a, OI_DEVERR_MISSED);              /* dots were lost: tell the host, but keep paper aligned */
    uint64_t steps = oi_feed_steps(&a->feed, j->feed_um);
    a->hal.feed_steps(a->hal.ctx, steps);
    a->paper_steps += steps;
    a->passes++;
}

static void end_page(oi_app_t *a) {
    a->page_active = 0;
    if (oi_maint_page_done(&a->maint) == A_WIPE) { a->hal.maint(a->hal.ctx, A_WIPE); oi_maint_step(&a->maint); }
}

void oi_app_feed(oi_app_t *a, uint8_t byte) {
    a->rx_epoch++;                                           /* machine context turns this into 'page not idle' */
    oi_job_feed(&a->job, byte, hal_reply, a);                /* ACK/NAK/BUSY leave immediately; no pass runs here */
}

int oi_app_service(oi_app_t *a) {
    int did = 0;
    if (oi_job_take_pass(&a->job)) { run_pass(a); oi_job_pass_done(&a->job); did = 1; }
    if (oi_job_take_page_end(&a->job) && a->page_active) { end_page(a); did = 1; }
    return did;
}

void oi_app_rx(oi_app_t *a, uint8_t byte) {
    oi_app_feed(a, byte);
    oi_app_service(a);
}

void oi_app_idle_rx(oi_app_t *a) { oi_parser_reset(&a->job.parser); }

void oi_app_idle(oi_app_t *a, uint32_t dt_ms) {
    oi_app_idle_rx(a);
    oi_app_idle_machine(a, dt_ms);
}

void oi_app_idle_machine(oi_app_t *a, uint32_t dt_ms) {
    if (a->rx_epoch != a->seen_epoch) { a->seen_epoch = a->rx_epoch; a->page_idle_ms = 0; }   /* bytes arrived since last look */
    if (a->page_active && a->cfg.page_timeout_ms) {                  /* aborted job: no PAGE_END will ever come */
        a->page_idle_ms += dt_ms;
        if (a->page_idle_ms >= a->cfg.page_timeout_ms) { a->page_idle_ms = 0; end_page(a); }
    }
    if (a->maint.state != M_READY) return;
    if (oi_maint_tick(&a->maint, dt_ms) == A_CAP) { a->hal.maint(a->hal.ctx, A_CAP); oi_maint_step(&a->maint); }
}
