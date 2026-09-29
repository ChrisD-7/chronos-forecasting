# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
import math
import os
import re
import pytest
import design as d
import netlist as n

BOARD = os.path.join(os.path.dirname(__file__), "..", "firmware", "board", "rp2040", "board_config.h")


def test_calculations_match_hand_arithmetic():
    assert d.heater_current_a() == pytest.approx(0.4)                       # 12 V / 30 ohm
    assert d.pulse_energy_j() == pytest.approx(9.6e-6)                      # 12^2/30 * 2 us
    assert d.peak_current_a() == pytest.approx(5.6)                         # 14 heaters at once
    assert d.bulk_capacitance_f() == pytest.approx(5.6 * 2e-6 / (12 * 0.05))   # Q / (V * droop) = 18.7 uF
    assert d.shift_register_count() == 5 and d.shift_register_count(40) == 5 and d.shift_register_count(41) == 6


def test_head_line_budget_is_consistent():
    assert d.N_ADDR + d.N_PRIM == 36 and 36 <= d.shift_register_count() * 8
    assert d.head_contact_budget() == 2                                    # 52 - 22 - 28 : two contacts of unknown function
    assert d.RP2040_USABLE_GPIO < d.N_ADDR + d.N_PRIM                       # why shift registers are needed at all
    assert len(n.MCU_PINS) - 1 <= d.RP2040_USABLE_GPIO                      # everything else fits on the MCU (LED excluded)


def test_timing_budget_supports_the_configured_carriage_speed():
    # firmware sim/board config cruise speed: v_max = head limit / 4 = 18000 * 2 / 4 = 9000 counts/s at 2 counts per dot
    v_cfg = 18_000 * 2 / 4
    assert d.max_carriage_speed_counts_s(2) > v_cfg                         # worst-case fully inked columns still fit
    assert d.worst_case_column_time_s() < 1 / (v_cfg / 2)                   # column time < column period (222 us)
    assert d.max_column_rate_hz() < d.F_FIRE_MAX                            # and the SPI-limited rate is the binding limit, not the head


def test_netlist_passes_erc_rules():
    assert n.check() == []


def test_netlist_erc_detects_defects():
    nets = n.build(); nets["ADDR3"] = nets["ADDR3"][:1]
    assert any("floating" in v for v in n.check(nets))
    nets = n.build(); nets["EXTRA"] = [("MCU", "GP4"), ("X", "1")]
    assert any("two nets" in v for v in n.check(nets))
    nets = n.build(); del nets["GND"]
    assert any("GND" in v for v in n.check(nets))


def test_every_head_line_is_driven_exactly_once():
    nets = n.build()
    for k in range(d.N_ADDR):
        assert sum(1 for c, p in nets["HEAD_ADDR%d" % k] if c == "J_HEAD") == 1
    for k in range(d.N_PRIM):
        assert sum(1 for c, p in nets["HEAD_PRIM%d" % k] if c == "J_HEAD") == 1
    outs = [(c, p) for net, pins in nets.items() for c, p in pins if c.startswith("SR") and re.fullmatch(r"Q[A-H]", p)]
    assert len(outs) == len(set(outs)) == 40                               # 5 x 8 outputs, each used once
    head = [p for net, pins in nets.items() for c, p in pins if c == "J_HEAD"]
    assert len(head) == len(set(head)) == d.HEAD_CONTACTS                    # all 52 contacts assigned


def test_board_config_header_matches_netlist_pins():
    text = open(BOARD).read()
    found = dict((m.group(1), int(m.group(2))) for m in re.finditer(r"#define\s+PIN_(\w+)\s+(\d+)", text))
    assert found == n.MCU_PINS


def test_board_config_constants_match_design():
    text = open(BOARD).read()
    assert re.search(r"#define\s+OI_SR_COUNT\s+%d\b" % d.shift_register_count(), text)
    assert re.search(r"#define\s+OI_N_ADDR\s+%d\b" % d.N_ADDR, text)
    assert re.search(r"#define\s+OI_N_PRIM\s+%d\b" % d.N_PRIM, text)
