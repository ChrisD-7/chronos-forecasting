"""Byte-stream link (serial tty, pipe, socket fd) with frame-level reads that time out."""
import os, select
from . import protocol as p


class FdLink:
    def __init__(self, read_fd: int, write_fd: int, timeout: float = 0.3):
        self.r, self.w, self.timeout, self.buf = read_fd, write_fd, timeout, b""

    def write(self, data: bytes):
        view = memoryview(data)
        while view:
            n = os.write(self.w, view)
            view = view[n:]

    def read_frame(self):
        """Return (ftype, payload), or None if no complete valid frame arrives within `timeout`."""
        while True:
            try:
                t, pl, n = p.decode(self.buf)
                self.buf = self.buf[n:]
                return t, pl
            except p.NeedMore:
                pass
            except ValueError:
                self.buf = self.buf[1:]          # resync: drop one byte, hunt for the next SOF
                continue
            ready, _, _ = select.select([self.r], [], [], self.timeout)
            if not ready:
                return None
            chunk = os.read(self.r, 4096)
            if not chunk:
                return None
            self.buf += chunk


def open_serial(path: str, baud_const=None) -> FdLink:
    """Open a tty in raw mode. baud_const: a termios.B* constant (default B115200)."""
    import termios, tty
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(fd)
    attrs = termios.tcgetattr(fd)
    b = baud_const if baud_const is not None else termios.B115200
    attrs[4] = attrs[5] = b
    termios.tcsetattr(fd, termios.TCSANOW, attrs)
    return FdLink(fd, fd)
