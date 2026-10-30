# A2: Independent checks of the Sentman plate

**Status: done 2026-10-30.** All 46 tests pass (101 in the fast suite); reference formulas written by the user, reviewed.

Step plan for task A2 in `docs/tasks.md`. Mode: the user writes the reference formulas from the papers; Claude wrote the tests around them and the documentation.

## Goal

Check the Sentman code from A1 against formulas derived independently of it: Bird's sphere, Dey et al.'s DRIA plate and sphere, and Cook's hyperthermal formula. This turns the primer's derived numbers into test references and closes Q-04, except the k = 1/2 plate values at α < 1, which wait for the ADBSat comparison in A11. Validation rungs V1 and V2 in `docs/aero_plan.md`.

Independence comes from the source: the reference formulas are typed from the papers, never from leodragkit's code.

## Files

| File | Change | Who |
| --- | --- | --- |
| `tests/aero/test_sentman_independent_checks.py` | new: six reference-formula templates at the top, then the tests | user (formulas), Claude (tests) |
| `docs/methods/drag_coefficient_primer.md`, `docs/aero_plan.md`, `docs/tasks.md` | the corrected hyperthermal-limit statement (R-04) | Claude |
| `docs/results_log.md` | R-04 | Claude |
| `docs/decisions.md` | Q-04 status | Claude |

No package code changes. The closed forms are test references only; analytic components are parked (D-48).

## What to write

All six functions are in `tests/aero/test_sentman_independent_checks.py`, each with its equation in the docstring and numbered steps:

| Function | Source |
| --- | --- |
| `bird_sphere_drag(speed_ratio, wall_speed_ratio)` | Parham & Barba 2014, eq. 4 |
| `dey_reflected_kinetic_temperature_kelvin(speed_ratio, energy_accommodation, ambient_temperature_kelvin, wall_temperature_kelvin)` | Dey et al. 2025a, eq. 2.4 |
| `dey_dria_plate_drag(cos_incidence_angle, speed_ratio, reflected_kinetic_temperature_kelvin, ambient_temperature_kelvin)` | Dey et al. 2025a, eq. 2.3 |
| `dey_dria_sphere_drag(speed_ratio, reflected_kinetic_temperature_kelvin, ambient_temperature_kelvin)` | Dey et al. 2025a, eq. 2.5 |
| `cook_hyperthermal_drag(cos_incidence_angle, energy_accommodation, wall_temperature_kelvin, incident_kinetic_temperature_kelvin)` | Sinpetru et al. 2022a, eq. 18, intended form |
| `integrate_plate_over_sphere(plate_drag_of_cos)` | derived: C_D = 2∫₋₁¹ c_d(c) dc |

Suggested order: `dey_reflected_kinetic_temperature_kelvin` (used by most tests), then `bird_sphere_drag`, `dey_dria_sphere_drag`, `integrate_plate_over_sphere`, `dey_dria_plate_drag`, `cook_hyperthermal_drag`. When all six are written, remove the two `# noqa: F401` comments on the imports and run `ruff check .`.

## Required reading

| # | What | Which parts | Why | Time |
| --- | --- | --- | --- | --- |
| 1 | Parham & Barba 2014 (arXiv:1312.3691) | §II up to eq. 4 | Bird's closed-form sphere drag; what S_W is | 20 min |
| 2 | Dey et al. 2025a | §2.1, eqs. 2.1–2.5 | the DRIA plate and sphere in their notation; T_k,i and T_k,r | 20 min |
| 3 | Sinpetru et al. 2022a | eqs. 16–21 and the paragraph above eq. 18 | the hyperthermal models (Storch, Cook, Newton); eq. 18 has the eq. 6 bracket typo | 15 min |
| 4 | `scipy.integrate.quad` documentation | arguments, the returned error estimate, `epsabs`, `epsrel`, `limit` | the sphere integral must reach about 1e-12 | 10 min |
| 5 | Our primer | "Verification cases for unit tests" | the numbers these tests reproduce | 10 min |

## The sphere integral

A sphere element at polar angle θ from the flow has cos δ = cos θ and area 2πR² sin θ dθ. Referencing the drag to the cross-section πR² gives C_D = 2∫₋₁¹ c_d(c) dc, so any plate formula becomes a sphere formula by one integral. That is what lets a closed-form sphere check the plate.

## Tests

At the start: 44 failed, 2 passed. Every failure is a `NotImplementedError` from a reference formula. The two that pass already are the hyperthermal-limit tests, which use only the A1 code. Against scratch reference formulas kept out of the repository, all 46 pass.

| Group | Tests |
| --- | --- |
| Sphere, α = 1 | the A1 plate integrated over a sphere equals Bird for s = 0.5 to 10, both k, to 1e-10; Bird reproduces the primer's 2.2140, 2.1253, 2.0874 |
| Sphere, α < 1 | the same against Dey eq. 2.5, for α = 0, 0.5, 0.9 and both k (with k = 1/2 through T_k,r = T∞(s·r)², the identity of R-02) |
| Plate | the A1 plate with k = 2/3 equals Dey eq. 2.3 for cos δ from −1 to 1, s from 0.5 to 20, α = 0, 0.5, 1, to 1e-12 |
| Primer values | Dey eq. 2.3 reproduces 2.1591, 2.4966 and 3.4676, and the A1 code agrees with Dey to 1e-12 |
| Hyperthermal | at s = 10⁴ the A1 drag equals 2cos δ + √π·r·cos²δ; Cook's re-emission term differs from it by exactly 3√(πk)/4 (R-04) |

## Traps

- **erfc in Dey's plate.** Dey writes 1 + erf(γs); compute it as `erfc(-γs)`, as in A1, or the back-face values at s = 20 lose their digits.
- **Two temperatures in Cook.** Eq. 18's T_inf is the incident kinetic temperature, mV²/(3k_B) = (2/3)s²T∞, not the gas temperature T∞. The test passes the kinetic temperature in.
- **Eq. 18's typo.** The bracket is α(T_w/T_i − 1), as in eq. 6.
- **quad tolerances.** The defaults stop near 1e-8 relative; the tests compare at 1e-10. Pass tighter `epsabs` and `epsrel`, and a larger `limit` if quad warns.
- **Sentman is not Cook.** The last test expects them to differ, by a fixed factor. A ratio of exactly 1 would mean the Cook formula was typed from Sentman's.

## Done when

All 46 tests in this file pass, the fast suite shows 101 passed, and `ruff check .` passes with the `noqa` comments removed. A2 is then marked done, and Q-04 stays open only for the k = 1/2 values that A11 checks.
