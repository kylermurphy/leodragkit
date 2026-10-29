# Results log

Every run whose result is reported or acted on gets an entry here, with an id (`R-NN`) that decisions, method documents and notebooks cite. Entries are never edited afterwards; a correction is a new entry that refers to the old one.

Each entry gives:

- **What was run**: the workflow, and the `ldk` command or API call.
- **Run folder**: `<output_root>/<workflow_name>/<run_id>/`. Its `manifest.json` holds the settings, input records, code version and seeds.
- **Result**: the numbers, with units and uncertainties.
- **What it informed**: the decision, task or question it fed (`D-NN`, `T-NN`, `Q-NN`).

## R-01. Sentman flat plate: hyperthermal limit, back-face sign, and the sphere (2026-10-28)

- **What was run:** an exploration in the planning chat for task A1, not a workflow. A scratch implementation of the plate formula (`docs/methods/drag_coefficient_primer.md`, steps 2–3), equal in content to what A1 asks for, was evaluated directly and integrated over a sphere with `scipy.integrate.quad` (C_D,sphere = 2∫₋₁¹ c_d(c) dc). The script was not kept; task A2 repeats these checks as tests.
- **Run folder:** none.
- **Result:**
  - With s = 10⁴ and r = 0, c_d = 2cos δ at δ = 0°, 30°, 60°, 85° (2.0000, 1.7321, 1.0000, 0.1743), not 2cos³δ (2.0000, 1.2990, 0.2500, 0.0013).
  - A back-facing plate (cos δ = −1, α = 0.9, T∞ = 1000 K, T_w = 300 K) gives c_d = 3.3 × 10⁻²³ at s = 7, −3.9 × 10⁻⁷ at s = 3 and −0.054 at s = 1.
  - Sphere, α = 1, T∞ = 922 K, T_w = 300 K, with Bird's formula from Parham & Barba (2014), eq. 4:

    | s | Bird | plate integral, sign kept | plate integral, back faces clipped to 0 |
    |---|---|---|---|
    | 0.5 | 7.661754 | 7.661754 | 8.460538 |
    | 1 | 4.246143 | 4.246143 | 4.281078 |
    | 2 | 2.805842 | 2.805842 | 2.805936 |
    | 5 | 2.214006 | 2.214006 | 2.214006 |
    | 10 | 2.087353 | 2.087353 | 2.087353 |

  - The primer's head-on plate values (2.1591, 2.4380, 3.2737 for k = 1/2; 2.4966, 3.4676 for k = 2/3), its edge-on value (0.0806) and its sphere values at s = 5 and 10 were reproduced from the same equations. This is consistency, not independent verification; that is task A2.
- **What it informed:** the two corrections to the primer and to `.claude/rules/aero.md` (hyperthermal limit, back-face sign); the A1 tests; Q-04 (partly).

## R-02. DRIA and CLL plate identities (2026-10-29)

- **What was run:** an exploration while writing `docs/aero_plan.md`, not a workflow. Three plate forms were evaluated at cos δ = 1, 0.5, 0, −0.5 and s = 0.7, 2, 7, with T∞ = 1000 K and T_w = 300 K:
  - Dey et al. (2025a) eq. 2.3 (DRIA), with T_k,r from eq. 2.4;
  - Dey et al. (2025a) eq. 2.7 (CLL);
  - the primer's Sentman form, C_p cos δ + C_τ sin δ.
  The script was not kept; tasks A2 and A10 turn these checks into tests.
- **Run folder:** none.
- **Result:**
  - Dey eq. 2.3 at α = 0.9 equals the Sentman form with k = 2/3: largest difference 4.4 × 10⁻¹⁶.
  - Dey eq. 2.3 at α = 1 equals Dey eq. 2.7 with σ_n = σ_t = 1: largest difference 2.2 × 10⁻¹⁶.
- **What it informed:** D-40 (DRIA is Sentman per species); Q-08 (the published DRIA uses k = 2/3); the V1 tests in `docs/aero_plan.md`.
