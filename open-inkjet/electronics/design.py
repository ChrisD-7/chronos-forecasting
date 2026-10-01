# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: CERN-OHL-S-2.0
"""Head-drive electronics: calculations and budgets (block level). NOT a verified circuit.

Tags: SOURCED = from public sources seen only as search snippets (see docs/VERIFICATION.md); UNVERIFIED = no source
found, measure on the bench (docs/BENCH.md); DERIVED = arithmetic from the tagged inputs; CHOICE = design decision."""
import math

# ---- inputs -------------------------------------------------------------------------------------------------------
V_HEAD = 12.0            # SOURCED: HP45 operates on 12 V (ytec3d.com via search summary)
R_HEATER = 30.0          # UNVERIFIED: "~30 ohm" appeared in one snippet, could not be confirmed
T_PULSE_S = 2.0e-6       # UNVERIFIED: "~2 us" appeared in one snippet, pulse width is ink dependent
N_ADDR = 22              # SOURCED: patent snippet (22 address select lines)
N_PRIM = 14              # SOURCED: patent snippet (14 primitives + 14 primitive commons; 50 interconnections)
N_NOZZLES = 300          # SOURCED
HEAD_CONTACTS = 52       # SOURCED: 52 contacts on the cartridge back
F_FIRE_MAX = 18_000.0    # SOURCED: max firing frequency 18 kHz
RP2040_USABLE_GPIO = 26  # Pico/Pico 2 header: GP0-GP22 and GP26-GP28 minus GP23-25 internal = 26 usable + LED (GP25) separate
SR_BITS = 8              # 74HC595
SPI_REQUEST_HZ = 10_000_000   # CHOICE: derated; 74HC595 clock limits are tabulated at 2 / 4.5 / 6 V, nothing found for 3.3 V (UNVERIFIED)
CLK_PERI_HZ = 125_000_000     # RP2040 clk_peri default (a 150 MHz Pico 2 differs)
LATCH_S = 100e-9         # CHOICE: RCLK pulse
SETTLE_S = 1.0e-6        # CHOICE: driver stage settling after RCLK and before OE_N goes low (firmware: OI_SETTLE_NS; UNVERIFIED, measure)
GAP_S = 0.5e-6           # CHOICE: gap between two address pulses
DROOP_MAX = 0.05         # CHOICE: <= 5% supply droop during a worst-case column


def rp2040_spi_hz(requested, clk=CLK_PERI_HZ):
    """Baud the Pico SDK's spi_set_baudrate() really produces: prescale must be even (2..254), postdiv 1..256."""
    prescale = 2
    while prescale <= 254 and clk >= (prescale + 2) * 256 * requested:
        prescale += 2
    postdiv = 256
    while postdiv > 1 and clk / (prescale * (postdiv - 1)) <= requested:
        postdiv -= 1
    return clk / (prescale * postdiv)


SPI_HZ = rp2040_spi_hz(SPI_REQUEST_HZ)      # DERIVED: 8.93 MHz for a 10 MHz request at 125 MHz


def heater_current_a():
    return V_HEAD / R_HEATER


def pulse_energy_j():
    """Energy per heater per pulse (one nozzle)."""
    return V_HEAD ** 2 / R_HEATER * T_PULSE_S


def peak_current_a(n_simultaneous=N_PRIM):
    """One address is enabled at a time, so at most N_PRIM heaters fire together."""
    return n_simultaneous * heater_current_a()


def bulk_capacitance_f(n_simultaneous=N_PRIM):
    """PER-PULSE minimum: capacitance so ONE worst-case pulse (14 heaters) droops the rail by <= DROOP_MAX (charge = I * t).
    It is a lower bound: a column is many pulses, see column_capacitance_f()."""
    q = peak_current_a(n_simultaneous) * T_PULSE_S
    return q / (V_HEAD * DROOP_MAX)


def column_charge_c(n_nozzles=N_NOZZLES):
    """Charge drawn by a fully inked column (every nozzle once)."""
    return n_nozzles * heater_current_a() * T_PULSE_S


def column_capacitance_f():
    """Capacitance to ride through a whole worst-case column with NO recharge from the supply (conservative bound)."""
    return column_charge_c() / (V_HEAD * DROOP_MAX)


def esr_budget_ohm(n_simultaneous=N_PRIM):
    """Total series resistance (ESR + wiring + switch) allowed so the peak current alone drops the rail by <= DROOP_MAX."""
    return V_HEAD * DROOP_MAX / peak_current_a(n_simultaneous)


def average_column_current_a():
    return column_charge_c() / worst_case_column_time_s()


def shift_register_count(n_outputs=N_ADDR + N_PRIM):
    return math.ceil(n_outputs / SR_BITS)


def spi_bytes_per_address():
    return shift_register_count()


def per_address_time_s():
    spi = spi_bytes_per_address() * 8 / SPI_HZ
    return spi + LATCH_S + SETTLE_S + T_PULSE_S + GAP_S


def worst_case_column_time_s():
    """Every address has at least one nozzle to fire (fully inked column)."""
    return N_ADDR * per_address_time_s()


def max_column_rate_hz():
    return 1.0 / worst_case_column_time_s()


def max_carriage_speed_counts_s(counts_per_dot):
    """Highest carriage speed at which worst-case columns can still be fired: one column per dot pitch."""
    return max_column_rate_hz() * counts_per_dot


def head_contact_budget():
    """52 contacts = 22 address + 14 primitive + 14 primitive common + remaining unknown."""
    return HEAD_CONTACTS - N_ADDR - 2 * N_PRIM


def summary():
    return dict(
        heater_current_a=heater_current_a(), pulse_energy_uj=pulse_energy_j() * 1e6, peak_current_a=peak_current_a(),
        bulk_cap_per_pulse_uf=bulk_capacitance_f() * 1e6, bulk_cap_per_column_uf=column_capacitance_f() * 1e6,
        esr_budget_mohm=esr_budget_ohm() * 1e3, avg_column_current_a=average_column_current_a(),
        spi_mhz=SPI_HZ / 1e6, shift_registers=shift_register_count(),
        per_address_us=per_address_time_s() * 1e6, worst_column_us=worst_case_column_time_s() * 1e6,
        max_column_rate_khz=max_column_rate_hz() / 1e3,
        max_speed_counts_s_at_2cpd=max_carriage_speed_counts_s(2), unknown_head_contacts=head_contact_budget())


if __name__ == "__main__":
    for k, v in summary().items():
        print("%-28s %.4g" % (k, v))
