#ifndef OI_PROTO_H
#define OI_PROTO_H
#include <stdint.h>
#include <stddef.h>

#define OI_SOF 0xA5
#define OI_MAX_PAYLOAD 1024

typedef struct {
    uint8_t  state;
    uint8_t  type;
    uint16_t len, got, crc, rx_crc;
    uint8_t  payload[OI_MAX_PAYLOAD];
    uint32_t crc_errors;
} oi_parser_t;

typedef enum { OI_NONE = 0, OI_FRAME = 1, OI_BAD = -1 } oi_result_t;

uint16_t oi_crc16(const uint8_t *d, size_t n, uint16_t crc);
void oi_parser_init(oi_parser_t *p);
/* Feed one byte. Returns OI_FRAME when a complete valid frame is in p->type/len/payload,
 * OI_BAD on CRC/length error, else OI_NONE.
 * Resync contract: after OI_BAD the parser hunts for the next SOF byte, but 0xA5 also occurs in
 * payload data, so a lost byte mid-frame is NOT self-healing. The transport must (a) call
 * oi_parser_reset() when no byte arrives for OI_FRAME_TIMEOUT_MS and (b) use per-frame ACK/NAK
 * with host retransmit (see host/openinkjet/sender.py). */
#define OI_FRAME_TIMEOUT_MS 50
void oi_parser_reset(oi_parser_t *p);
oi_result_t oi_parser_feed(oi_parser_t *p, uint8_t b);
#endif
