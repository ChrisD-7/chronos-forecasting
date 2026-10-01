# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Host<->MCU framing. Frame: 0xA5 | type u8 | len u16 LE | payload | crc16 u16 LE.
CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF) over type|len|payload. Spec mirrored in firmware/core/oi_proto.c."""
import binascii
import struct

SOF = 0xA5
T_SWATH_HDR = 1   # payload: swath_idx u16, columns u32, bytes_per_col u16, dir i8, feed_um u32
T_SWATH_DATA = 2  # payload: offset u32, raw bytes (chunk of packed columns)
T_START_PASS = 3  # payload: swath_idx u16 (receiver must ignore a repeated idx: retransmit safe)
T_PAGE_END = 7   # payload: empty; sent after the last swath of a page (wipe accounting, eject)
T_RESET = 9      # host -> device: abandon the current page (best effort after a failed job); ACKed, refused with BUSY mid-pass
T_ERROR = 8      # device -> host, unsolicited: payload code u16, swath idx u16 (codes: firmware/core/oi_app.h OI_DEVERR_*)
T_ACK, T_NAK, T_BUSY = 4, 5, 6   # payload: crc16 u16 LE of the frame being answered; BUSY = printer is printing, retry later
MAX_PAYLOAD = 1024


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
    """CRC-16/CCITT-FALSE (poly 0x1021, init 0xFFFF, no reflection). binascii.crc_hqx is the C implementation of the same function
    (verified against the check value 0x29B1 and the bitwise reference in tests); the bitwise loop cost about 6 s per page of frame data."""
    return binascii.crc_hqx(data, crc)


def crc16_bitwise(data: bytes, crc: int = 0xFFFF) -> int:
    """Reference implementation, kept for the equivalence test."""
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def frame_crc(frame: bytes) -> int:
    return struct.unpack_from("<H", frame, len(frame) - 2)[0]


def encode(ftype: int, payload: bytes = b"") -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload too large")
    body = struct.pack("<BH", ftype, len(payload)) + payload
    return bytes([SOF]) + body + struct.pack("<H", crc16(body))


class NeedMore(ValueError):
    """Buffer holds a valid prefix; read more bytes and retry."""


def decode(buf, off: int = 0):
    """Return (ftype, payload, bytes_consumed) for the frame starting at buf[off:]. Raises NeedMore for a truncated frame, ValueError for a
    corrupt one. Takes an offset instead of requiring a slice so scanning a long stream is linear (slicing copied the rest of the stream
    for every frame: quadratic, and a 50-page job is over 100 MB)."""
    avail = len(buf) - off
    if avail <= 0:
        raise NeedMore("empty")
    if buf[off] != SOF:
        raise ValueError("bad sof")
    if avail < 4:
        raise NeedMore("short header")
    ftype, n = struct.unpack_from("<BH", buf, off + 1)
    if n > MAX_PAYLOAD:
        raise ValueError("bad length")
    if avail < 6 + n:
        raise NeedMore("short payload")
    body = bytes(buf[off + 1:off + 4 + n])
    (crc,) = struct.unpack_from("<H", buf, off + 4 + n)
    if crc != crc16(body):
        raise ValueError("crc")
    return ftype, bytes(buf[off + 4:off + 4 + n]), 6 + n


# Column order contract: columns are ALWAYS sent in left-to-right (increasing carriage position) order.
# For dir=-1 the firmware scheduler (oi_sched.c) starts at the last column and walks backwards; the host
# must NOT pre-reverse the data.


def swath_frames(idx: int, cols: bytes, columns: int, bytes_per_col: int, direction: int, feed_um: int,
                 chunk: int = 512):
    yield encode(T_SWATH_HDR, struct.pack("<HIHbI", idx, columns, bytes_per_col, direction, feed_um))
    for off in range(0, len(cols), chunk):
        yield encode(T_SWATH_DATA, struct.pack("<I", off) + cols[off:off + chunk])
    yield encode(T_START_PASS, struct.pack("<H", idx))


# ---- untrusted-stream validation (used by the CUPS backend, which runs as root and may be handed raw jobs) ----
HOST_TYPES = {T_SWATH_HDR, T_SWATH_DATA, T_START_PASS, T_PAGE_END, T_RESET}
MAX_COLUMNS = 4000        # A4 at 300 dpi is 2480; 600 dpi would be 4961 and is not supported by this firmware build
MAX_BYTES_PER_COL = 64
MAX_FEED_UM = 30_000      # one swath never feeds more than 30 mm (12.7 mm nominal)


def validate_frame(ftype: int, payload: bytes):
    """Return None if a host->device frame is acceptable, else a reason string. Rejects device-only types and out-of-range fields."""
    if ftype not in HOST_TYPES:
        return "frame type %d is not a host->device type" % ftype
    if ftype == T_SWATH_HDR:
        if len(payload) != 13:
            return "swath header length %d" % len(payload)
        idx, cols, bpc, d, feed = struct.unpack("<HIHbI", payload)
        if not (1 <= cols <= MAX_COLUMNS and 1 <= bpc <= MAX_BYTES_PER_COL and d in (1, -1) and feed <= MAX_FEED_UM):
            return "swath header out of range (columns %d, bytes/col %d, dir %d, feed %d um)" % (cols, bpc, d, feed)
    elif ftype == T_SWATH_DATA:
        if len(payload) < 4 or struct.unpack_from("<I", payload)[0] > MAX_COLUMNS * MAX_BYTES_PER_COL:
            return "swath data offset/length out of range"
    elif ftype == T_START_PASS and len(payload) != 2:
        return "start frame length %d" % len(payload)
    elif ftype in (T_PAGE_END, T_RESET) and len(payload) != 0:
        return "frame type %d must have no payload" % ftype
    return None
