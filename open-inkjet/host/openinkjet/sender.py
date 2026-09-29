"""Stop-and-wait sender: every frame must be ACKed; NAK or timeout triggers retransmit."""
from . import protocol as p


class LinkError(RuntimeError):
    pass


def send_frames(frames, write, read_frame, retries: int = 5):
    """write(bytes); read_frame() -> (ftype) or None on timeout. Raises LinkError after `retries` failures."""
    for f in frames:
        for _ in range(retries + 1):
            write(f)
            if read_frame() == p.T_ACK:
                break
        else:
            raise LinkError("frame not acknowledged")
