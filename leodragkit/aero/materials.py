"""Surface materials: the properties of a spacecraft's surfaces that the gas-surface models need.

Each material holds only what a built task uses (D-59): the wall temperature and the energy accommodation
coefficient α. Surface-atom mass and the CLL coefficients are added by the tasks that first need them.
Neither value has a default: both are explicit modelling choices, written to every output (D-23).

Read first: ``SurfaceMaterial``.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class SurfaceMaterial:
    """One surface material, by name, with the properties the gas-surface models read.

    Example::

        aluminium = SurfaceMaterial("aluminium", wall_temperature_kelvin=300.0, energy_accommodation=0.9)
    """

    name: str
    wall_temperature_kelvin: float  # T_w, > 0
    energy_accommodation: float  # α, in [0, 1]

    def __post_init__(self) -> None:
        if not isinstance(self.name, str) or not self.name:
            raise ValueError(f"SurfaceMaterial.name must be a non-empty string, got {self.name!r}.")
        temperature = self.wall_temperature_kelvin
        if isinstance(temperature, bool) or not np.isfinite(temperature) or temperature <= 0:
            raise ValueError(
                f"Material {self.name!r}: wall_temperature_kelvin must be > 0, got {temperature!r}."
            )
        alpha = self.energy_accommodation
        if isinstance(alpha, bool) or not np.isfinite(alpha) or not 0.0 <= alpha <= 1.0:
            raise ValueError(
                f"Material {self.name!r}: energy_accommodation must be in [0, 1], got {alpha!r}."
            )
