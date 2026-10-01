/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Core 0: USB CDC receive + oi_app_feed (answers ACK/NAK/BUSY at once, never blocks on a pass).
 * Core 1: oi_app_service loop (runs passes, maintenance, idle timers).
 * Compiles against the Pico SDK; not run on hardware. With no verified head map the head is DRY: everything moves, nothing fires. */
#include <stdio.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "board_config.h"
#include "oi_board.h"

static uint8_t swath_buf[2600 * 38];             /* 2480 columns x 38 bytes for A4 at 300 dpi, with margin */
static oi_app_t app;

static void core1_main(void) {
    uint64_t last = time_us_64();
    for (;;) {
        if (oi_app_service(&app)) { last = time_us_64(); continue; }
        uint64_t now = time_us_64();
        if (now - last >= 50000) { oi_app_idle_machine(&app, (uint32_t)((now - last) / 1000)); last = now; }
        tight_loop_contents();
    }
}

int main(void) {
    stdio_init_all();
    stdio_set_translate_crlf(&stdio_usb, false);
    oi_board_init();
    int armed;
    oi_head_t *head = oi_board_head(&armed);
    oi_app_cfg_t cfg = {
        .counts_per_dot = OI_COUNTS_PER_DOT, .origin_counts = 400, .bidir_offset_counts = 0,      /* GUESS: calibrate per docs/BENCH.md */
        .left_stop_counts = OI_LEFT_STOP_COUNTS, .margin_counts = 400, .v_max = OI_CAR_VMAX_COUNTS_S, .accel = OI_CAR_ACCEL_COUNTS_S2,
        .max_fire_hz = 18000, .steps_per_mm_x1000 = OI_FEED_STEPS_PER_MM_X1000,
        .idle_cap_ms = 2000, .wipe_every_pages = 1, .spit_droplets = 5,
        .stall_ticks = OI_STALL_POLLS, .page_timeout_ms = 10000 };
    if (oi_app_init(&app, oi_board_hal(), &cfg, head, swath_buf, sizeof swath_buf) != 0)
        for (;;) { gpio_put(PIN_LED, 1); sleep_ms(100); gpio_put(PIN_LED, 0); sleep_ms(100); }   /* config error: fast blink */
    gpio_put(PIN_LED, armed ? 1 : 0);                                                            /* solid = armed, dark = dry-run */
    multicore_launch_core1(core1_main);
    uint64_t last_rx = time_us_64();
    for (;;) {
        int ch = getchar_timeout_us(0);
        if (ch >= 0) { oi_app_feed(&app, (uint8_t)ch); last_rx = time_us_64(); continue; }
        if (time_us_64() - last_rx >= 50000) { oi_app_idle_rx(&app); last_rx = time_us_64(); }   /* frame timeout: reset the parser */
    }
}
