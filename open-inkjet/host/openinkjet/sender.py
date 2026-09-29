# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Stop-and-wait sender. A reply only counts if it echoes the CRC of the frame just sent, so a late ACK
for an earlier (retransmitted) frame is ignored instead of acknowledging the wrong frame.
BUSY (printer is printing the previous swath) waits and resends WITHOUT using the retry budget, but only until
`busy_timeout` seconds have passed for that frame."""
import struct, time
from . import protocol as p


class LinkError(RuntimeError):
    pass


class DeviceError(LinkError):
    """The printer reported that a pass did not print correctly (T_ERROR frame)."""
    def __init__(self, code, swath):
        super().__init__("printer error code %d on swath %d" % (code, swath))
        self.code, self.swath = code, swath


class LinkClosed(LinkError):
    """The device went away (EOF / I/O error), as opposed to a timeout."""


MAX_DRAIN = 64   # stale replies discarded per wait before the wait counts as a timeout


def _reply_for(frame_crc: int, read_frame):
    """Return T_ACK / T_NAK / T_BUSY for this frame, or None on timeout. Replies for other frames are drained
    (at most MAX_DRAIN, so a device flooding stale replies cannot hang the sender)."""
    for _ in range(MAX_DRAIN):
        r = read_frame()
        if r is None:
            return None
        ftype, payload = r
        if ftype == p.T_ERROR and len(payload) == 4:                # unsolicited: abort the job, do not keep sending
            raise DeviceError(*struct.unpack("<HH", payload))
        if len(payload) == 2 and struct.unpack("<H", payload)[0] == frame_crc:
            return ftype
    return None


def send_frames(frames, write, read_frame, retries: int = 5, busy_timeout: float = 30.0,
                sleep=time.sleep, clock=time.monotonic, busy_poll: float = 0.05):
    """write(bytes); read_frame() -> (ftype, payload) or None on timeout.
    Each frame is sent up to retries+1 times (NAK/timeout); LinkError if none is ACKed or BUSY outlasts busy_timeout."""
    for f in frames:
        want = p.frame_crc(f)
        attempts, busy_since = 0, None
        while True:
            write(f)
            r = _reply_for(want, read_frame)
            if r == p.T_ACK:
                break
            if r == p.T_BUSY:
                busy_since = clock() if busy_since is None else busy_since
                if clock() - busy_since > busy_timeout:
                    raise LinkError("printer stayed busy")
                sleep(busy_poll)
                continue
            attempts += 1
            if attempts > retries:
                raise LinkError("frame not acknowledged")
