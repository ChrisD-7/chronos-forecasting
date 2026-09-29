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
SPI_HZ = 25_000_000      # CHOICE (RP2040 SPI at clk_peri 125 MHz / 5); 74HC595 at 5 V is rated well above this, verify at 3.3 V
LATCH_S = 100e-9         # CHOICE: RCLK pulse
SETTLE_S = 1.0e-6        # CHOICE: driver stage settling before the pulse (UNVERIFIED; measure)
GAP_S = 0.5e-6           # CHOICE: gap between two address pulses
DROOP_MAX = 0.05         # CHOICE: <= 5% supply droop during a worst-case column


def heater_current_a():
    return V_HEAD / R_HEATER


def pulse_energy_j():
    """Energy per heater per pulse (one nozzle)."""
    return V_HEAD ** 2 / R_HEATER * T_PULSE_S


def peak_current_a(n_simultaneous=N_PRIM):
    """One address is enabled at a time, so at most N_PRIM heaters fire together."""
    return n_simultaneous * heater_current_a()


def bulk_capacitance_f(n_simultaneous=N_PRIM):
    """Capacitance so the worst-case pulse droops the rail by <= DROOP_MAX (charge drawn = I * t)."""
    q = peak_current_a(n_simultaneous) * T_PULSE_S
    return q / (V_HEAD * DROOP_MAX)


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
        bulk_cap_min_uf=bulk_capacitance_f() * 1e6, shift_registers=shift_register_count(),
        per_address_us=per_address_time_s() * 1e6, worst_column_us=worst_case_column_time_s() * 1e6,
        max_column_rate_khz=max_column_rate_hz() / 1e3,
        max_speed_counts_s_at_2cpd=max_carriage_speed_counts_s(2), unknown_head_contacts=head_contact_budget())


if __name__ == "__main__":
    for k, v in summary().items():
        print("%-28s %.4g" % (k, v))
