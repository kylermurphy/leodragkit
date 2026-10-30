# A1: Sentman flat plate (pressure, shear, drag)

Step plan for task A1 in `docs/tasks.md`: what to read, what to write, in what order, and how to know it is done. Mode: the user writes the physics; Claude wrote the templates, tests and documentation.

## Goal

Write the functions that turn a plate's incidence and the gas state into its pressure, shear and drag coefficients: steps 2–3 of `docs/methods/drag_coefficient_primer.md`, validation rung V0 in `docs/aero_plan.md`. Everything after this (panels, the force vector, DRIA, CLL) builds on these numbers.

## Files

| File | Change | Who |
| --- | --- | --- |
| `leodragkit/aero/gas_surface.py` | the contract `FlatPlateCoefficients`, complete | Claude |
| `leodragkit/aero/gas_surface_sentman.py` | template: `_as_checked_array` complete; two physics functions to write | Claude (template, helper); user (physics bodies) |
| `tests/aero/test_gas_surface_sentman.py` | 29 tests | Claude |
| `docs/decisions.md` | D-50: force-sign convention and the dataclass | Claude |
| `docs/results_log.md` | R-03: erfc versus 1 + erf on back faces | Claude |
| `docs/methods/drag_coefficient_primer.md` | corrected back-face value (R-03) | Claude |
| `docs/code_tour.md`, `docs/tasks.md` | A1 entry and status | Claude |

No code exists in swift_reentry to reuse. The libraries needed are `scipy.special.erfc`, `np.exp`, `np.sqrt` and `np.clip`.

## The functions

```python
# gas_surface.py: the contract every gas-surface model returns
@dataclass(frozen=True)
class FlatPlateCoefficients:
    pressure_coefficient: np.ndarray   # C_p: pushes into the plate, along −n̂_outward
    shear_coefficient: np.ndarray      # C_τ: along the flow direction projected onto the plate
    drag_coefficient: np.ndarray       # C_d = C_p cos δ + C_τ sin δ: along the flow

# gas_surface_sentman.py: what you write
def compute_reflected_speed_ratio(speed_ratio, ambient_temperature_kelvin, wall_temperature_kelvin,
                                  energy_accommodation, reflected_speed_constant=0.5) -> np.ndarray

def compute_sentman_flat_plate_coefficients(cos_incidence_angle, speed_ratio,
                                            reflected_speed_ratio) -> FlatPlateCoefficients
```

The plate's force is q·A·(C_p·(−n̂_outward) + C_τ·t̂), with t̂ the flow direction (−v̂_rel) projected onto the plate (D-50). Task A5 builds the force vector from this. Every later gas-surface model returns the same dataclass (D-52); `docs/aero_plan.md`, section 3a, shows how the modules connect.

## Required reading

In order. The first three are essential for A1; the rest prepare for the tasks after it.

| # | What | Which parts | Why | Time |
| --- | --- | --- | --- | --- |
| 1 | `docs/methods/drag_coefficient_primer.md` | "Core concepts", steps 1–3, "Choices and pitfalls" | the method and its conventions in our notation | 25 min |
| 2 | Sinpetru et al. 2022a, ADBSat methodology (arXiv:2104.05543v2) | §2 on gas-surface models: eq. 2 (accommodation), eqs. 6–8 (Sentman C_p, C_τ, erf), eqs. 18–21 (Cook and Newton limits); §3 on panels: eqs. 25–28 | the source of the formulas; mind the eq. 6 bracket typo | 45 min |
| 3 | Storch 2002 (scan in the project) | §2.1 (PDF pp. 11–12): accommodation and Figs. 2.1–2.2; §3.1 (PDF p. 28): eqs. 3.7–3.9 | what pressure and shear are physically: momentum carried in and out, normal and tangential | 30 min |
| 4 | Moe & Moe 2005 | §§1–3 | why Cd > 2, and why α falls with altitude | 30 min |
| 5 | Dey et al. 2025a | §2.1, eqs. 2.1–2.4 | the same plate written another way, with k = 2/3; task A2 tests this identity | 15 min |
| 6 | `docs/aero_plan.md` | §3a (data flow, types, contracts), §4.1 | where these numbers go next | 15 min |

## Work order

`_as_checked_array` is already written; use it for every input check. Then:

1. **`compute_reflected_speed_ratio`**:
   1. check the inputs, including that k is 1/2 or 2/3;
   2. compute T_i = k s² T∞;
   3. compute r = √(k[1 + α(T_w/T_i − 1)]).
2. **`compute_sentman_flat_plate_coefficients`**:
   1. check the inputs and clamp cos δ to [−1, 1] within the tolerance;
   2. sin δ;
   3. E and F, with F from erfc;
   4. C_p;
   5. C_τ;
   6. C_d;
   7. return the dataclass.
3. Run `pytest tests/aero/test_gas_surface_sentman.py` after each function. The reflected-speed tests go green first.

## Why F must be computed with erfc

The formula needs F = 1 + erf(s cos δ). On a back face, s cos δ is large and negative, erf is almost exactly −1, and the subtraction loses every significant digit. Compared with 50-digit arithmetic (R-03; α = 0.9, T∞ = 1000 K, T_w = 300 K, k = 1/2):

| s (back face) | 1 + erf form | erfc(−x) form | 50 digits |
| --- | --- | --- | --- |
| 3 | −3.8923 × 10⁻⁷ | −3.892324 × 10⁻⁷ | −3.892324 × 10⁻⁷ |
| 7 | **+3.3434 × 10⁻²³** (wrong sign) | −9.570727 × 10⁻²⁶ | −9.570727 × 10⁻²⁶ |
| 10 | **+1.6718 × 10⁻⁴⁵** (wrong sign) | −2.205651 × 10⁻⁴⁸ | −2.205651 × 10⁻⁴⁸ |

The erfc form agrees with 50 digits to within 4 × 10⁻¹³ relative at every case tested.

## Tests

At the start:

```
29 failed, 26 passed
     23 NotImplementedError: compute_reflected_speed_ratio
      6 NotImplementedError: compute_sentman_flat_plate_coefficients
```

Every failure is a `NotImplementedError`. All 29 tests pass against a scratch implementation kept out of the repository, so a failure is in the new code, not the tests.

| Group | Tests |
| --- | --- |
| Reflected speed | at α = 1 both constants give √(T_w/(s²T∞)); the default constant is 1/2; less accommodation means faster re-emission |
| Plate structure | the result holds three arrays; drag = C_p cos δ + C_τ sin δ; a head-on plate has no shear; at α = 1 head-on drag does not depend on k; head-on drag grows as α falls; an edge-on plate has finite positive drag |
| Limits | at large s with r = 0: C_p → 2cos²δ (Newton), C_τ → 2 sin δ cos δ, C_d → 2cos δ |
| Back faces | negative drag for s = 1, 3, 5, 7 and 10, matching 50-digit references to 10⁻¹² (precision checks, not physics references) |
| Mechanics | arrays broadcast and match scalar calls; cos δ just beyond 1 is clamped; every invalid input raises a `ValueError` naming it |

The primer's physics reference values (for example Cd = 2.1591 head-on) are not used yet; task A2 reproduces them independently first.

## Traps

- **erfc, not erf.** Write F as `erfc(-s*c)`. The back-face tests fail if you use `1 + erf(s*c)`.
- **sin δ.** Compute it after clamping, with `np.sqrt(1 - c**2)`, not `np.sin(np.arccos(c))`, which loses precision near c = ±1.
- **k.** It is a plain float, so compare it with `np.isclose` against the two constants rather than `==`.
- **Broadcasting.** Let numpy broadcast mixed scalars and arrays; the broadcasting test compares an array call with element-by-element calls to 10⁻¹⁵.
- **Eq. 6 typo.** The re-emission term is α(T_w/T_i − 1), not αT_w/(T_i − 1).

## Done when

All 29 tests pass, and the fast suite (`pytest -m "not slow and not network"`) shows 55 passed. Then send `gas_surface_sentman.py` for review. A1 is marked done in `docs/tasks.md` once the review is approved.
