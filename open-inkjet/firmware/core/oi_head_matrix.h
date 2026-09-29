/* Address/primitive matrix printhead backend (HP45-style thermal head).
 * Public source (patent snippet via search): 22 address lines x 14 primitives, 300 resistors used.
 * The nozzle -> (address, primitive) map is NOT in this repo as fact: it is a table you fill from bench
 * measurement (docs/BENCH_PHASE2.md). Only one address is enabled at a time. */
#ifndef OI_HEAD_MATRIX_H
#define OI_HEAD_MATRIX_H
#include "oi_head.h"

#define OI_MATRIX_MAX_ADDR 32
typedef struct {
    void (*select_address)(void *hw, uint8_t addr);
    void (*set_primitives)(void *hw, uint32_t mask);   /* bit p = primitive p powered for this pulse */
    void (*pulse)(void *hw);                           /* fires; width set by the HAL */
    void (*idle)(void *hw);                            /* all address/primitive lines off */
    void *hw;
} oi_matrix_hal_t;

typedef struct {
    oi_head_t head;                  /* head.ctx points back at this struct */
    const oi_matrix_hal_t *hal;
    const uint16_t *map;             /* map[nozzle] = (addr << 8) | prim */
    uint8_t n_addr;
    uint32_t pulses;                 /* diagnostics */
} oi_matrix_head_t;

/* Returns 0 on success, -1 if map has out-of-range or duplicate (addr,prim) slots. */
int oi_matrix_head_init(oi_matrix_head_t *m, const oi_matrix_hal_t *hal, const uint16_t *map,
                        uint16_t nozzles, uint8_t n_addr, uint8_t n_prim);
#endif
