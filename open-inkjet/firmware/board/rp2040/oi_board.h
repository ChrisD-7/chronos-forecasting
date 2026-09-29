/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
#ifndef OI_BOARD_H
#define OI_BOARD_H
#include "../../core/oi_app.h"
#include "../../core/oi_head_matrix.h"

void oi_board_init(void);                         /* GPIO, SPI, PWM, encoder IRQ; everything starts safe (outputs off) */
const oi_hal_t *oi_board_hal(void);
/* Returns the head to hand to oi_app: the real matrix head if a verified nozzle map is compiled in and valid, otherwise a
 * DRY head that never pulses. *armed is set to 1 only for the real head. */
oi_head_t *oi_board_head(int *armed);
void oi_board_fire_safe_off(void);                /* outputs disabled, shift registers cleared */
#endif
