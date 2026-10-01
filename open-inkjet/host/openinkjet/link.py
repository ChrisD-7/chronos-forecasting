# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Byte-stream link (serial tty, pipe, socket fd) with frame-level reads that time out."""
import os, select, stat
from . import protocol as p
from .sender import LinkError, LinkClosed


class FdLink:
    def __init__(self, read_fd: int, write_fd: int, timeout: float = 0.3, write_timeout: float = 5.0):
        self.r, self.w, self.timeout, self.write_timeout = read_fd, write_fd, timeout, write_timeout
        self.buf = bytearray()
        self.restore = None          # (fd, termios attrs) to put the tty back the way we found it

    def close(self):
        if self.restore:
            try:
                import termios
                termios.tcsetattr(self.restore[0], termios.TCSANOW, self.restore[1])
            except Exception:
                pass
            self.restore = None
        for fd in {self.r, self.w}:
            try:
                os.close(fd)
            except OSError:
                pass

    def write(self, data: bytes):
        view = memoryview(data)
        while view:
            _, ready, _ = select.select([], [self.w], [], self.write_timeout)
            if not ready:
                raise LinkError("write timed out (device not draining)")
            try:
                n = os.write(self.w, view)
            except BlockingIOError:
                continue
            except OSError as e:
                raise LinkClosed("write failed: %s" % e)
            view = view[n:]

    def read_frame(self):
        """Return (ftype, payload); None if no complete valid frame arrives within `timeout`.
        Raises LinkClosed on EOF or read error (device gone)."""
        while True:
            i = self.buf.find(bytes([p.SOF]))
            if i < 0:
                self.buf.clear()
            elif i > 0:
                del self.buf[:i]                       # skip garbage before the next SOF in one step
            if self.buf:
                try:
                    t, pl, n = p.decode(bytes(self.buf))
                    del self.buf[:n]
                    return t, pl
                except p.NeedMore:
                    pass
                except ValueError:
                    del self.buf[:1]                   # false SOF (0xA5 inside payload): drop it, look for the next
                    continue
            ready, _, _ = select.select([self.r], [], [], self.timeout)
            if not ready:
                return None
            try:
                chunk = os.read(self.r, 4096)
            except OSError as e:
                raise LinkClosed("read failed: %s" % e)
            if not chunk:
                raise LinkClosed("device closed the link")
            self.buf += chunk


def open_serial(path: str, baud_const=None) -> FdLink:
    """Open a tty in raw mode (path must already be validated by the caller). Non-tty devices are rejected.
    baud_const: a termios.B* constant (default B115200)."""
    import termios, tty
    fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)   # O_NONBLOCK: never hang on open
    try:
        if not stat.S_ISCHR(os.fstat(fd).st_mode) or not os.isatty(fd):
            raise OSError("%s is not a tty" % path)
        os.set_blocking(fd, True)
        saved = termios.tcgetattr(fd)
        tty.setraw(fd)
        attrs = termios.tcgetattr(fd)
        b = baud_const if baud_const is not None else termios.B115200
        attrs[2] |= termios.CLOCAL | termios.CREAD
        attrs[4] = attrs[5] = b
        termios.tcsetattr(fd, termios.TCSANOW, attrs)
    except (OSError, termios.error):
        os.close(fd)
        raise
    link = FdLink(fd, fd)
    link.restore = (fd, saved)
    return link
