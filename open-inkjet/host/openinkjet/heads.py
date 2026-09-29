# SPDX-FileCopyrightText: 2026 open-inkjet contributors
# SPDX-License-Identifier: GPL-3.0-only
"""Printhead descriptors. Values are from public sources and MUST be confirmed on the bench
(see docs/VERIFICATION.md). Source for HP45: https://ytec3d.com/hp45-inkjet-printhead/"""
from dataclasses import dataclass

MM_PER_INCH = 25.4


@dataclass(frozen=True)
class HeadSpec:
    name: str
    nozzles: int
    nozzle_dpi: int          # nozzle spacing along the paper-feed axis
    max_fire_hz: float
    fire_pulse_us: float
    supply_v: float

    @property
    def swath_mm(self) -> float:
        return self.nozzles / self.nozzle_dpi * MM_PER_INCH


HP45 = HeadSpec("HP45/51645A", nozzles=300, nozzle_dpi=600,
                max_fire_hz=18_000.0, fire_pulse_us=2.0, supply_v=12.0)
