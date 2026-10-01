# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Block-level netlist for the controller and head-drive board, with pin types and electrical-rule checks.

Scope: MCU pin map, the 74HC595 chain (per chip: power, clock, latch, enable, clear, serial in/out), the 40 shift-register
outputs mapped onto the head's 22 address + 14 primitive lines, pull resistors that fix the safe state, and the 52-contact head
connector. It does NOT model the analog driver stage internals (MOSFETs, level shifting, current limiting): that needs the bench
measurements in docs/BENCH.md first. Driver stages appear as blocks with an input, an output and a supply pin.

Pin kinds: 'out' drives its net, 'in' needs a driver on its net, 'pwr' is a supply/ground pin (net must be a power net),
'src' is a power source, 'pass' is passive (head contact, resistor, testpoint, switch)."""
from design import N_ADDR, N_PRIM, SR_BITS, shift_register_count, HEAD_CONTACTS

# MCU (RP2040 / Pico) GPIO assignment: signal -> GPIO number. Mirrors firmware/board/rp2040/board_config.h.
MCU_PINS = {
    "SR_SCK": 18, "SR_MOSI": 19, "SR_RCLK": 20, "SR_OE_N": 21,
    "ENC_A": 2, "ENC_B": 3,
    "CAR_STEP": 4, "CAR_DIR": 5, "CAR_EN_N": 6,
    "FEED_STEP": 7, "FEED_DIR": 8, "FEED_EN_N": 9,
    "PAPER_SENSE": 10, "HOME_LEFT": 11, "HOME_RIGHT": 12,
    "CAP_PWM": 13, "WIPE_PWM": 14,
    "LED": 25,
}
MCU_OUTPUTS = {"SR_SCK", "SR_MOSI", "SR_RCLK", "SR_OE_N", "CAR_STEP", "CAR_DIR", "CAR_EN_N", "FEED_STEP", "FEED_DIR",
               "FEED_EN_N", "CAP_PWM", "WIPE_PWM", "LED"}
SR_PINS = {"VCC": "pwr", "GND": "pwr", "SRCLK": "in", "RCLK": "in", "OE_N": "in", "SRCLR_N": "in", "SER": "in", "QH_OUT": "out"}
SR_OUT_PINS = ["Q" + c for c in "ABCDEFGH"]


class Netlist:
    def __init__(self):
        self.nets = {}          # net -> [(comp, pin)]
        self.kind = {}          # (comp, pin) -> kind
        self.components = {}    # comp -> set of expected pins (all must be connected)

    def declare(self, comp, pins):
        self.components.setdefault(comp, set()).update(pins)

    def add(self, net, comp, pin, kind):
        self.nets.setdefault(net, []).append((comp, pin))
        self.kind[(comp, pin)] = kind


def build():
    nl = Netlist()
    n_sr = shift_register_count()

    # --- MCU
    for sig, gpio in MCU_PINS.items():
        nl.add(sig, "MCU", "GP%d" % gpio, "out" if sig in MCU_OUTPUTS else "in")
    nl.add("V3V3", "MCU", "3V3_OUT", "src")
    nl.add("GND", "MCU", "GND", "pwr")

    # --- peripherals on MCU nets
    for sig, (comp, pin, kind) in {
        "ENC_A": ("ENC", "A", "out"), "ENC_B": ("ENC", "B", "out"),
        "CAR_STEP": ("DRV_CAR", "STEP", "in"), "CAR_DIR": ("DRV_CAR", "DIR", "in"), "CAR_EN_N": ("DRV_CAR", "EN_N", "in"),
        "FEED_STEP": ("DRV_FEED", "STEP", "in"), "FEED_DIR": ("DRV_FEED", "DIR", "in"), "FEED_EN_N": ("DRV_FEED", "EN_N", "in"),
        "PAPER_SENSE": ("PAPER_OPTO", "OUT", "out"), "HOME_LEFT": ("SW_LEFT", "NO", "out"), "HOME_RIGHT": ("SW_RIGHT", "NO", "out"),
        "CAP_PWM": ("CAP_ACT", "SIG", "in"), "WIPE_PWM": ("WIPE_ACT", "SIG", "in"), "LED": ("LED1", "A", "pass")}.items():
        nl.add(sig, comp, pin, kind)

    # --- 74HC595 chain: SCK/RCLK/OE_N shared by all chips, SER chained, CLR tied high, power per chip
    for i in range(1, n_sr + 1):
        sr = "SR%d" % i
        nl.declare(sr, list(SR_PINS) + SR_OUT_PINS)
        nl.add("SR_SCK", sr, "SRCLK", "in")
        nl.add("SR_RCLK", sr, "RCLK", "in")
        nl.add("SR_OE_N", sr, "OE_N", "in")
        nl.add("V3V3", sr, "SRCLR_N", "in")                       # clear held inactive (tied to VCC)
        nl.add("V3V3", sr, "VCC", "pwr")
        nl.add("GND", sr, "GND", "pwr")
        nl.add("SR_MOSI" if i == 1 else "SR_CHAIN%d" % (i - 1), sr, "SER", "in")
        if i < n_sr:
            nl.add("SR_CHAIN%d" % i, sr, "QH_OUT", "out")
        else:
            nl.add("SR_CHAIN_END", sr, "QH_OUT", "out")
            nl.add("SR_CHAIN_END", "TESTPOINT", "TP_CHAIN", "pass")
    # safe state: OE_N pulled high (outputs high-Z), SR outputs pulled down at the driver inputs
    nl.add("SR_OE_N", "R_OE_PULLUP", "1", "pass"); nl.add("V3V3", "R_OE_PULLUP", "2", "pass")

    # --- outputs: ADDR0..21 then PRIM0..13 then spares, allocated in shift order (bit i = output i)
    outputs = ["ADDR%d" % k for k in range(N_ADDR)] + ["PRIM%d" % k for k in range(N_PRIM)]
    outputs += ["SR_SPARE%d" % k for k in range(n_sr * SR_BITS - len(outputs))]
    for idx, sig in enumerate(outputs):
        sr, q = "SR%d" % (idx // SR_BITS + 1), SR_OUT_PINS[idx % SR_BITS]
        nl.add(sig, sr, q, "out")
        if sig.startswith("SR_SPARE"):
            nl.add(sig, "TESTPOINT", "SP%d" % int(sig[8:]), "pass")
            continue
        kind, n = ("ADDR", int(sig[4:])) if sig.startswith("ADDR") else ("PRIM", int(sig[4:]))
        drv = "%s_DRV%d" % (kind, n)
        nl.declare(drv, ["IN", "OUT", "VIN", "GND"])
        nl.add(sig, drv, "IN", "in")
        nl.add(sig, "R_PD_" + sig, "1", "pass"); nl.add("GND", "R_PD_" + sig, "2", "pass")   # pull-down: driver off while OE_N high
        nl.add("HEAD_" + sig, drv, "OUT", "out")
        nl.add("HEAD_" + sig, "J_HEAD", ("A%d" if kind == "ADDR" else "P%d") % n, "pass")
        nl.add("V_HEAD", drv, "VIN", "pwr")
        nl.add("GND", drv, "GND", "pwr")
    for k in range(N_PRIM):                                   # primitive commons return to one pad each
        nl.add("PCOM%d" % k, "J_HEAD", "C%d" % k, "pass")
        nl.add("PCOM%d" % k, "PWR_GND", "PAD%d" % k, "pass")
    for k in range(HEAD_CONTACTS - N_ADDR - 2 * N_PRIM):      # unknown-function contacts: test points only
        nl.add("HEAD_UNKNOWN%d" % k, "J_HEAD", "U%d" % k, "pass")
        nl.add("HEAD_UNKNOWN%d" % k, "TESTPOINT", "TP%d" % k, "pass")

    # --- power
    nl.add("V_HEAD", "PSU", "12V", "src"); nl.add("V_HEAD", "F1", "OUT", "pass"); nl.add("V_HEAD", "C_BULK", "+", "pass")
    nl.add("GND", "PSU", "GND", "pwr"); nl.add("GND", "C_BULK", "-", "pass")
    for comp in ("PAPER_OPTO", "DRV_CAR", "DRV_FEED"):
        nl.add("V3V3", comp, "VCC", "pwr"); nl.add("GND", comp, "GND", "pwr")
    return nl


POWER_NETS = {"V3V3", "V_HEAD", "GND"}


def check(nl=None):
    """ERC rules. Returns a list of violation strings (empty = pass)."""
    nl = build() if nl is None else nl
    bad, seen = [], {}
    for net, pins in nl.nets.items():
        if len(pins) < 2:
            bad.append("net %s has %d pin(s): floating" % (net, len(pins)))
        if len(set(pins)) != len(pins):
            bad.append("net %s lists a pin twice" % net)
        for p in pins:
            if p in seen and seen[p] != net:
                bad.append("pin %s.%s on two nets: %s and %s" % (p[0], p[1], seen[p], net))
            seen[p] = net
        kinds = [nl.kind.get(p, "pass") for p in pins]
        drivers = kinds.count("out") + kinds.count("src")
        if net not in POWER_NETS:
            if drivers > 1:
                bad.append("net %s has %d drivers" % (net, drivers))
            if "in" in kinds and drivers == 0:
                bad.append("net %s has an input but no driver" % net)
            if "pwr" in kinds or "src" in kinds:
                bad.append("power pin on signal net %s" % net)
        else:
            if "out" in kinds:                                  # inputs may be tied to a rail (e.g. SRCLR_N); outputs may not
                bad.append("output pin driving power net %s" % net)
            if net in ("V3V3", "V_HEAD") and "src" not in kinds:
                bad.append("supply net %s has no source" % net)
    # every declared component pin must be connected
    connected = set(seen)
    for comp, pins in nl.components.items():
        for pin in pins:
            if (comp, pin) not in connected:
                bad.append("%s.%s is unconnected" % (comp, pin))
    # power pins must be on power nets
    for (comp, pin), kind in nl.kind.items():
        if kind in ("pwr", "src") and seen.get((comp, pin)) not in POWER_NETS:
            bad.append("%s.%s (power) is not on a power net" % (comp, pin))
    # GPIO uniqueness and exact MCU map
    gpios = [p[1] for pins in nl.nets.values() for p in pins if p[0] == "MCU" and p[1].startswith("GP")]
    if len(gpios) != len(set(gpios)):
        bad.append("MCU GPIO used twice")
    # safe-state pull resistors must exist
    if ("R_OE_PULLUP", "1") not in seen or seen[("R_OE_PULLUP", "1")] != "SR_OE_N":
        bad.append("OE_N has no pull-up to keep outputs off in reset")
    for k in range(N_ADDR):
        if ("R_PD_ADDR%d" % k, "1") not in seen:
            bad.append("ADDR%d has no pull-down" % k)
    for k in range(N_PRIM):
        if ("R_PD_PRIM%d" % k, "1") not in seen:
            bad.append("PRIM%d has no pull-down" % k)
    # head connector contact name must match its net function (catches swapped contacts)
    for net, pins in nl.nets.items():
        for comp, pin in pins:
            if comp != "J_HEAD":
                continue
            if net.startswith("HEAD_ADDR") and pin != "A" + net[len("HEAD_ADDR"):]:
                bad.append("head contact %s is on %s" % (pin, net))
            if net.startswith("HEAD_PRIM") and pin != "P" + net[len("HEAD_PRIM"):]:
                bad.append("head contact %s is on %s" % (pin, net))
    # chain continuity: walk SER <- QH_OUT from the MCU MOSI net through every chip
    ser_net = {c: seen.get((c, "SER")) for c in nl.components if c.startswith("SR")}
    chips, cur = [], "SR_MOSI"
    for _ in range(len(ser_net) + 1):
        nxt = [c for c, n in ser_net.items() if n == cur]
        if not nxt:
            break
        chips.append(nxt[0])
        cur = seen.get((nxt[0], "QH_OUT"))
    if len(chips) != len(ser_net):
        bad.append("shift register chain broken: reached %d of %d chips" % (len(chips), len(ser_net)))
    return bad


def head_line_for_output(nl, chip_index, out_index):
    """Which head line a shift-register output ends up on: returns e.g. 'ADDR5' / 'PRIM3' / 'SR_SPARE0'."""
    comp, pin = "SR%d" % (chip_index + 1), SR_OUT_PINS[out_index]
    for net, pins in nl.nets.items():
        if (comp, pin) in pins:
            return net
    return None


if __name__ == "__main__":
    n = build()
    print("nets:", len(n.nets), "violations:", check(n))
