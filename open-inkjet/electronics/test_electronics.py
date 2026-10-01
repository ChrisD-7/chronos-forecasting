# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
import copy
import os
import re
import pytest
import design as d
import netlist as n

BOARD = os.path.join(os.path.dirname(__file__), "..", "firmware", "board", "rp2040", "board_config.h")
BOARD_C = os.path.join(os.path.dirname(__file__), "..", "firmware", "board", "rp2040", "oi_board.c")


def test_calculations_match_hand_arithmetic():
    assert d.heater_current_a() == pytest.approx(0.4)                       # 12 V / 30 ohm
    assert d.pulse_energy_j() == pytest.approx(9.6e-6)                      # 12^2/30 * 2 us
    assert d.peak_current_a() == pytest.approx(5.6)                         # 14 heaters at once
    assert d.bulk_capacitance_f() == pytest.approx(5.6 * 2e-6 / (12 * 0.05))   # per-pulse: 18.7 uF
    assert d.column_charge_c() == pytest.approx(300 * 0.4 * 2e-6)           # 240 uC per fully inked column
    assert d.column_capacitance_f() == pytest.approx(240e-6 / 0.6)          # 400 uF with no recharge
    assert d.esr_budget_ohm() == pytest.approx(0.6 / 5.6)                   # 107 mohm
    assert d.shift_register_count() == 5 and d.shift_register_count(40) == 5 and d.shift_register_count(41) == 6


def test_spi_baud_matches_pico_sdk_algorithm():
    # hand-derived from spi_set_baudrate(): prescale even, postdiv 1..256, largest rate <= request
    assert d.rp2040_spi_hz(25_000_000, 125_000_000) == pytest.approx(125e6 / 6)       # 20.83 MHz, NOT 25 MHz
    assert d.rp2040_spi_hz(25_000_000, 150_000_000) == pytest.approx(25e6)            # Pico 2 can do 25 MHz
    assert d.rp2040_spi_hz(10_000_000, 125_000_000) == pytest.approx(125e6 / 14)      # 8.93 MHz
    for req in (1e6, 3.3e6, 10e6, 12.5e6):
        assert d.rp2040_spi_hz(req) <= req


def test_head_line_budget_is_consistent():
    assert d.N_ADDR + d.N_PRIM == 36 and 36 <= d.shift_register_count() * 8
    assert d.head_contact_budget() == 2                                    # 52 - 22 - 28 : two contacts of unknown function
    assert d.RP2040_USABLE_GPIO < d.N_ADDR + d.N_PRIM                       # why shift registers are needed at all
    assert len(n.MCU_PINS) - 1 <= d.RP2040_USABLE_GPIO                      # everything else fits on the MCU (LED excluded)


def test_timing_budget_supports_the_configured_carriage_speed():
    v_cfg = 18_000 * 2 / 4                                                  # 9000 counts/s at 2 counts per dot
    assert d.max_carriage_speed_counts_s(2) > v_cfg                         # worst-case fully inked columns still fit
    assert d.worst_case_column_time_s() < 1 / (v_cfg / 2)                   # column time < column period (222 us)
    assert d.max_column_rate_hz() < d.F_FIRE_MAX                            # the SPI-driven sequence is the binding limit
    assert d.per_address_time_s() == pytest.approx(5 * 8 / d.SPI_HZ + d.LATCH_S + d.SETTLE_S + d.T_PULSE_S + d.GAP_S)


def test_netlist_passes_erc_rules():
    assert n.check() == []


# ---- defect injection: each defect must be caught by the rules or by the firmware-order test ----
def _mutate(fn):
    nl = n.build(); fn(nl); return n.check(nl)


def _move(nl, pin_a, pin_b):
    """Swap the nets of two pins."""
    na = [net for net, p in nl.nets.items() if pin_a in p][0]
    nb = [net for net, p in nl.nets.items() if pin_b in p][0]
    nl.nets[na] = [pin_b if p == pin_a else p for p in nl.nets[na]]
    nl.nets[nb] = [pin_a if p == pin_b else p for p in nl.nets[nb]]


@pytest.mark.parametrize("name,fn,expect", [
    ("floating net", lambda nl: nl.nets.__setitem__("ADDR3", nl.nets["ADDR3"][:1]), "floating"),
    ("pin on two nets", lambda nl: (nl.nets.__setitem__("EXTRA", [("MCU", "GP4"), ("X", "1")]), nl.kind.__setitem__(("X", "1"), "in")), "two nets"),
    ("missing ground", lambda nl: nl.nets.__setitem__("GND", [p for p in nl.nets["GND"] if p[0] != "SR2"]), "SR2.GND"),
    ("swapped head contacts A3/A4", lambda nl: _move(nl, ("J_HEAD", "A3"), ("J_HEAD", "A4")), "head contact"),
    ("broken chain", lambda nl: nl.nets.__setitem__("SR_CHAIN2", [p for p in nl.nets["SR_CHAIN2"] if p != ("SR3", "SER")]), "SR3.SER"),
    ("unclocked chip", lambda nl: nl.nets.__setitem__("SR_SCK", [p for p in nl.nets["SR_SCK"] if p[0] != "SR4"]), "SR4.SRCLK"),
    ("clear left floating", lambda nl: nl.nets.__setitem__("V3V3", [p for p in nl.nets["V3V3"] if p != ("SR2", "SRCLR_N")]), "SR2.SRCLR_N"),
    ("unpowered primitive driver", lambda nl: nl.nets.__setitem__("V_HEAD", [p for p in nl.nets["V_HEAD"] if p != ("PRIM_DRV3", "VIN")]), "PRIM_DRV3.VIN"),
    ("no OE_N pull-up", lambda nl: nl.nets.__setitem__("SR_OE_N", [p for p in nl.nets["SR_OE_N"] if p[0] != "R_OE_PULLUP"]), "pull-up"),
    ("missing output pull-down", lambda nl: nl.nets.__setitem__("PRIM5", [p for p in nl.nets["PRIM5"] if p[0] != "R_PD_PRIM5"]), "no pull-down"),
    ("two drivers on a net", lambda nl: (nl.nets["ENC_A"].append(("SR1", "QH_OUT")), nl.kind.__setitem__(("SR1", "QH_OUT"), "out")), "drivers"),
    ("input with no driver", lambda nl: (nl.nets.__setitem__("CAR_STEP", [p for p in nl.nets["CAR_STEP"] if p[0] != "MCU"] + [("T", "1")]), nl.kind.__setitem__(("T", "1"), "pass")), "no driver"),
    ("supply without source", lambda nl: nl.nets.__setitem__("V_HEAD", [p for p in nl.nets["V_HEAD"] if p[0] != "PSU"]), "no source"),
])
def test_erc_detects_defect(name, fn, expect):
    violations = _mutate(fn)
    assert any(expect in v for v in violations), (name, violations)


# ---- firmware bit order <-> netlist: simulate the real shift sequence of oi_board.c ----
def _shift_chain(bytes_sent, n_chips):
    """74HC595 chain model: each byte clocked MSB first; after 8 clocks the first byte sits in the farthest chip."""
    regs = [[0] * 8 for _ in range(n_chips)]            # regs[chip][bit] with bit0 = QA (the LAST bit shifted in)
    for byte in bytes_sent:
        for k in range(7, -1, -1):                       # MSB first
            bit = (byte >> k) & 1
            carry = bit
            for c in range(n_chips):                     # shift every chip by one: QA <- carry, carry <- old QH
                old_qh = regs[c][7]
                regs[c] = [carry] + regs[c][:7]
                carry = old_qh
    return regs


def _firmware_bytes(word, n_chips):
    """Mirror of sr_shift_and_latch(): farthest register first."""
    return [(word >> (8 * (n_chips - 1 - i))) & 0xFF for i in range(n_chips)]


def test_firmware_word_layout_lands_on_the_intended_head_lines():
    nl = n.build(); chips = d.shift_register_count()
    for addr in range(d.N_ADDR):
        for prim_mask in (0b1, 0b10000000000001, 0b10101010101010):
            word = (1 << addr) | (prim_mask << d.N_ADDR)                       # oi_board.c: address one-hot, primitives above
            regs = _shift_chain(_firmware_bytes(word, chips), chips)
            lit = sorted(n.head_line_for_output(nl, c, b) for c in range(chips) for b in range(8) if regs[c][b])
            want = sorted(["ADDR%d" % addr] + ["PRIM%d" % p for p in range(d.N_PRIM) if prim_mask >> p & 1])
            assert lit == want, (addr, prim_mask, lit, want)


def test_firmware_order_test_detects_swapped_shift_register_outputs():
    nl = n.build()
    _move(nl, ("SR1", "QF"), ("SR3", "QB"))               # ADDR5 <-> PRIM(...): a miswired board
    chips = d.shift_register_count()
    word = (1 << 5)
    regs = _shift_chain(_firmware_bytes(word, chips), chips)
    lit = [n.head_line_for_output(nl, c, b) for c in range(chips) for b in range(8) if regs[c][b]]
    assert lit != ["ADDR5"]


def test_board_source_uses_the_modelled_byte_order_and_settle_before_oe():
    src = open(BOARD_C).read()
    assert "word >> (8 * (OI_SR_COUNT - 1 - i))" in src                        # the order the model above mirrors
    assert src.index("sr_shift_and_latch(sr_word)") < src.index("OI_SETTLE_NS") < src.index("gpio_put(PIN_SR_OE_N, 0)")


def test_board_config_header_matches_netlist_pins():
    text = open(BOARD).read()
    found = dict((m.group(1), int(m.group(2))) for m in re.finditer(r"#define\s+PIN_(\w+)\s+(\d+)", text))
    assert found == n.MCU_PINS


def test_board_config_constants_match_design():
    text = open(BOARD).read()
    assert re.search(r"#define\s+OI_SR_COUNT\s+%d\b" % d.shift_register_count(), text)
    assert re.search(r"#define\s+OI_N_ADDR\s+%d\b" % d.N_ADDR, text)
    assert re.search(r"#define\s+OI_N_PRIM\s+%d\b" % d.N_PRIM, text)
    assert re.search(r"#define\s+OI_SPI_HZ\s+%du\b" % d.SPI_REQUEST_HZ, text)
    assert re.search(r"#define\s+OI_SETTLE_NS\s+%du\b" % round(d.SETTLE_S * 1e9), text)


# ---- circuit simulation (ngspice) of the head power stage, ASSUMED head parameters ----
import shutil
import spice_sim as sim

needs_ngspice = pytest.mark.skipif(shutil.which("ngspice") is None, reason="needs ngspice")


@needs_ngspice
def test_spice_confirms_the_per_pulse_capacitor_formula():
    r = sim.run(d.bulk_capacitance_f(), **sim.ISOLATED)                       # only the capacitor supplies one worst-case pulse
    assert r["droop_fraction"] == pytest.approx(d.DROOP_MAX, abs=0.01)        # the formula says 5%; the simulator agrees (heater current falls a little)
    assert r["supply_peak_a"] < 0.01                                          # (supply really was isolated)


@needs_ngspice
def test_spice_shows_the_per_column_bound_and_that_the_per_pulse_minimum_is_not_enough():
    col = sim.run(d.column_capacitance_f(), n_pulses=d.N_ADDR, **sim.ISOLATED)
    assert col["droop_fraction"] == pytest.approx(d.DROOP_MAX, abs=0.01)      # 400 uF holds a fully inked column to about 5% with no recharge
    small = sim.run(d.bulk_capacitance_f(), n_pulses=d.N_ADDR, **sim.ISOLATED)
    assert small["droop_fraction"] > 0.5                                      # 18.7 uF with no recharge: the rail collapses over a column


@needs_ngspice
def test_spice_confirms_the_esr_budget():
    over = sim.run(2200e-6, esr=0.15, **sim.ISOLATED)                         # 150 mohm: above the 107 mohm budget
    under = sim.run(2200e-6, esr=0.05, **sim.ISOLATED)
    assert over["droop_fraction"] > d.DROOP_MAX > under["droop_fraction"]
    assert under["droop_fraction"] == pytest.approx(5.6 * 0.05 / d.V_HEAD, abs=0.01)    # I x ESR / V


@needs_ngspice
def test_spice_with_a_stiff_supply_a_modest_capacitor_holds_the_rail():
    """ASSUMED supply: 50 mohm + 100 nH + 20 mohm ESR. This is a statement about that assumption, not about a real PSU."""
    for c in (470e-6, 1000e-6):
        r = sim.run(c, n_pulses=d.N_ADDR, **sim.REALISTIC)
        assert r["droop_fraction"] < d.DROOP_MAX
    assert sim.run(d.bulk_capacitance_f(), n_pulses=d.N_ADDR, **sim.REALISTIC)["supply_peak_a"] > 1.0   # the supply, not the cap, then carries the load


@needs_ngspice
def test_spice_numbers_quoted_in_the_docs():
    small = sim.run(d.bulk_capacitance_f(), n_pulses=d.N_ADDR, **sim.REALISTIC)["droop_fraction"]
    big = sim.run(470e-6, n_pulses=d.N_ADDR, **sim.REALISTIC)["droop_fraction"]
    assert 0.030 < small < 0.040 and big < small and 0.010 < big < 0.016           # docs: 3.5% and 1.3% (stiff supply assumption)
    at_budget = sim.run(2200e-6, esr=d.esr_budget_ohm(), **sim.ISOLATED)["droop_fraction"]
    assert at_budget == pytest.approx(0.048, abs=0.006)                           # right at the 107 mohm budget: just under 5%


@needs_ngspice
def test_spice_conclusions_are_fragile_to_loop_inductance_and_supply_resistance():
    """Review finding: '18.7 uF is enough with a stiff supply' only holds for low inductance / resistance; 470 uF is robust."""
    small_l = lambda l: sim.run(d.bulk_capacitance_f(), n_pulses=d.N_ADDR, esr=0.02, r_supply=0.05, l_loop=l)["droop_fraction"]
    small_r = lambda r: sim.run(d.bulk_capacitance_f(), n_pulses=d.N_ADDR, esr=0.02, r_supply=r, l_loop=100e-9)["droop_fraction"]
    assert small_l(10e-9) < small_l(100e-9) < d.DROOP_MAX < small_l(1e-6)         # 1 uH of loop already breaks the 5% target
    assert small_r(0.05) < d.DROOP_MAX < small_r(0.5)                              # so does 0.5 ohm of supply resistance
    worst = sim.run(470e-6, n_pulses=d.N_ADDR, esr=0.02, r_supply=5.0, l_loop=5e-6)["droop_fraction"]
    assert worst <= d.DROOP_MAX                                                    # 470 uF stays within 5% even for 5 ohm and 5 uH


@needs_ngspice
def test_spice_load_really_switches():
    """The stiff-supply tests could pass vacuously if nothing switched on: the supply must carry the pulses and the rail must dip."""
    r = sim.run(470e-6, n_pulses=d.N_ADDR, **sim.REALISTIC)
    assert r["supply_peak_a"] > 1.0 and r["vmin"] < d.V_HEAD - 0.05
