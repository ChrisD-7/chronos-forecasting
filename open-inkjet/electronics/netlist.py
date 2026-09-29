# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Block-level netlist for the controller and head-drive board, with electrical-rule-style checks.

Scope: which MCU pin goes where, how the 40 shift-register outputs map onto the head's 22 address + 14 primitive lines, and
the head connector. It does NOT model the analog driver stage (MOSFETs, level shifting, current limiting): that needs the
bench measurements in docs/BENCH.md first. MCU pin numbers here are compared with firmware/board/rp2040/board_config.h by
test_electronics.py."""
from design import N_ADDR, N_PRIM, SR_BITS, shift_register_count, HEAD_CONTACTS

# MCU (RP2040 / Pico) GPIO assignment: signal -> GPIO number. Mirrors board_config.h.
MCU_PINS = {
    "SR_SCK": 18, "SR_MOSI": 19, "SR_RCLK": 20, "SR_OE_N": 21,
    "ENC_A": 2, "ENC_B": 3,
    "CAR_STEP": 4, "CAR_DIR": 5, "CAR_EN_N": 6,
    "FEED_STEP": 7, "FEED_DIR": 8, "FEED_EN_N": 9,
    "PAPER_SENSE": 10, "HOME_LEFT": 11, "HOME_RIGHT": 12,
    "CAP_PWM": 13, "WIPE_PWM": 14,
    "LED": 25,
}


def build():
    """Return {net_name: [(component, pin), ...]}."""
    nets = {}

    def add(net, comp, pin):
        nets.setdefault(net, []).append((comp, pin))

    # MCU pins to their peripherals
    peripherals = {"SR_SCK": ("SR1", "SRCLK"), "SR_MOSI": ("SR1", "SER"), "SR_RCLK": ("SR_ALL", "RCLK"), "SR_OE_N": ("SR_ALL", "OE_N"),
                   "ENC_A": ("ENC", "A"), "ENC_B": ("ENC", "B"),
                   "CAR_STEP": ("DRV_CAR", "STEP"), "CAR_DIR": ("DRV_CAR", "DIR"), "CAR_EN_N": ("DRV_CAR", "EN_N"),
                   "FEED_STEP": ("DRV_FEED", "STEP"), "FEED_DIR": ("DRV_FEED", "DIR"), "FEED_EN_N": ("DRV_FEED", "EN_N"),
                   "PAPER_SENSE": ("PAPER_OPTO", "OUT"), "HOME_LEFT": ("SW_LEFT", "NO"), "HOME_RIGHT": ("SW_RIGHT", "NO"),
                   "CAP_PWM": ("CAP_ACT", "SIG"), "WIPE_PWM": ("WIPE_ACT", "SIG"), "LED": ("LED1", "A")}
    for sig, gpio in MCU_PINS.items():
        add(sig, "MCU", "GP%d" % gpio)
        add(sig, *peripherals[sig])

    # Shift register chain: SR1.QH' -> SR2.SER ... ; outputs allocated ADDR0..21 then PRIM0..13 then spares
    n_sr = shift_register_count()
    for i in range(1, n_sr):
        add("SR_CHAIN%d" % i, "SR%d" % i, "QH_SER_OUT")
        add("SR_CHAIN%d" % i, "SR%d" % (i + 1), "SER")
    outputs = ["ADDR%d" % k for k in range(N_ADDR)] + ["PRIM%d" % k for k in range(N_PRIM)]
    outputs += ["SR_SPARE%d" % k for k in range(n_sr * SR_BITS - len(outputs))]
    for idx, sig in enumerate(outputs):
        sr, bit = "SR%d" % (idx // SR_BITS + 1), "Q%s" % "ABCDEFGH"[idx % SR_BITS]
        add(sig, sr, bit)
        if sig.startswith("SR_SPARE"):
            add(sig, "TESTPOINT", "SP%d" % int(sig[8:]))              # spare outputs brought out to test points
        if sig.startswith("ADDR"):
            add(sig, "ADDR_DRV%d" % int(sig[4:]), "IN")
            add("HEAD_" + sig, "ADDR_DRV%d" % int(sig[4:]), "OUT")
            add("HEAD_" + sig, "J_HEAD", "A%d" % int(sig[4:]))
        elif sig.startswith("PRIM"):
            add(sig, "PRIM_DRV%d" % int(sig[4:]), "IN")
            add("HEAD_" + sig, "PRIM_DRV%d" % int(sig[4:]), "OUT")
            add("HEAD_" + sig, "J_HEAD", "P%d" % int(sig[4:]))
    for k in range(N_PRIM):                                   # primitive commons return to the driver ground/sense node
        add("PCOM%d" % k, "J_HEAD", "C%d" % k)
        add("PCOM%d" % k, "PWR_GND", "PAD%d" % k)                 # one return pad per common (no shared pin)
    # remaining head contacts: unknown function, deliberately left unconnected until measured
    for k in range(HEAD_CONTACTS - N_ADDR - 2 * N_PRIM):
        add("HEAD_UNKNOWN%d" % k, "J_HEAD", "U%d" % k)
        add("HEAD_UNKNOWN%d" % k, "TESTPOINT", "TP%d" % k)
    # power
    for comp, pin in [("SR_ALL", "VCC"), ("MCU", "3V3"), ("PAPER_OPTO", "VCC")]:
        add("V3V3", comp, pin)
    for k in range(N_PRIM):
        add("V_HEAD", "PRIM_DRV%d" % k, "VIN")
    add("V_HEAD", "PSU", "12V")
    add("V_HEAD", "C_BULK", "+")
    add("V_HEAD", "F1", "OUT")
    add("GND", "PSU", "GND")
    add("GND", "C_BULK", "-")
    return nets


def check(nets=None):
    """ERC-style rules. Returns a list of violation strings (empty = pass)."""
    nets = build() if nets is None else nets
    bad = []
    seen = {}
    for net, pins in nets.items():
        if len(pins) < 2:
            bad.append("net %s has %d pin(s): floating" % (net, len(pins)))
        for p in pins:
            if p in seen and seen[p] != net and not (p[0] == "MCU" and False):
                bad.append("pin %s.%s on two nets: %s and %s" % (p[0], p[1], seen[p], net))
            seen[p] = net
        if len(set(pins)) != len(pins):
            bad.append("net %s lists a pin twice" % net)
    gpios = [p[1] for pins in nets.values() for p in pins if p[0] == "MCU" and p[1].startswith("GP")]
    if len(gpios) != len(set(gpios)):
        bad.append("MCU GPIO used twice")
    for req in ("V_HEAD", "GND", "V3V3"):
        if req not in nets:
            bad.append("missing power net " + req)
    return bad


if __name__ == "__main__":
    n = build()
    print("nets:", len(n), "violations:", check(n))
