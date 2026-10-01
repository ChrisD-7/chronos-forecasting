# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""ngspice simulation of the head power stage under the ASSUMED head parameters in design.py (12 V SOURCED; 30 ohm heaters and 2 us
pulses UNVERIFIED). It checks the capacitor/ESR/droop budget with a circuit simulator instead of only arithmetic. It does not model the
real driver FETs, the head's thermal behaviour or the address FET stage; switches are ideal with a stated on-resistance.

Circuit: supply -> R_supply -> L_loop -> head rail <- (ESR + bulk C); 14 heaters (each R_heater) switched to ground, all pulsed together
(worst case: all 14 primitives of one address), repeated once per address for a whole column."""
import os
import re
import subprocess
import tempfile
import design as d

RON = 0.05           # ohm, switch on-resistance (CHOICE: a modest logic-level MOSFET; the real part is not selected)


def netlist(c_f, esr=0.0, r_supply=0.0, l_loop=0.0, n_pulses=1, period_s=None):
    period = period_s or d.per_address_time_s()
    lines = ["* open-inkjet head power stage (assumed head parameters, see electronics/design.py)",
             "Vsup nsup 0 DC %g" % d.V_HEAD]
    lines.append("Rsup nsup nl %g" % max(r_supply, 1e-6))
    lines.append("Lloop nl vh %g" % max(l_loop, 1e-12))
    lines.append("Resr vh ncap %g" % max(esr, 1e-6))
    lines.append("Cbulk ncap 0 %g IC=%g" % (c_f, d.V_HEAD))
    for k in range(d.N_PRIM):
        lines.append("S%d vh n%d ctl 0 swm" % (k, k))
        lines.append("Rh%d n%d 0 %g" % (k, k, d.R_HEATER))
    lines.append("Vctl ctl 0 PULSE(0 1 1u 5n 5n %g %g %d)" % (d.T_PULSE_S, period, n_pulses))
    lines.append(".model swm SW(Vt=0.5 Vh=0.1 Ron=%g Roff=1e9)" % RON)
    t_end = 1e-6 + n_pulses * period + 5e-6
    lines.append(".ic v(vh)=%g v(ncap)=%g" % (d.V_HEAD, d.V_HEAD))
    lines.append(".tran 2n %g uic" % t_end)
    lines.append(".control\nrun\nmeas tran vmin MIN v(vh)\nmeas tran ipk MIN i(Vsup)\nmeas tran vend FIND v(vh) AT=%g\nquit\n.endc\n.end" % (t_end - 1e-7))
    return "\n".join(lines)


def run(c_f, **kw):
    """Returns dict(vmin, droop_fraction, supply_peak_a, vend)."""
    with tempfile.TemporaryDirectory() as dd:
        path = os.path.join(dd, "ps.cir")
        open(path, "w").write(netlist(c_f, **kw))
        r = subprocess.run(["ngspice", "-b", path], capture_output=True, text=True, timeout=120)
    out = r.stdout + r.stderr
    vals = {}
    for name in ("vmin", "ipk", "vend"):
        m = re.search(r"^%s\s*=\s*([-+0-9.eE]+)" % name, out, re.M)
        if not m:
            raise RuntimeError("ngspice gave no %s:\n%s" % (name, out[-1500:]))
        vals[name] = float(m.group(1))
    return dict(vmin=vals["vmin"], droop_fraction=(d.V_HEAD - vals["vmin"]) / d.V_HEAD, supply_peak_a=abs(vals["ipk"]), vend=vals["vend"])


ISOLATED = dict(r_supply=1e9)          # supply effectively disconnected: only the capacitor delivers charge (the worst case the formulas assume)
REALISTIC = dict(esr=0.02, r_supply=0.05, l_loop=100e-9)   # ASSUMED: 20 mohm ESR, 50 mohm supply+wiring, 100 nH loop


if __name__ == "__main__":
    for label, kw in [("single worst pulse, isolated cap, per-pulse minimum C", dict(c_f=d.bulk_capacitance_f(), **ISOLATED)),
                      ("full column, isolated cap, 400 uF", dict(c_f=d.column_capacitance_f(), n_pulses=d.N_ADDR, **ISOLATED)),
                      ("full column, isolated cap, per-pulse minimum C", dict(c_f=d.bulk_capacitance_f(), n_pulses=d.N_ADDR, **ISOLATED)),
                      ("single pulse, big C, ESR 150 mohm (budget 107)", dict(c_f=2200e-6, esr=0.15, **ISOLATED)),
                      ("single pulse, big C, ESR 50 mohm", dict(c_f=2200e-6, esr=0.05, **ISOLATED)),
                      ("full column, realistic supply, 470 uF", dict(c_f=470e-6, esr=0.02, r_supply=0.05, l_loop=100e-9, n_pulses=d.N_ADDR)),
                      ("full column, realistic supply, 1000 uF", dict(c_f=1000e-6, esr=0.02, r_supply=0.05, l_loop=100e-9, n_pulses=d.N_ADDR)),
                      ("full column, realistic supply, per-pulse minimum C", dict(c_f=d.bulk_capacitance_f(), esr=0.02, r_supply=0.05, l_loop=100e-9, n_pulses=d.N_ADDR))]:
        r = run(**kw)
        print("%-55s droop %.1f%%  vmin %.2f V  supply peak %.2f A" % (label, 100 * r["droop_fraction"], r["vmin"], r["supply_peak_a"]))
