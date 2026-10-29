---
paths:
  - "leodragkit/aero/**"
  - "tests/aero/**"
---

# aero: spacecraft drag from panel geometry and attitude

`leodragkit.aero` computes Cd·A(t) and B(t) = Cd·A(t)/m from flat panels, attitude quaternions and the atmosphere state. It is used on its own (contigo_edr) and by B estimation in `scaled_aero` mode (D-22). Method: `docs/methods/drag_coefficient_primer.md`. Read it before changing anything here.

## Boundaries

- Imports only numpy and scipy (for example `scipy.special.erf`, `scipy.constants.k`), and nothing from leodragkit (D-04). The atmosphere state arrives as arrays.
- Geometry is data, not code. Panel tables are files holding a body-frame unit normal and an area in m² per panel. They are validated on load: normals of unit length within a stated tolerance, areas > 0. Mission tables, such as the Spire bus versions, are data files.
- Reading attitude files belongs to `leodragkit.io`. Here, attitude arrives as quaternion arrays.

## Science conventions (change only with the user's approval)

1. **Method.** Free-molecular flow; the panel method, with each panel a Sentman flat plate under diffuse reflection with incomplete accommodation (DRIA); the satellite is the sum over panels. Multiple reflections are ignored. Shadowing is added only when a geometry needs it.
2. **Incidence angle.** cos δ = n̂_outward · v̂_rel, so δ = 0 faces straight into the flow. A unit test pins this sign.
3. **Relative velocity** is the velocity relative to the co-rotating atmosphere (Earth-fixed velocity), with no winds.
4. **Speed ratio** uses the most probable thermal speed, s = V / √(2 k_B T / m). It starts with one mean molecular mass. The mass-weighted per-species form (Mehta et al. 2023, eq. 11) is added later, as a sensitivity test.
5. **Reflected-speed constant** k is a parameter: ½ (Koppenwallner, as in the ADBSat code) or ⅔ (Cook, Moe). It defaults to ½ so results can be compared with ADBSat, and it is written to every output.
6. **Energy accommodation α and wall temperature T_w** are explicit inputs with no code defaults, and they are written to every output. α is the dominant uncertainty. It starts as a fixed value swept over a range; the atomic-oxygen (Langmuir) model comes later, by decision.
7. **Store Cd·A (m²) and B (m²/kg), never Cd alone.** Cd has no meaning without its reference area.
8. **Drag only.** Lift is not computed until a workflow needs it.
9. **Composition** comes from an `AtmosphereState` (D-10). When its model differs from the density model, raise `MixedAtmosphereModelWarning` and record both model names (D-12).
10. **Output** is B(t) as a time series, with optional averaging over one orbit or a chosen window (D-21).

## Quaternions

- The scalar position (first or last) and the frame pair (from body frame to which frame) are required arguments with no defaults. A wrong convention silently turns ram faces into wake faces.
- For each new attitude source, test that the nadir-pointing body axis points down in the expected frame.

## Sources and licence

- Write the equations from the published papers. Use the ADBSat code only to resolve the paper's known typos and as a test oracle. Never translate its GPL-3 MATLAB line by line, because that could constrain this package's licence.
- The paper typos and the forms to use instead are listed in the primer ("Choices and pitfalls"). The intended re-emission term is α(T_w/T_i − 1).
- Citations verified on 2026-10-27 (DOI resolves to the work):
  - Sinpetru et al. 2022, doi:10.1016/j.cpc.2022.108326 (methodology);
  - Sinpetru et al. 2022, doi:10.1016/j.cpc.2022.108327 (verification and validation);
  - Mehta et al. 2023, doi:10.1016/j.asr.2022.05.064;
  - Moe & Moe 2005, doi:10.1016/j.pss.2005.03.005;
  - March et al. 2021, doi:10.1051/swsc/2021035;
  - Walker, Mehta & Koller 2014, doi:10.2514/1.A32677;
  - Pilinski, Argrow & Palo 2010, doi:10.2514/1.49330.

  Parham & Barba and Doornbos are not yet usable (Q-03).

## Tests

Structural tests come first, because they need no reference numbers:

- a single plate summed over panels equals the closed form to machine precision;
- with large s and no re-emission (r = 0), the pressure coefficient approaches Newton's 2cos²δ, and the drag coefficient approaches 2cos δ, because the shear term adds 2sin²δ cos δ (full absorption of the intercepted momentum).;
- an edge-on plate (cos δ = 0) gives a finite value;
- a back-facing plate gives a small negative value (a forward push from molecules striking and leaving its rear face), negligible at s = 7 and growing in size as s falls. Never clip it to zero: summed over a sphere, the plate formula matches Bird's sphere formula only with this sign.;
- rotating a symmetric body by a symmetry of its shape leaves Cd·A unchanged.

The primer's numeric values (for example Cd = 2.1591 for a head-on plate) are derived, not published, and unverified (Q-04). Use them as reference values only after they have been reproduced independently, for example with Bird's sphere formula or ADBSat. Say in the test which check produced the number.
