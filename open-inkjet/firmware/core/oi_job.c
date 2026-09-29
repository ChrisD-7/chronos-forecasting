#include "oi_job.h"
#include <string.h>

enum { T_HDR = 1, T_DATA = 2, T_START = 3, T_ACK = 4, T_NAK = 5 };

size_t oi_frame_build(uint8_t *out, uint8_t type, const uint8_t *payload, uint16_t len) {
    out[0] = OI_SOF; out[1] = type; out[2] = (uint8_t)(len & 0xFF); out[3] = (uint8_t)(len >> 8);
    if (len) memcpy(out + 4, payload, len);
    uint16_t crc = oi_crc16(out + 1, (size_t)3 + len, 0xFFFF);
    out[4 + len] = (uint8_t)(crc & 0xFF); out[5 + len] = (uint8_t)(crc >> 8);
    return (size_t)6 + len;
}

void oi_job_init(oi_job_t *j, uint8_t *buf, size_t cap) {
    memset(j, 0, sizeof *j);
    oi_parser_init(&j->parser);
    j->buf = buf; j->cap = cap; j->last_started = -1;
}

static void answer(uint8_t type, uint16_t crc, oi_reply_fn reply, void *ctx) {
    uint8_t pl[2] = { (uint8_t)(crc & 0xFF), (uint8_t)(crc >> 8) }, f[8];
    reply(ctx, f, oi_frame_build(f, type, pl, 2));
}

static uint16_t rd16(const uint8_t *p) { return (uint16_t)(p[0] | (p[1] << 8)); }
static uint32_t rd32(const uint8_t *p) { return (uint32_t)p[0] | ((uint32_t)p[1] << 8) | ((uint32_t)p[2] << 16) | ((uint32_t)p[3] << 24); }

/* returns 1 = ACK, 0 = NAK */
static int handle(oi_job_t *j) {
    const oi_parser_t *p = &j->parser;
    if (p->type == T_HDR) {
        if (p->len != 13) return 0;
        uint32_t cols = rd32(p->payload + 2); uint16_t bpc = rd16(p->payload + 6);
        if (bpc == 0 || (uint64_t)cols * bpc > j->cap) return 0;
        int8_t d = (int8_t)p->payload[8];
        if (d != 1 && d != -1) return 0;
        j->idx = rd16(p->payload); j->columns = cols; j->bytes_per_col = bpc; j->dir = d;
        j->feed_um = rd32(p->payload + 9);
        j->total = (size_t)cols * bpc; j->received = 0; j->have_hdr = 1; j->pass_ready = 0;
        return 1;
    }
    if (p->type == T_DATA) {
        if (!j->have_hdr || p->len < 4) return 0;
        uint32_t off = rd32(p->payload); size_t n = (size_t)p->len - 4;
        if ((size_t)off + n <= j->received) { j->dup_acks++; return 1; }      /* retransmit of data we already have */
        if (off != j->received || (size_t)off + n > j->total) return 0;
        memcpy(j->buf + off, p->payload + 4, n); j->received += n;
        return 1;
    }
    if (p->type == T_START) {
        if (p->len != 2) return 0;
        uint16_t idx = rd16(p->payload);
        if ((int32_t)idx == j->last_started) { j->dup_acks++; return 1; }      /* idempotent: never print a swath twice */
        if (!j->have_hdr || idx != j->idx || j->received != j->total) return 0;
        j->last_started = idx; j->pass_ready = 1;
        return 1;
    }
    return 0;
}

void oi_job_feed(oi_job_t *j, uint8_t b, oi_reply_fn reply, void *ctx) {
    oi_result_t r = oi_parser_feed(&j->parser, b);
    if (r == OI_FRAME) {
        int ok = handle(j);
        if (!ok) j->naks++;
        answer(ok ? T_ACK : T_NAK, j->parser.crc, reply, ctx);
    }
    /* OI_BAD: no CRC-valid frame to answer; host times out and retransmits */
}

int oi_job_take_pass(oi_job_t *j) { int r = j->pass_ready; j->pass_ready = 0; return r; }
