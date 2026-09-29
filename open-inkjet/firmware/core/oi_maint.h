/* Maintenance state machine: cap when idle, uncap before printing, spit, wipe.
 * Steps are emitted as actions for the motion layer; it does no I/O itself. */
#ifndef OI_MAINT_H
#define OI_MAINT_H
#include <stdint.h>

typedef enum { M_CAPPED, M_UNCAPPING, M_SPITTING, M_READY, M_PRINTING, M_WIPING, M_CAPPING, M_FAULT } oi_maint_state_t;
typedef enum { A_NONE, A_MOVE_TO_PARK, A_CAP, A_UNCAP, A_SPIT, A_WIPE, A_MOVE_TO_PAGE } oi_maint_action_t;

typedef struct {
    oi_maint_state_t state;
    uint32_t idle_ms, idle_cap_after_ms;   /* cap the head after this much idle time */
    uint32_t pages_since_wipe, wipe_every_pages;
    uint32_t spit_before_pass;             /* droplets to spit into the cap before each print job */
} oi_maint_t;

void oi_maint_init(oi_maint_t *m, uint32_t idle_cap_after_ms, uint32_t wipe_every_pages, uint32_t spit);
/* Job requested: returns next action to perform (drives head out of the cap first). Faults if already printing. */
oi_maint_action_t oi_maint_begin_job(oi_maint_t *m);
/* Call after the previous action completed; returns the next action or A_NONE when the state settled. */
oi_maint_action_t oi_maint_step(oi_maint_t *m);
/* Page finished: returns A_WIPE when a wipe is due (then call oi_maint_step when it completes), else A_NONE. */
oi_maint_action_t oi_maint_page_done(oi_maint_t *m);
/* Tick with elapsed ms while not printing; caps the head after the idle timeout. */
oi_maint_action_t oi_maint_tick(oi_maint_t *m, uint32_t dt_ms);
/* Printing is only permitted in M_PRINTING. */
int oi_maint_may_fire(const oi_maint_t *m);
#endif
