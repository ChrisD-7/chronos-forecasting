/* Job controller: consumes protocol frames, assembles a swath, ACK/NAKs, and reports pass-ready.
 * Replies echo the CRC of the frame answered (see host/openinkjet/sender.py). */
#ifndef OI_JOB_H
#define OI_JOB_H
#include <stdint.h>
#include <stddef.h>
#include "oi_proto.h"

typedef struct {
    oi_parser_t parser;
    uint8_t *buf;            /* swath column buffer (caller-owned) */
    size_t cap;
    /* current swath */
    uint16_t idx; uint32_t columns; uint16_t bytes_per_col; int8_t dir; uint32_t feed_um;
    size_t total, received;
    int have_hdr;
    /* pass hand-off */
    int pass_ready;          /* START accepted, pass not yet taken */
    int busy;                /* pass taken and running: buffer is owned by the machine until oi_job_pass_done() */
    int started;             /* START already accepted for the current header (dedupe key with idx) */
    uint32_t naks, dup_acks, busys;
} oi_job_t;

typedef void (*oi_reply_fn)(void *ctx, const uint8_t *frame, size_t n);

void oi_job_init(oi_job_t *j, uint8_t *buf, size_t cap);
/* Feed one received byte; replies (ACK/NAK) are emitted through reply(). */
void oi_job_feed(oi_job_t *j, uint8_t b, oi_reply_fn reply, void *ctx);
/* Non-zero when a full swath is buffered and START_PASS was accepted; marks the buffer busy. */
int oi_job_take_pass(oi_job_t *j);
/* The machine finished printing the taken pass; the buffer may be overwritten again.
 * While pass_ready/busy the job answers HDR/DATA/START with BUSY (the host waits and retries, see sender.py). */
void oi_job_pass_done(oi_job_t *j);
size_t oi_frame_build(uint8_t *out, uint8_t type, const uint8_t *payload, uint16_t len);
#endif
