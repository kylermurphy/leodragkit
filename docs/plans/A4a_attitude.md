# A4a: Attitude in ITRF

Step plan for task A4a in `docs/tasks.md`; part of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Three components, one patch each, reviewed and pushed before the next.

## Goal

Turn attitude data, or an attitude law, into `Attitude`: the rotation from ITRF into the body frame at each epoch, alongside `OrbitStates` on the same epochs. Everything is in ITRF (D-79), nothing is interpolated (D-80), and the quaternion conventions are explicit (D-81, D-85). This is the input A4b needs to find each panel's angle to the flow.

## Decisions in this step (the user's answers, 2026-11-03; D-86)

- **Times in aero:** `times` (a `datetime64[ns]` array) plus a `time_scale` label (`"GPS"`, `"UTC"`), not `Epochs`. aero only checks that inputs share instants; the workflow uses `Epochs` to line up attitude, orbit (GPS) and atmosphere (UTC), then passes one scale. aero keeps importing nothing from `io` or `time_scales`, so it needs no spiceypy and no kernel (D-04).
- **`OrbitStates`:** aero's own type for positions, velocities, times, scale, frame and source, built by the workflow from `io`'s `SatelliteStates` in one line. Same pattern as `AeroAtmosphere`.
- **`common_epochs`:** a small aero helper keeping the epochs two inputs share **exactly**. It is selection, not interpolation.
- **The notebook** gets a real-data section: it reads the user's two FM134 files from paths set at its top, and falls back to a hand-built circular orbit when they are absent.

## Components

| # | Builds | Who |
| --- | --- | --- |
| 1 | `Attitude`, `OrbitStates`; `attitude_from_quaternions` with the three conventions | Claude (this patch) |
| 2 | `inertial_velocity_in_itrf(r, v)` = v + ω_E × r; `itrf_from_orbit_level(r, v_inertial)`, Spire's orbit frame; the attitude law (`along_velocity`, `towards_nadir`, both required) | user |
| 3 | `"orbit_level_spire"` → `"ITRF"` (body_from_ITRF = body_from_orbit · orbit_from_ITRF); `common_epochs`; checks that epochs, scale and frame agree; notebook section 12 | Claude |

## Component 1 in detail

**`attitude_from_quaternions(times, time_scale, quaternions, *, scalar_position, algebra, direction, frame, source)`**, in three steps:

1. **Scalar position:** reordered to scalar last, as scipy expects.
2. **Algebra:** read as Hamilton. JPL multiplication is Hamilton's in reverse order (a ⊗ b in JPL is b ⊗ a in Hamilton), so u′ = q u q* in JPL algebra is q* u q in Hamilton's: the inverse rotation. A JPL quaternion is read as Hamilton and inverted.
3. **Direction:** `"body_to_reference"` (Spire's) is inverted, so the stored rotation is always `body_from_reference`; `"reference_to_body"` is kept.

**Quaternions:** finite, (T, 4), and of length 1 within 10⁻⁶. Otherwise it raises, naming the first bad one, because scipy would rescale it silently into a plausible but wrong attitude.

**`Attitude`** (checked whenever created):

- times: non-empty, strictly increasing, `datetime64[ns]`;
- a known time scale;
- one scipy `Rotation` per epoch;
- a frame from `("ITRF", "orbit_level_spire")`;
- a source.

**`OrbitStates`** has the same time checks, plus (T, 3) finite positions and velocities and the frame `"ITRF"`.

**Tests (component 1):** 17.

- **Hand-worked conventions,** for 90° about z:
  - Hamilton, body to reference: reference +y → body x;
  - JPL: reference −y → body x;
  - scalar first gives the same rotation;
  - reference to body keeps the quaternion's rotation.
- **All four algebra and direction combinations** recover a known rotation to 10⁻¹⁴.
- **A real Spire sample:** orbit-frame nadir lies 0.47° from body +z, which matches Spire's body frame (Appendix A.1).
- **Six bad inputs:** length 1.1, NaN, wrong shape, and three unknown conventions.
- **The type checks** for `Attitude` and `OrbitStates`.

## Component 2: what the user writes (planned)

- **`inertial_velocity_in_itrf(positions_m, velocities_m_per_s)`** = v + ω_E × r, with ω_E = (0, 0, 7.292115 × 10⁻⁵) rad s⁻¹. That is the nominal mean angular velocity of the Earth, from the IERS Conventions' numerical standards (IERS Technical Note 32, McCarthy & Petit, 2003, Table 1.1; https://iers-conventions.obspm.fr/archive/2003/chapter1/tn32_c1.pdf, read 2026-11-03), unchanged in the IAU 2009 system of astronomical constants. It ignores day-length changes of a few parts in 10⁸; their effect on v is micrometres per second.
- **`itrf_from_orbit_level(positions_m, inertial_velocities_m_per_s)`:** Z = −r̂, Y = −(r × v)/\|r × v\|, X = Y × Z, as the columns of a rotation (Spire's leoAtt header; D-85).
- **The attitude law:** `along_velocity` and `towards_nadir`, each a signed body axis such as `"+x"` or `"-z"`; they must be perpendicular.
