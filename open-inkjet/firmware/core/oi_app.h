/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Device application core: wires job controller -> maintenance FSM -> motion planner -> fire scheduler -> head.
 * Board-independent: everything hardware-specific goes through oi_hal_t (implemented per board, and by
 * firmware/tests/sim.c for the simulator).
 *
 * LIMITATION (documented, not solved here): oi_app_rx() is polled and runs a whole pass before returning, so bytes
 * that arrive during a pass are not parsed until it finishes. A real board must receive into a UART/USB ring buffer
 * (interrupt or DMA) large enough for the host's next frame, and the host must use a reply timeout longer than a
 * pass for the first frame after START (or the RX path must answer BUSY from an interrupt). The simulator runs
 * passes in microseconds, so this is not visible there. */
#ifndef OI_APP_H
#define OI_APP_H
#include "oi_job.h"
#include "oi_sched.h"
#include "oi_motion.h"
#include "oi_maint.h"

typedef struct {
    void *ctx;
    int32_t (*encoder_pos)(void *ctx);                    /* absolute carriage position, encoder counts */
    void (*carriage_drive)(void *ctx, int dir, uint32_t speed_counts_s);   /* dir 0 = stop */
    void (*wait_encoder_change)(void *ctx);               /* block until the encoder moves (or one poll tick) */
    void (*feed_steps)(void *ctx, uint64_t steps);        /* blocking paper feed */
    void (*maint)(void *ctx, oi_maint_action_t a);        /* blocking cap/uncap/spit/wipe/move actions */
    void (*reply)(void *ctx, const uint8_t *f, size_t n); /* transport write */
} oi_hal_t;

typedef struct {
    int32_t counts_per_dot;
    int32_t origin_counts;        /* column 0 position for a rightward pass (already calibrated for flight lag) */
    int32_t bidir_offset_counts;  /* extra trim for leftward passes */
    int32_t left_stop_counts;     /* carriage position at the start of a rightward pass */
    int32_t margin_counts;        /* run-in/out distance beyond the first/last column (must fit the accel ramp) */
    uint32_t v_max, accel;        /* counts/s, counts/s^2 (v_max is clamped to the head's fire-rate limit) */
    uint32_t max_fire_hz;
    uint32_t steps_per_mm_x1000;
    uint32_t idle_cap_ms, wipe_every_pages, spit_droplets;
    uint32_t stall_ticks;         /* carriage watchdog: wait_encoder_change calls without progress before aborting (> 0) */
    uint32_t page_timeout_ms;     /* no bytes for this long mid-page: end the page so the head can be capped (0 = never) */
} oi_app_cfg_t;

/* Device error codes, sent to the host as an unsolicited T_ERROR (8) frame: payload = code u16 LE, swath idx u16 LE.
 * The host sender raises LinkError on it. */
enum { OI_DEVERR_FAULT = 1, OI_DEVERR_RAMP = 2, OI_DEVERR_CONFIG = 3, OI_DEVERR_MISSED = 4, OI_DEVERR_STALL = 5, OI_DEVERR_RANGE = 6 };

typedef struct {
    oi_hal_t hal; oi_app_cfg_t cfg;
    oi_head_t *head;
    oi_job_t job; oi_maint_t maint; oi_feed_t feed; oi_sched_t sched;
    uint64_t paper_steps;
    int page_active;
    uint32_t page_idle_ms;
    uint32_t passes, pass_errors, faults, last_error;
} oi_app_t;

/* Returns 0 on success, -1 on invalid config. buf/cap: swath buffer. */
int oi_app_init(oi_app_t *a, const oi_hal_t *hal, const oi_app_cfg_t *cfg, oi_head_t *head, uint8_t *buf, size_t cap);
/* Feed one received byte; runs any pass / page-end it completes before returning. */
void oi_app_rx(oi_app_t *a, uint8_t byte);
/* Transport silence: reset a stalled frame parser and advance idle timers (caps the head after idle_cap_ms). */
void oi_app_idle(oi_app_t *a, uint32_t dt_ms);
#endif
