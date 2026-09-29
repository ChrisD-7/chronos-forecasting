/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* RP2040 implementation of oi_hal_t + the matrix-head HAL. Compiles against Pico SDK 2.x; NEVER RUN on hardware by the
 * author (no board available). Every timing/polarity/angle constant is in board_config.h and tagged GUESS/UNVERIFIED. */
#include <stdio.h>
#include <string.h>
#include "pico/stdlib.h"
#include "pico/multicore.h"
#include "pico/sync.h"
#include "hardware/gpio.h"
#include "hardware/spi.h"
#include "hardware/pwm.h"
#include "hardware/clocks.h"
#include "hardware/sync.h"
#include "board_config.h"
#include "head_map.h"
#include "oi_board.h"

/* ---------- quadrature encoder (GPIO IRQ, both edges of both channels) ---------- */
static volatile int32_t enc_count;
static volatile uint8_t enc_prev;
/* index = (prev << 2) | now, Gray-code order 00 01 11 10; +1 forward, -1 backward, 0 = no change or invalid */
static const int8_t ENC_TABLE[16] = { 0, +1, -1, 0, -1, 0, 0, +1, +1, 0, 0, -1, 0, -1, +1, 0 };

static void enc_irq(uint gpio, uint32_t events) {
    (void)gpio; (void)events;
    uint8_t now = (uint8_t)((gpio_get(PIN_ENC_A) << 1) | gpio_get(PIN_ENC_B));
    enc_count += ENC_TABLE[(enc_prev << 2) | now];
    enc_prev = now;
}
static int32_t hal_encoder_pos(void *c) { (void)c; return enc_count; }

/* ---------- carriage step generator (repeating timer, trapezoid by acceleration slew) ---------- */
static volatile int car_dir;
static volatile uint32_t car_target_sps;            /* target steps/s */
static volatile float car_v;                        /* current steps/s */
static volatile bool car_running;
static struct repeating_timer car_timer;

static bool car_tick(struct repeating_timer *t) {
    float accel = (float)OI_CAR_ACCEL_COUNTS_S2 * OI_STEPS_PER_COUNT_X1000 / 1000.0f;
    float dt = (float)t->delay_us / 1e6f;
    float v = car_v, tgt = (float)car_target_sps;
    if (v < tgt) { v += accel * dt; if (v > tgt) v = tgt; }
    else if (v > tgt) { v -= accel * dt; if (v < tgt) v = tgt; }
    if (v < 50.0f && tgt == 0) { car_v = 0; car_running = false; return false; }     /* stopped */
    if (v < 50.0f) v = 50.0f;                                                        /* creep start */
    car_v = v;
    gpio_put(PIN_CAR_STEP, 1); busy_wait_us_32(2); gpio_put(PIN_CAR_STEP, 0);
    t->delay_us = -(int64_t)(1000000.0f / v);
    return true;
}

static void hal_carriage_drive(void *c, int dir, uint32_t speed_counts_s) {
    (void)c;
    if (dir == 0 || speed_counts_s == 0) {
        car_target_sps = 0;
        while (car_running) tight_loop_contents();          /* blocks until the trapezoid decelerated to a stop */
        gpio_put(PIN_CAR_EN_N, 1);
        return;
    }
    gpio_put(PIN_CAR_DIR, dir > 0 ? 1 : 0);
    gpio_put(PIN_CAR_EN_N, 0);
    car_dir = dir;
    car_target_sps = (uint32_t)((uint64_t)speed_counts_s * OI_STEPS_PER_COUNT_X1000 / 1000u);
    if (!car_running) {
        car_v = 50.0f; car_running = true;
        add_repeating_timer_us(-20000, car_tick, NULL, &car_timer);
        car_timer.delay_us = -1000;
    }
}
static void hal_wait_encoder_change(void *c) { (void)c; busy_wait_us_32(20); }

/* ---------- paper feed (blocking, short linear ramp) ---------- */
static void hal_feed_steps(void *c, uint64_t steps) {
    (void)c;
    gpio_put(PIN_FEED_DIR, 1); gpio_put(PIN_FEED_EN_N, 0);
    const uint32_t ramp = 200, slow_us = 1000, fast_us = 250;
    for (uint64_t i = 0; i < steps; i++) {
        uint64_t from_end = steps - 1 - i, k = i < from_end ? i : from_end;
        uint32_t d = k >= ramp ? fast_us : slow_us - (uint32_t)((slow_us - fast_us) * k / ramp);
        gpio_put(PIN_FEED_STEP, 1); busy_wait_us_32(2); gpio_put(PIN_FEED_STEP, 0);
        busy_wait_us_32(d);
    }
    gpio_put(PIN_FEED_EN_N, 1);
}

/* ---------- head: 74HC595 chain, outputs gated by OE_N ---------- */
static uint64_t sr_word;                      /* bit i = output i (SR(i/8+1).Q(i%8)); outputs: ADDR0..21, PRIM0..13 */
static uint8_t cur_addr;
static uint32_t cur_prim;

static void sr_shift_and_latch(uint64_t word) {
    uint8_t b[OI_SR_COUNT];
    for (int i = 0; i < OI_SR_COUNT; i++) b[i] = (uint8_t)(word >> (8 * (OI_SR_COUNT - 1 - i)));   /* farthest register first */
    spi_write_blocking(spi0, b, OI_SR_COUNT);
    gpio_put(PIN_SR_RCLK, 1); __asm volatile("nop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\nnop\n"); gpio_put(PIN_SR_RCLK, 0);
}
void oi_board_fire_safe_off(void) { gpio_put(PIN_SR_OE_N, 1); sr_shift_and_latch(0); }

static void mh_select_address(void *hw, uint8_t a) { (void)hw; cur_addr = a; }
static void mh_set_primitives(void *hw, uint32_t m) { (void)hw; cur_prim = m; }
static void __not_in_flash_func(mh_pulse)(void *hw) {
    (void)hw;
    uint64_t addr_bits = OI_ADDR_ACTIVE_HIGH ? (1ull << cur_addr) : (((1ull << OI_N_ADDR) - 1) & ~(1ull << cur_addr));
    sr_word = addr_bits | ((uint64_t)cur_prim << OI_N_ADDR);
    sr_shift_and_latch(sr_word);
    uint32_t irq = save_and_disable_interrupts();
    gpio_put(PIN_SR_OE_N, 0);                                              /* outputs on: the heater pulse starts */
    for (uint32_t i = 0; i < (OI_PULSE_NS * 125u) / 1000u / 2u; i++) __asm volatile("nop\nnop");   /* ~1 cycle per nop at 125 MHz */
    gpio_put(PIN_SR_OE_N, 1);                                              /* outputs off again */
    restore_interrupts(irq);
}
static void mh_idle(void *hw) { (void)hw; oi_board_fire_safe_off(); }
static const oi_matrix_hal_t MATRIX_HAL = { mh_select_address, mh_set_primitives, mh_pulse, mh_idle, 0 };

/* ---------- dry head (never pulses) and head selection ---------- */
static void dry_fire(oi_head_t *h, const uint8_t *bits) { (void)h; (void)bits; }
static oi_head_t dry_head = { "dry", 300, dry_fire, 0 };

#if OI_HEAD_MAP_VERIFIED
#  ifndef OI_HEAD_MAP
#    error "OI_HEAD_MAP_VERIFIED is 1 but OI_HEAD_MAP is not defined in head_map.h"
#  endif
static const uint16_t head_map[300] = OI_HEAD_MAP;
static oi_matrix_head_t matrix_head;
#endif

oi_head_t *oi_board_head(int *armed) {
    *armed = 0;
#if OI_HEAD_MAP_VERIFIED
    if (oi_matrix_head_init(&matrix_head, &MATRIX_HAL, head_map, 300, OI_N_ADDR, OI_N_PRIM) == 0) { *armed = 1; return &matrix_head.head; }
#else
    (void)MATRIX_HAL;
#endif
    return &dry_head;                                                    /* unverified/invalid map: run dry */
}

/* ---------- actuators: hobby servos on PWM (50 Hz) ---------- */
static void servo_init(uint pin) {
    gpio_set_function(pin, GPIO_FUNC_PWM);
    uint slice = pwm_gpio_to_slice_num(pin);
    pwm_set_clkdiv(slice, 125.0f);                    /* 1 MHz counter */
    pwm_set_wrap(slice, 19999);                       /* 20 ms period */
    pwm_set_enabled(slice, true);
}
static void servo_us(uint pin, int us) { pwm_set_gpio_level(pin, (uint16_t)us); sleep_ms(400); }

static oi_head_t *maint_head;
static void hal_maint(void *c, oi_maint_action_t a) {
    (void)c;
    switch (a) {
    case A_UNCAP: servo_us(PIN_CAP_PWM, OI_SERVO_CAP_OPEN_US); break;
    case A_CAP: servo_us(PIN_CAP_PWM, OI_SERVO_CAP_CLOSED_US); break;
    case A_SPIT:
        if (maint_head) { uint8_t all[38]; memset(all, 0xFF, sizeof all); all[37] = 0x0F; for (int i = 0; i < 5; i++) maint_head->fire_column(maint_head, all); }
        break;
    case A_WIPE: servo_us(PIN_WIPE_PWM, OI_SERVO_WIPE_END_US); servo_us(PIN_WIPE_PWM, OI_SERVO_WIPE_HOME_US); break;
    default: break;                                    /* A_MOVE_TO_PAGE: the application positions the carriage itself */
    }
}

/* ---------- transport: USB CDC via stdio, replies serialised across cores ---------- */
static mutex_t reply_mutex;
static void hal_reply(void *c, const uint8_t *f, size_t n) {
    (void)c;
    mutex_enter_blocking(&reply_mutex);
    for (size_t i = 0; i < n; i++) putchar_raw(f[i]);
    stdio_flush();
    mutex_exit(&reply_mutex);
}

static const oi_hal_t HAL = { 0, hal_encoder_pos, hal_carriage_drive, hal_wait_encoder_change, hal_feed_steps, hal_maint, hal_reply };
const oi_hal_t *oi_board_hal(void) { return &HAL; }

static void out_pin(uint pin, int level) { gpio_init(pin); gpio_set_dir(pin, GPIO_OUT); gpio_put(pin, level); }
static void in_pin(uint pin) { gpio_init(pin); gpio_set_dir(pin, GPIO_IN); gpio_pull_up(pin); }

void oi_board_init(void) {
    /* head first, and safe: outputs disabled before anything else */
    out_pin(PIN_SR_OE_N, 1);
    out_pin(PIN_SR_RCLK, 0);
    spi_init(spi0, OI_SPI_HZ);
    spi_set_format(spi0, 8, SPI_CPOL_0, SPI_CPHA_0, SPI_MSB_FIRST);
    gpio_set_function(PIN_SR_SCK, GPIO_FUNC_SPI);
    gpio_set_function(PIN_SR_MOSI, GPIO_FUNC_SPI);
    oi_board_fire_safe_off();
    /* motors disabled, step low */
    out_pin(PIN_CAR_STEP, 0); out_pin(PIN_CAR_DIR, 0); out_pin(PIN_CAR_EN_N, 1);
    out_pin(PIN_FEED_STEP, 0); out_pin(PIN_FEED_DIR, 0); out_pin(PIN_FEED_EN_N, 1);
    in_pin(PIN_PAPER_SENSE); in_pin(PIN_HOME_LEFT); in_pin(PIN_HOME_RIGHT);
    out_pin(PIN_LED, 0);
    servo_init(PIN_CAP_PWM); servo_init(PIN_WIPE_PWM);
    /* encoder */
    in_pin(PIN_ENC_A); in_pin(PIN_ENC_B);
    enc_prev = (uint8_t)((gpio_get(PIN_ENC_A) << 1) | gpio_get(PIN_ENC_B));
    gpio_set_irq_enabled_with_callback(PIN_ENC_A, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true, &enc_irq);
    gpio_set_irq_enabled(PIN_ENC_B, GPIO_IRQ_EDGE_RISE | GPIO_IRQ_EDGE_FALL, true);
    mutex_init(&reply_mutex);
    int armed; maint_head = oi_board_head(&armed);
}
