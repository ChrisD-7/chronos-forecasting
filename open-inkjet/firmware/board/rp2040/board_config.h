/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* RP2040 (Pico) pin map and timing constants. The PIN_* list is compared with electronics/netlist.py MCU_PINS by
 * electronics/test_electronics.py, so change both together. Every value tagged GUESS/UNVERIFIED needs a bench measurement. */
#ifndef OI_BOARD_CONFIG_H
#define OI_BOARD_CONFIG_H

/* --- GPIO assignment (matches electronics/netlist.py) --- */
#define PIN_SR_SCK 18            /* SPI0 SCK  -> 74HC595 chain SRCLK */
#define PIN_SR_MOSI 19           /* SPI0 TX   -> 74HC595 SER */
#define PIN_SR_RCLK 20           /* latch */
#define PIN_SR_OE_N 21           /* output enable, active low: the fire pulse gate; pulled HIGH externally = outputs off */
#define PIN_ENC_A 2
#define PIN_ENC_B 3
#define PIN_CAR_STEP 4
#define PIN_CAR_DIR 5
#define PIN_CAR_EN_N 6
#define PIN_FEED_STEP 7
#define PIN_FEED_DIR 8
#define PIN_FEED_EN_N 9
#define PIN_PAPER_SENSE 10
#define PIN_HOME_LEFT 11
#define PIN_HOME_RIGHT 12
#define PIN_CAP_PWM 13
#define PIN_WIPE_PWM 14
#define PIN_LED 25

/* --- head driver (see electronics/design.py) --- */
#define OI_SR_COUNT 5            /* 74HC595 chips: 40 outputs = 22 address + 14 primitive + 4 spare */
#define OI_N_ADDR 22
#define OI_N_PRIM 14
#define OI_SPI_HZ 10000000u      /* requested; the SDK delivers 8.93 MHz at 125 MHz clk_peri. Derated: 74HC595 fmax at 3.3 V is UNVERIFIED */
#define OI_SETTLE_NS 1000u       /* UNVERIFIED: wait between RCLK and OE_N low for the driver stage (electronics/design.py SETTLE_S) */
#define OI_PULSE_NS 2000u        /* UNVERIFIED: fire pulse width; start SHORT on the bench and increase (docs/BENCH.md). Loop is 3 cycles per
                                  * iteration: SCOPE IT, the real width also includes GPIO and loop-entry cycles */
#define OI_ADDR_ACTIVE_HIGH 1    /* UNVERIFIED polarity of the address stage */

/* --- motion (GUESS until calibrated) --- */
#define OI_STEPS_PER_COUNT_X1000 1000u   /* carriage motor steps per encoder count, x1000 */
#define OI_CAR_ACCEL_COUNTS_S2 300000u
#define OI_CAR_VMAX_COUNTS_S 9000u       /* 25% of the 18 kHz x 2 counts/dot head limit */
#define OI_COUNTS_PER_DOT 2              /* 150 lpi strip, x4 quadrature, 300 dpi */
#define OI_FEED_STEPS_PER_MM_X1000 50930u /* 200 * 16 microsteps / (pi * 20 mm roller) = 50.93 (cad/assembly.py) */
#define OI_STALL_POLLS 100000u           /* wait_encoder_change polls (about 20 us each) without progress before aborting */
#define OI_STEP_PULSE_US 3u              /* step pulse width: DRV8825 needs >= 1.9 us, A4988 >= 1 us */
#define OI_STOP_TIMEOUT_MS 2000u         /* hal_carriage_drive(0) gives up waiting for the ramp-down and forces the motor idle */
#define OI_HOME_SPEED_COUNTS_S 1500u     /* homing speed toward the left switch (GUESS) */
#define OI_HOME_TIMEOUT_MS 8000u         /* homing fails if the switch is not reached in this time */

/* --- actuators (GUESS) --- */
#define OI_SERVO_CAP_CLOSED_US 1000
#define OI_SERVO_CAP_OPEN_US 2000
#define OI_SERVO_WIPE_HOME_US 1000
#define OI_SERVO_WIPE_END_US 2000

#endif
