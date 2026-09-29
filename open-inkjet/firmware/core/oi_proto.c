#include "oi_proto.h"
#include <string.h>

enum { S_SOF, S_TYPE, S_LEN0, S_LEN1, S_PAY, S_CRC0, S_CRC1 };

uint16_t oi_crc16(const uint8_t *d, size_t n, uint16_t crc) {
    for (size_t i = 0; i < n; i++) {
        crc ^= (uint16_t)d[i] << 8;
        for (int k = 0; k < 8; k++)
            crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
    }
    return crc;
}

void oi_parser_init(oi_parser_t *p) { memset(p, 0, sizeof *p); p->state = S_SOF; }
void oi_parser_reset(oi_parser_t *p) { p->state = S_SOF; p->len = p->got = 0; }

oi_result_t oi_parser_feed(oi_parser_t *p, uint8_t b) {
    switch (p->state) {
    case S_SOF:
        if (b == OI_SOF) { p->state = S_TYPE; p->crc = 0xFFFF; }
        return OI_NONE;
    case S_TYPE:
        p->type = b; p->crc = oi_crc16(&b, 1, p->crc); p->state = S_LEN0; return OI_NONE;
    case S_LEN0:
        p->len = b; p->crc = oi_crc16(&b, 1, p->crc); p->state = S_LEN1; return OI_NONE;
    case S_LEN1:
        p->len |= (uint16_t)b << 8; p->crc = oi_crc16(&b, 1, p->crc); p->got = 0;
        if (p->len > OI_MAX_PAYLOAD) { p->state = S_SOF; p->crc_errors++; return OI_BAD; }
        p->state = p->len ? S_PAY : S_CRC0; return OI_NONE;
    case S_PAY:
        p->payload[p->got++] = b; p->crc = oi_crc16(&b, 1, p->crc);
        if (p->got == p->len) p->state = S_CRC0;
        return OI_NONE;
    case S_CRC0: p->rx_crc = b; p->state = S_CRC1; return OI_NONE;
    default: /* S_CRC1 */
        p->rx_crc |= (uint16_t)b << 8; p->state = S_SOF;
        if (p->rx_crc == p->crc) return OI_FRAME;
        p->crc_errors++; return OI_BAD;
    }
}
