#include "oi_maint.h"
#include <string.h>

void oi_maint_init(oi_maint_t *m, uint32_t idle_cap_after_ms, uint32_t wipe_every_pages, uint32_t spit) {
    memset(m, 0, sizeof *m);
    m->state = M_CAPPED; m->idle_cap_after_ms = idle_cap_after_ms;
    m->wipe_every_pages = wipe_every_pages; m->spit_before_pass = spit;
}

oi_maint_action_t oi_maint_begin_job(oi_maint_t *m) {
    m->idle_ms = 0;
    if (m->state == M_CAPPED) { m->state = M_UNCAPPING; return A_UNCAP; }
    if (m->state == M_READY) { m->state = M_PRINTING; return A_MOVE_TO_PAGE; }
    if (m->state == M_UNCAPPING || m->state == M_SPITTING || m->state == M_WIPING || m->state == M_CAPPING)
        return A_BUSY;                                 /* maintenance move in progress: retry later, no fault */
    m->state = M_FAULT; return A_NONE;                /* printing/faulted: caller violated the protocol */
}

oi_maint_action_t oi_maint_step(oi_maint_t *m) {
    switch (m->state) {
    case M_UNCAPPING:
        if (m->spit_before_pass) { m->state = M_SPITTING; return A_SPIT; }
        m->state = M_PRINTING; return A_MOVE_TO_PAGE;
    case M_SPITTING: m->state = M_PRINTING; return A_MOVE_TO_PAGE;
    case M_WIPING:   m->state = M_READY;    return A_NONE;
    case M_CAPPING:  m->state = M_CAPPED;   return A_NONE;
    default:         return A_NONE;         /* READY/PRINTING/CAPPED/FAULT: nothing pending */
    }
}

oi_maint_action_t oi_maint_page_done(oi_maint_t *m) {
    if (m->state != M_PRINTING) { m->state = M_FAULT; return A_NONE; }
    m->pages_since_wipe++;
    if (m->wipe_every_pages && m->pages_since_wipe >= m->wipe_every_pages) {
        m->pages_since_wipe = 0; m->state = M_WIPING; return A_WIPE;
    }
    m->state = M_READY; return A_NONE;
}

oi_maint_action_t oi_maint_tick(oi_maint_t *m, uint32_t dt_ms) {
    if (m->state != M_READY) return A_NONE;
    m->idle_ms += dt_ms;
    if (m->idle_ms >= m->idle_cap_after_ms) { m->state = M_CAPPING; return A_CAP; }
    return A_NONE;
}

int oi_maint_may_fire(const oi_maint_t *m) { return m->state == M_PRINTING; }
void oi_maint_clear_fault(oi_maint_t *m) { if (m->state == M_FAULT) { m->state = M_CAPPED; m->idle_ms = 0; m->pages_since_wipe = 0; } }
