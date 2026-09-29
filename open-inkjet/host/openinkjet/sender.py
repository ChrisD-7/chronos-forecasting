"""Stop-and-wait sender. A reply only counts if it echoes the CRC of the frame just sent, so a late ACK
for an earlier (retransmitted) frame is ignored instead of acknowledging the wrong frame."""
import struct
from . import protocol as p


class LinkError(RuntimeError):
    pass


def _reply_for(frame_crc: int, read_frame):
    """Return T_ACK / T_NAK for this frame, or None on timeout. Replies for other frames are drained."""
    while True:
        r = read_frame()
        if r is None:
            return None
        ftype, payload = r
        if len(payload) == 2 and struct.unpack("<H", payload)[0] == frame_crc:
            return ftype


def send_frames(frames, write, read_frame, retries: int = 5):
    """write(bytes); read_frame() -> (ftype, payload) or None on timeout.
    Each frame is sent up to retries+1 times; LinkError if none is ACKed."""
    for f in frames:
        want = p.frame_crc(f)
        for _ in range(retries + 1):
            write(f)
            if _reply_for(want, read_frame) == p.T_ACK:
                break
        else:
            raise LinkError("frame not acknowledged")
