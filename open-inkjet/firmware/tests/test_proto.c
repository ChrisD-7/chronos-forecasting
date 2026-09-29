/* Reads a stream produced by host/openinkjet (vectors.bin) and checks every frame decodes. */
#include <stdlib.h>
#define assert(c) do { if (!(c)) { fprintf(stderr, "FAIL %s:%d %s\n", __FILE__, __LINE__, #c); exit(1); } } while (0)
#include <stdio.h>
#include <string.h>
#include "../core/oi_proto.h"

int main(int argc, char **argv) {
    assert(argc == 2);
    static oi_parser_t p;
    uint8_t chk[] = "123456789";
    assert(oi_crc16(chk, 9, 0xFFFF) == 0x29B1);
    FILE *f = fopen(argv[1], "rb"); assert(f);
    oi_parser_init(&p);
    int c, frames = 0, hdr = 0, data = 0, start = 0, bad = 0;
    while ((c = fgetc(f)) != EOF) {
        oi_result_t r = oi_parser_feed(&p, (uint8_t)c);
        if (r == OI_FRAME) { frames++; hdr += p.type == 1; data += p.type == 2; start += p.type == 3; }
        if (r == OI_BAD) bad++;
    }
    fclose(f);
    printf("frames=%d hdr=%d data=%d start=%d bad=%d\n", frames, hdr, data, start, bad);
    assert(bad == 0 && hdr == start && hdr > 0 && data >= hdr);
    /* corruption: flipped byte must be rejected and parser must resync to the next good frame */
    uint8_t good[] = {0xA5, 4, 0, 0, 0, 0};
    uint16_t crc = oi_crc16(good + 1, 3, 0xFFFF); good[4] = crc & 0xFF; good[5] = crc >> 8;
    oi_parser_init(&p); int ok = 0, nbad = 0;
    uint8_t badf[6]; memcpy(badf, good, 6); badf[1] ^= 0x40;
    for (int i = 0; i < 6; i++) { oi_result_t r = oi_parser_feed(&p, badf[i]); ok += r == OI_FRAME; nbad += r == OI_BAD; }
    for (int i = 0; i < 6; i++) ok += oi_parser_feed(&p, good[i]) == OI_FRAME;
    assert(ok == 1 && nbad == 1);
    /* lost byte mid-frame: parser stalls until reset, then next good frame decodes */
    oi_parser_init(&p);
    uint8_t part[] = {0xA5, 2, 0x10, 0x00, 1, 2, 3}; /* claims 16 payload bytes, only 3 arrive */
    for (int i = 0; i < 7; i++) assert(oi_parser_feed(&p, part[i]) == OI_NONE);
    oi_parser_reset(&p);
    int got = 0;
    for (int i = 0; i < 6; i++) got += oi_parser_feed(&p, good[i]) == OI_FRAME;
    assert(got == 1);
    /* oversized LEN is counted */
    oi_parser_init(&p);
    uint8_t big[] = {0xA5, 1, 0x01, 0x08};
    oi_result_t last = OI_NONE; for (int i = 0; i < 4; i++) last = oi_parser_feed(&p, big[i]);
    assert(last == OI_BAD && p.crc_errors == 1);
    puts("proto tests OK");
    return 0;
}
