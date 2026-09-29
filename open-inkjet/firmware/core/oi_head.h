/* SPDX-FileCopyrightText: 2026 open-inkjet contributors
 * SPDX-License-Identifier: GPL-3.0-only */
/* Printhead abstraction: the scheduler never touches HP45-specific pins. */
#ifndef OI_HEAD_H
#define OI_HEAD_H
#include <stdint.h>

typedef struct oi_head oi_head_t;
struct oi_head {
    const char *name;
    uint16_t nozzles;
    /* Fire one column. bits[] packs nozzle 0 in bit0 of byte0. Must return
     * within the head's max period; hardware timing lives in the backend. */
    void (*fire_column)(oi_head_t *h, const uint8_t *bits);
    void *ctx;
};
#endif
