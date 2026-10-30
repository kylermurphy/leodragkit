"""The contract every gas-surface model meets: what a model returns for one flat plate.

A gas-surface model (Sentman, DRIA, CLL) describes how molecules exchange momentum with a surface.
Whatever the model, it returns the same thing for every panel and epoch: the pressure, shear and drag
coefficients of a one-sided flat plate, referenced to the panel's own area. The integration stage
builds force and moment vectors from these numbers alone, so it never needs to know which model ran.

Sign convention: pressure pushes into the plate, along −n̂_outward; shear acts along t̂, the flow
direction (−v̂_rel) projected onto the plate and normalised. The plate's force is
q·A·(C_p·(−n̂_outward) + C_τ·t̂), with q = ½ρV², so its component along the flow is
C_d = C_p cos δ + C_τ sin δ. Back-facing plates keep their small negative drag; nothing is clipped.

The models live in modules named ``gas_surface_<model>.py``. Read this module first, then
``gas_surface_sentman.py``.
"""

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class FlatPlateCoefficients:
    """Coefficients of one-sided flat plates, referenced to each plate's own area.

    All three arrays have the same shape, usually (epochs, panels) or broadcast from the inputs.
    """

    pressure_coefficient: np.ndarray  # C_p: pushes into the plate, along −n̂_outward
    shear_coefficient: np.ndarray  # C_τ: along the flow direction projected onto the plate
    drag_coefficient: np.ndarray  # C_d = C_p cos δ + C_τ sin δ: the component along the flow
