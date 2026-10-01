# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""End-to-end through a REAL CUPS daemon: lp -> cupsd -> oi_filter -> backend -> pty -> C firmware simulator -> printed page.

Needs root, an installed CUPS (cupsd, lpadmin, lp), gcc and the repo. Not part of the default pytest run (it modifies /usr/lib/cups and
/etc/cups). Run:  sudo python3 host/tests/cups_integration.py   (from open-inkjet/). Exits 0 only if the printed page equals the expected bitmap."""
import os, pty, subprocess, sys, tempfile, time, tty
import numpy as np
from PIL import Image

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, os.path.join(ROOT, "host"))
sys.path.insert(0, os.path.dirname(__file__))
from openinkjet.filter import page_bitmap
import test_e2e_sim as e2e


def sh(*a, **k):
    return subprocess.run(a, check=k.pop("check", True), capture_output=True, text=True, **k)


def main():
    assert os.geteuid() == 0, "needs root"
    work = tempfile.mkdtemp()
    sim = os.path.join(work, "oi_sim")
    src = ["tests/sim.c"] + ["core/%s.c" % n for n in ("oi_app", "oi_job", "oi_proto", "oi_sched", "oi_head_matrix", "oi_motion", "oi_maint")]
    sh("gcc", "-std=c99", "-D_POSIX_C_SOURCE=200809L", "-Wall", "-Wextra", "-Werror", "-o", sim, *src, cwd=os.path.join(ROOT, "firmware"))
    sh(os.path.join(ROOT, "host", "install_cups.sh"))
    cupsd = subprocess.Popen(["cupsd", "-f"], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for _ in range(50):                                   # wait for the scheduler socket
            if sh("lpstat", "-r", check=False).stdout.startswith("scheduler is running"):
                break
            time.sleep(0.2)
        master, slave = pty.openpty(); tty.setraw(master); tty.setraw(slave)
        out = os.path.join(work, "out.pbm")
        simp = subprocess.Popen([sim, out], stdin=master, stdout=master, stderr=subprocess.PIPE)
        dev = "openinkjet:" + os.ttyname(slave)
        print("device:", dev)
        print(sh("lpadmin", "-p", "oi", "-E", "-v", dev, "-P", "/usr/share/cups/model/openinkjet.ppd").stderr.strip() or "queue created")
        sh("cupsenable", "oi", check=False); sh("cupsaccept", "oi", check=False)
        img = e2e.make_image()
        png = os.path.join(work, "page.png"); img.save(png)
        os.chmod(work, 0o755); os.chmod(png, 0o644)
        r = sh("lp", "-d", "oi", "-o", "fit-to-page", png)
        print(r.stdout.strip())
        deadline = time.time() + 300
        while time.time() < deadline:                         # wait for the queue to drain
            if not sh("lpstat", "-o", "oi", check=False).stdout.strip():
                break
            time.sleep(1)
        else:
            print("TIMEOUT waiting for the job"); print(open("/var/log/cups/error_log").read()[-3000:]); return 1
        time.sleep(1)
        os.close(slave); os.close(master)
        err = simp.stderr.read().decode(); simp.wait(timeout=60)
        print("sim:", err.strip())
        if "passes=24" not in err:
            print(sh("tail", "-n", "40", "/var/log/cups/error_log", check=False).stdout); return 1
        got = e2e.read_pbm(out)
        want = e2e.expected(img)
        ok = got.shape == want.shape and np.array_equal(got, want)
        print("printed page equals expected bitmap:", ok)
        return 0 if ok else 1
    finally:
        sh("lpadmin", "-x", "oi", check=False)
        cupsd.terminate()


if __name__ == "__main__":
    sys.exit(main())
