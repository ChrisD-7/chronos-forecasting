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

/* Busy-wait of exactly 3 cycles per iteration on Cortex-M0+ (subs = 1, taken bne = 2). Used for the head timing, where the
 * SDK's 1 us granularity is too coarse. Lives in RAM when called from a __not_in_flash_func function. */
static inline __attribute__((always_inline)) void delay3(uint32_t n) {
    __asm volatile(".syntax unified\n\t1: subs %0, #1\n\tbne 1b" : "+l"(n) : : "cc");
}
#define NS_TO_ITERS(ns) ((((uint32_t)(ns)) * 125u / 1000u) / 3u)       /* at the 125 MHz default system clock */

/* ---------- quadrature encoder (GPIO IRQ, both edges of both channels) ---------- */
static volatile int32_t enc_count;
static volatile uint8_t enc_prev;
/* index = (prev << 2) | now, Gray-code order 00 01 11 10; +1 forward, -1 backward, 0 = no change or invalid (a skipped
 * transition loses 2 counts silently) */
static const int8_t ENC_TABLE[16] = { 0, +1, -1, 0, -1, 0, 0, +1, +1, 0, 0, -1, 0, -1, +1, 0 };

static void enc_irq(uint gpio, uint32_t events) {
    (void)gpio; (void)events;
    uint8_t now = (uint8_t)((gpio_get(PIN_ENC_A) << 1) | gpio_get(PIN_ENC_B));
    enc_count += ENC_TABLE[(enc_prev << 2) | now];
    enc_prev = now;
}
static int32_t hal_encoder_pos(void *c) { (void)c; return enc_count; }

/* ---------- carriage step generator ----------
 * A repeating timer fires once per step. The callback runs on the core that created the timer (core 0 here, in IRQ context)
 * while hal_carriage_drive() runs on core 1, so the target/running state is protected by a spin lock. The step period is kept in
 * car_period_us (always positive); the SDK's t->delay_us is negative ("from the last fire time") and must not be used as dt. */
#define CAR_START_SPS 500u                          /* start/stop speed: steps/s the motor can take without ramping (GUESS) */
static spin_lock_t *car_lock;
static volatile int car_dir;
static volatile uint32_t car_target_sps;            /* target steps/s, 0 = decelerate and stop */
static volatile uint32_t car_sps;                   /* current steps/s */
static volatile uint32_t car_period_us;             /* current step period, positive */
static volatile bool car_running;
static struct repeating_timer car_timer;

static bool car_tick(struct repeating_timer *t) {
    uint32_t sps = car_sps, tgt = car_target_sps;
    uint32_t accel_sps2 = (uint32_t)(((uint64_t)OI_CAR_ACCEL_COUNTS_S2 * OI_STEPS_PER_COUNT_X1000) / 1000u);
    uint32_t dv = (uint32_t)(((uint64_t)accel_sps2 * car_period_us) / 1000000u);   /* speed change over one period */
    if (dv == 0) dv = 1;
    if (sps < tgt) { sps += dv; if (sps > tgt) sps = tgt; }
    else if (sps > tgt) { sps = sps > dv ? sps - dv : 0; if (sps < tgt) sps = tgt; }
    if (sps < CAR_START_SPS && tgt < CAR_START_SPS) {   /* at/below the start-stop speed and not asked to go faster: stop */
        uint32_t save = spin_lock_blocking(car_lock);
        bool restart = car_target_sps >= CAR_START_SPS;  /* core 1 raised the target while we decided: keep running */
        if (!restart) { car_sps = 0; car_running = false; }
        spin_unlock(car_lock, save);
        if (!restart) return false;
        sps = CAR_START_SPS;
    }
    if (sps < CAR_START_SPS) sps = CAR_START_SPS;         /* never step slower than the start speed while moving */
    car_sps = sps;
    car_period_us = (1000000u + sps - 1u) / sps;        /* ceil: the real rate never exceeds the target */
    gpio_put(PIN_CAR_STEP, 1); busy_wait_us_32(OI_STEP_PULSE_US); gpio_put(PIN_CAR_STEP, 0);
    t->delay_us = -(int64_t)car_period_us;               /* next step one period after this one */
    return true;
}

static void hal_carriage_drive(void *c, int dir, uint32_t speed_counts_s) {
    (void)c;
    if (dir == 0 || speed_counts_s == 0) {
        uint32_t save = spin_lock_blocking(car_lock);
        car_target_sps = 0;
        spin_unlock(car_lock, save);
        absolute_time_t until = make_timeout_time_ms(OI_STOP_TIMEOUT_MS);
        while (car_running) {                              /* blocks until the trapezoid decelerated to a stop, but never forever */
            if (time_reached(until)) {
                cancel_repeating_timer(&car_timer);       /* the tick stopped answering: force the motor idle */
                car_running = false; car_sps = 0;
                break;
            }
            tight_loop_contents();
        }
        gpio_put(PIN_CAR_EN_N, 1);
        return;
    }
    uint32_t save = spin_lock_blocking(car_lock);
    car_dir = dir;
    gpio_put(PIN_CAR_DIR, dir > 0 ? 1 : 0);
    car_target_sps = (uint32_t)((uint64_t)speed_counts_s * OI_STEPS_PER_COUNT_X1000 / 1000u);
    if (car_target_sps < CAR_START_SPS) car_target_sps = CAR_START_SPS;
    bool start = !car_running;
    if (start) { car_running = true; car_sps = CAR_START_SPS; car_period_us = 1000000u / CAR_START_SPS; }
    spin_unlock(car_lock, save);
    gpio_put(PIN_CAR_EN_N, 0);
    if (start && !add_repeating_timer_us(-(int64_t)car_period_us, car_tick, NULL, &car_timer)) {
        car_running = false; car_target_sps = 0;           /* no alarm slot: do not claim to be running */
        gpio_put(PIN_CAR_EN_N, 1);
    }
}
static void hal_wait_encoder_change(void *c) { (void)c; busy_wait_us_32(20); }

/* Homing: always approach the left switch from the right. Active-low switch with pull-up (polarity UNVERIFIED).
 *  1. if the switch is already closed, back off to the right until it opens (a zero taken anywhere inside the actuation range would differ);
 *  2. drive left; if the encoder has not moved left after OI_HOME_DIR_CHECK_MS the direction or encoder is wrong: abort (never run 8 s into a stop);
 *  3. record the encoder value at the moment the switch closes, brake, then re-zero relative to that value, so zero = switch edge, not the
 *     braking overshoot. The carriage ends up a few counts left of zero; left_stop_counts must leave room for that (checked in oi_app.c).
 * Returns 0 on success, -1 on any timeout, wrong direction, stuck switch or start failure (the carriage is stopped in every case). */
static int hal_home(void *c) {
    (void)c;
    if (!gpio_get(PIN_HOME_LEFT)) {                       /* on the switch: back off to the right */
        hal_carriage_drive(0, +1, OI_HOME_SPEED_COUNTS_S);
        if (!car_running) return -1;
        absolute_time_t until = make_timeout_time_ms(OI_HOME_TIMEOUT_MS);
        while (!gpio_get(PIN_HOME_LEFT)) {
            if (time_reached(until)) { hal_carriage_drive(0, 0, 0); return -1; }      /* stuck closed or wrong direction */
            busy_wait_us_32(50);
        }
        hal_carriage_drive(0, 0, 0);
    }
    int32_t start = enc_count;
    hal_carriage_drive(0, -1, OI_HOME_SPEED_COUNTS_S);
    if (!car_running) return -1;
    absolute_time_t until = make_timeout_time_ms(OI_HOME_TIMEOUT_MS), check = make_timeout_time_ms(OI_HOME_DIR_CHECK_MS);
    bool moved = false;
    while (gpio_get(PIN_HOME_LEFT)) {
        if (!moved && time_reached(check)) {
            if (enc_count >= start - 2) { hal_carriage_drive(0, 0, 0); return -1; }   /* not moving left: DIR or encoder wrong */
            moved = true;
        }
        if (time_reached(until)) { hal_carriage_drive(0, 0, 0); return -1; }
        busy_wait_us_32(50);
    }
    int32_t at_close = enc_count;                         /* encoder value when the switch closed (aligned 32-bit read) */
    hal_carriage_drive(0, 0, 0);
    if (gpio_get(PIN_HOME_LEFT)) return -1;               /* switch reads open after braking: bounce or wiring fault, do not trust the zero */
    uint32_t irq = save_and_disable_interrupts();
    enc_count -= at_close;                                /* zero = switch edge */
    restore_interrupts(irq);
    return 0;
}

/* ---------- paper feed (blocking, short linear ramp) ---------- */
static void hal_feed_steps(void *c, uint64_t steps) {
    (void)c;
    gpio_put(PIN_FEED_DIR, 1); gpio_put(PIN_FEED_EN_N, 0);
    const uint32_t ramp = 200, slow_us = 1000, fast_us = 250;
    for (uint64_t i = 0; i < steps; i++) {
        uint64_t from_end = steps - 1 - i, k = i < from_end ? i : from_end;
        uint32_t d = k >= ramp ? fast_us : slow_us - (uint32_t)((slow_us - fast_us) * k / ramp);
        gpio_put(PIN_FEED_STEP, 1); busy_wait_us_32(OI_STEP_PULSE_US); gpio_put(PIN_FEED_STEP, 0);
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
    gpio_put(PIN_SR_RCLK, 1); delay3(NS_TO_ITERS(100)); gpio_put(PIN_SR_RCLK, 0);                    /* ~100 ns latch */
}
void oi_board_fire_safe_off(void) { gpio_put(PIN_SR_OE_N, 1); sr_shift_and_latch(0); }

static void mh_select_address(void *hw, uint8_t a) { (void)hw; cur_addr = a; }
static void mh_set_primitives(void *hw, uint32_t m) { (void)hw; cur_prim = m; }
static void __not_in_flash_func(mh_pulse)(void *hw) {
    (void)hw;
    uint64_t addr_bits = OI_ADDR_ACTIVE_HIGH ? (1ull << cur_addr) : (((1ull << OI_N_ADDR) - 1) & ~(1ull << cur_addr));
    sr_word = addr_bits | ((uint64_t)cur_prim << OI_N_ADDR);
    sr_shift_and_latch(sr_word);                                           /* data latched, outputs still disabled (OE_N high) */
    delay3(NS_TO_ITERS(OI_SETTLE_NS));                                     /* let the driver stage settle before the pulse */
    uint32_t irq = save_and_disable_interrupts();
    gpio_put(PIN_SR_OE_N, 0);                                              /* outputs on: the heater pulse starts */
    delay3(NS_TO_ITERS(OI_PULSE_NS));                                      /* ~OI_PULSE_NS (3 cycles per iteration; scope-check) */
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

static const oi_hal_t HAL = { 0, hal_encoder_pos, hal_carriage_drive, hal_wait_encoder_change, hal_feed_steps, hal_maint, hal_reply, hal_home };
const oi_hal_t *oi_board_hal(void) { return &HAL; }

/* Set the level BEFORE making the pin an output: gpio_init() leaves the output register at 0, so the other order would drive the
 * pin low for a few cycles (OE_N and the driver enables must never glitch active at boot). */
static void out_pin(uint pin, int level) { gpio_init(pin); gpio_put(pin, level); gpio_set_dir(pin, GPIO_OUT); }
static void in_pin(uint pin) { gpio_init(pin); gpio_set_dir(pin, GPIO_IN); gpio_pull_up(pin); }

void oi_board_init(void) {
    /* head first, and safe: outputs disabled before anything else (an external pull-up on OE_N covers reset, see netlist.py) */
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
    car_lock = spin_lock_init(spin_lock_claim_unused(true));
    int armed; maint_head = oi_board_head(&armed);
}
