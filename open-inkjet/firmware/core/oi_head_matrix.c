#include "oi_head_matrix.h"
#include <string.h>

static void fire_column(oi_head_t *h, const uint8_t *bits) {
    oi_matrix_head_t *m = (oi_matrix_head_t *)h->ctx;
    uint32_t prim[OI_MATRIX_MAX_ADDR];
    memset(prim, 0, sizeof prim);
    for (uint16_t n = 0; n < h->nozzles; n++)
        if (bits[n >> 3] & (1u << (n & 7))) prim[m->map[n] >> 8] |= 1u << (m->map[n] & 0xFF);
    for (uint8_t a = 0; a < m->n_addr; a++) {
        if (!prim[a]) continue;
        m->hal->select_address(m->hal->hw, a);   /* exactly one address active at a time */
        m->hal->set_primitives(m->hal->hw, prim[a]);
        m->hal->pulse(m->hal->hw);
        m->pulses++;
    }
    m->hal->idle(m->hal->hw);
}

int oi_matrix_head_init(oi_matrix_head_t *m, const oi_matrix_hal_t *hal, const uint16_t *map,
                        uint16_t nozzles, uint8_t n_addr, uint8_t n_prim) {
    if (n_addr == 0 || n_addr > OI_MATRIX_MAX_ADDR || n_prim == 0 || n_prim > 32) return -1;
    static uint8_t seen[OI_MATRIX_MAX_ADDR][32];
    memset(seen, 0, sizeof seen);
    for (uint16_t n = 0; n < nozzles; n++) {
        uint8_t a = (uint8_t)(map[n] >> 8), p = (uint8_t)(map[n] & 0xFF);
        if (a >= n_addr || p >= n_prim || seen[a][p]) return -1;
        seen[a][p] = 1;
    }
    memset(m, 0, sizeof *m);
    m->head.name = "matrix"; m->head.nozzles = nozzles; m->head.fire_column = fire_column; m->head.ctx = m;
    m->hal = hal; m->map = map; m->n_addr = n_addr;
    return 0;
}
