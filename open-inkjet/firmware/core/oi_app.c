/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
#include "oi_app.h"
#include <string.h>

static void hal_reply(void *c, const uint8_t *f, size_t n) { oi_app_t *a = c; a->hal.reply(a->hal.ctx, f, n); }

int oi_app_init(oi_app_t *a, const oi_hal_t *hal, const oi_app_cfg_t *cfg, oi_head_t *head, uint8_t *buf, size_t cap) {
    if (!hal || !cfg || !head || !buf || !hal->encoder_pos || !hal->carriage_drive || !hal->wait_encoder_change ||
        !hal->feed_steps || !hal->maint || !hal->reply) return -1;
    if (cfg->counts_per_dot <= 0 || cfg->v_max == 0 || cfg->accel == 0 || cfg->margin_counts <= 0) return -1;
    memset(a, 0, sizeof *a);
    a->hal = *hal; a->cfg = *cfg; a->head = head;
    if (oi_feed_init(&a->feed, cfg->steps_per_mm_x1000)) return -1;
    oi_job_init(&a->job, buf, cap);
    oi_maint_init(&a->maint, cfg->idle_cap_ms, cfg->wipe_every_pages, cfg->spit_droplets);
    return 0;
}

/* Perform maintenance actions until the FSM has nothing more to do (ends in PRINTING when uncapping/positioning). */
static void maint_run(oi_app_t *a, oi_maint_action_t act) {
    for (int guard = 0; guard < 8 && act != A_NONE && act != A_BUSY && a->maint.state != M_FAULT; guard++) {
        a->hal.maint(a->hal.ctx, act);
        act = oi_maint_step(&a->maint);
    }
}

static void run_pass(oi_app_t *a) {
    oi_job_t *j = &a->job;
    if (!a->page_active) {                                           /* first swath of a page: uncap, spit, park at page */
        a->page_active = 1;
        maint_run(a, oi_maint_begin_job(&a->maint));
    }
    if (!oi_maint_may_fire(&a->maint)) { a->faults++; a->pass_errors++; return; }   /* never fire while capped/faulted */

    int dir = j->dir;
    int32_t last_col_pos = a->cfg.origin_counts + (int32_t)j->columns * a->cfg.counts_per_dot;
    int32_t left = a->cfg.left_stop_counts, right = last_col_pos + a->cfg.margin_counts;
    int32_t x0 = dir > 0 ? left : right, x1 = dir > 0 ? right : left;
    uint32_t vmax = a->cfg.v_max;
    uint32_t vlim = oi_max_cruise_for_head(a->cfg.max_fire_hz, (uint32_t)a->cfg.counts_per_dot);
    if (vmax > vlim) vmax = vlim;                                    /* never exceed the head's fire-rate limit */
    oi_traj_t t;
    uint32_t dist = (uint32_t)(x1 > x0 ? x1 - x0 : x0 - x1);
    if (oi_traj_plan(&t, dist, vmax, a->cfg.accel) || t.accel_counts > (uint32_t)a->cfg.margin_counts) {
        a->pass_errors++;                                            /* ramp would not fit in the run-in margin */
        return;
    }

    a->sched.head = a->head; a->sched.columns = j->buf; a->sched.n_columns = j->columns;
    a->sched.bytes_per_col = j->bytes_per_col; a->sched.counts_per_dot = a->cfg.counts_per_dot;
    a->sched.origin_counts = a->cfg.origin_counts; a->sched.bidir_offset_counts = a->cfg.bidir_offset_counts;
    if (oi_sched_start(&a->sched, dir) != OI_OK) { a->pass_errors++; return; }

    a->hal.carriage_drive(a->hal.ctx, dir, t.v_cruise);
    for (;;) {
        int32_t pos = a->hal.encoder_pos(a->hal.ctx);
        oi_sched_on_position(&a->sched, pos);
        if (dir > 0 ? pos >= x1 : pos <= x1) break;
        a->hal.wait_encoder_change(a->hal.ctx);
    }
    a->hal.carriage_drive(a->hal.ctx, 0, 0);
    uint64_t steps = oi_feed_steps(&a->feed, j->feed_um);
    a->hal.feed_steps(a->hal.ctx, steps);
    a->paper_steps += steps;
    a->passes++;
}

void oi_app_rx(oi_app_t *a, uint8_t byte) {
    oi_job_feed(&a->job, byte, hal_reply, a);
    if (oi_job_take_pass(&a->job)) { run_pass(a); oi_job_pass_done(&a->job); }
    if (oi_job_take_page_end(&a->job) && a->page_active) {
        a->page_active = 0;
        if (oi_maint_page_done(&a->maint) == A_WIPE) { a->hal.maint(a->hal.ctx, A_WIPE); oi_maint_step(&a->maint); }
    }
}

void oi_app_idle(oi_app_t *a, uint32_t dt_ms) {
    oi_parser_reset(&a->job.parser);
    if (a->maint.state != M_READY) return;
    if (oi_maint_tick(&a->maint, dt_ms) == A_CAP) { a->hal.maint(a->hal.ctx, A_CAP); oi_maint_step(&a->maint); }
}
