"""Host<->MCU framing. Frame: 0xA5 | type u8 | len u16 LE | payload | crc16 u16 LE.
CRC16-CCITT-FALSE (poly 0x1021, init 0xFFFF) over type|len|payload. Spec mirrored in firmware/core/oi_proto.c."""
import struct

SOF = 0xA5
T_SWATH_HDR = 1   # payload: swath_idx u16, columns u32, bytes_per_col u16, dir i8, feed_um u32
T_SWATH_DATA = 2  # payload: offset u32, raw bytes (chunk of packed columns)
T_START_PASS = 3  # payload: swath_idx u16 (receiver must ignore a repeated idx: retransmit safe)
T_ACK, T_NAK = 4, 5   # payload: crc16 u16 LE of the frame being answered
MAX_PAYLOAD = 1024


def crc16(data: bytes, crc: int = 0xFFFF) -> int:
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


def decode(buf: bytes):
    """Return (ftype, payload, bytes_consumed). Raises NeedMore for a truncated frame, ValueError for corrupt."""
    if not buf:
        raise NeedMore("empty")
    if buf[0] != SOF:
        raise ValueError("bad sof")
    if len(buf) < 4:
        raise NeedMore("short header")
    ftype, n = struct.unpack_from("<BH", buf, 1)
    if n > MAX_PAYLOAD:
        raise ValueError("bad length")
    if len(buf) < 6 + n:
        raise NeedMore("short payload")
    body = buf[1:4 + n]
    (crc,) = struct.unpack_from("<H", buf, 4 + n)
    if crc != crc16(body):
        raise ValueError("crc")
    return ftype, buf[4:4 + n], 6 + n


# Column order contract: columns are ALWAYS sent in left-to-right (increasing carriage position) order.
# For dir=-1 the firmware scheduler (oi_sched.c) starts at the last column and walks backwards; the host
# must NOT pre-reverse the data.


def swath_frames(idx: int, cols: bytes, columns: int, bytes_per_col: int, direction: int, feed_um: int,
                 chunk: int = 512):
    yield encode(T_SWATH_HDR, struct.pack("<HIHbI", idx, columns, bytes_per_col, direction, feed_um))
    for off in range(0, len(cols), chunk):
        yield encode(T_SWATH_DATA, struct.pack("<I", off) + cols[off:off + chunk])
    yield encode(T_START_PASS, struct.pack("<H", idx))
