# A4a: Attitude in ITRF

**Status: done 2026-11-03.**

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
| 2 | `inertial_velocity_in_itrf(r, v)` = v + ω_E × r; `itrf_from_orbit_level(r, v_inertial)`, Spire's orbit frame; the attitude law (`along_velocity`, `towards_nadir`, both required) | user (done; `itrf_from_orbit_level` and the law written with Claude's help, on request) |
| 3 | `"orbit_level_spire"` → `"ITRF"` (body_from_ITRF = body_from_orbit · orbit_from_ITRF); `common_epochs`; checks that epochs, scale and frame agree; notebook section 12 | Claude (done) |

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

## Component 2: the user's part

**In the template, written:** `EARTH_ROTATION_RATE_RAD_PER_S` = 7.292115 × 10⁻⁵ rad s⁻¹, the nominal mean angular velocity of the Earth (IERS Conventions 2003, IERS Technical Note 32, McCarthy & Petit, Table 1.1, https://iers-conventions.obspm.fr/archive/2003/chapter1/tn32_c1.pdf, read 2026-11-03; unchanged in the IAU 2009 system of astronomical constants). It ignores day-length changes of a few parts in 10⁸, which are micrometres per second in v + ω × r. Also written: `BODY_AXES` and `_signed_axis`.

**To write:**

| Function | Does |
| --- | --- |
| `inertial_velocity_in_itrf(positions_m, velocities_m_per_s)` | v + ω_E × r, row by row, with ω_E = (0, 0, `EARTH_ROTATION_RATE_RAD_PER_S`) |
| `itrf_from_orbit_level(positions_m, inertial_velocities_m_per_s)` | Z = −r̂; Y = −(r × v)/\|r × v\|; X = Y × Z; the matrices with X, Y, Z as **columns**, as a `Rotation`; raises, naming the epoch, if r or r × v is zero |
| `attitude_from_law(states, *, along_velocity, towards_nadir)` | the two signed body axes (perpendicular, or raise); body_from_orbit with columns X → `along_velocity`, Y → `towards_nadir` × `along_velocity`, Z → `towards_nadir`; then body_from_ITRF = body_from_orbit · orbit_from_ITRF, on the states' times, frame `"ITRF"` |

**Required reading:**

- the A4 overview's "Frames";
- D-79 and D-85;
- scipy's `Rotation`: `from_matrix`, `inv`, `apply`, and composition `a * b` (applies `b` first);
- for the cross-product identities, any linear-algebra reference on how a rotation preserves cross products (it's why Y's image is Z's image × X's image).

About 30 min.

**Tests (component 2):** 11.

- **Inertial velocity:**
  - at the equator it adds ω_E R ≈ 486.4 m/s eastward;
  - over the pole it is unchanged.
- **The orbit frame:**
  - a prograde equatorial orbit's frame, worked by hand;
  - for 50 random states, right-handed, with Z towards the Earth and X along the flight direction;
  - v along r raises.
- **The law:**
  - `+x` along the flight direction and `+z` to nadir;
  - GRACE leading (`-x` along velocity), still right-handed;
  - four bad axis pairs: the same axis, opposite axes, two unknown names.

At the start: 11 failed (all `NotImplementedError`), 443 passed. Against a scratch implementation kept out of the repository, all 454 pass.

**Traps:**

- **Columns, not rows.** `np.stack([X, Y, Z], axis=-1)` puts them as columns. `axis=1` would make them rows, giving the inverse rotation, which the hand-worked test catches.
- **Composition order.** In scipy, `a * b` applies `b` first; body_from_ITRF is `body_from_orbit * orbit_from_ITRF`.
- **The law's flight direction is the inertial one.** The test checks body x against the orbit frame's X, which differs by a few degrees from the ITRF velocity's direction.
- **Perpendicular means `a @ b == 0`.** Both the same axis and opposite axes fail.

## Review of component 2

All 454 tests passed and the functions follow the plan. The only changes are ruff's:

- a mis-indented comment and spacing in `inertial_velocity_in_itrf`;
- one long error message.

`inertial_velocity_in_itrf` accepts lists as well as arrays (numpy converts them), and a wrongly shaped input raises numpy's own "incompatible dimensions for cross product", which is clear enough.

## Component 3: Spire's orbit frame into ITRF, and shared epochs

| Function | Does |
| --- | --- |
| `attitude_in_itrf(attitude, states)` | returns an ITRF attitude as it is; turns `"orbit_level_spire"` into ITRF with the orbit frame from the states (body_from_ITRF = body_from_orbit · orbit_from_ITRF), saying so in the source |
| `check_same_epochs(attitude, states)` | raises unless both have exactly the same times on the same scale; the message gives the number shared and points to `common_epochs` |
| `common_epochs(attitude, states)` | both at the epochs they share exactly (`np.intersect1d`): selection, never interpolation; raises for different scales or nothing shared |

**Tests (component 3):** 6.

- a body aligned with the orbit frame (quaternion [0, 0, 0, 1]) gives the same attitude as the law with +x ahead and +z down, to 10⁻¹⁴;
- a half turn in yaw ([0, 0, 1, 0]) gives the law flying −x first (GRACE leading);
- an ITRF attitude passes through unchanged;
- different epochs raise, naming the shared count, and so do different scales;
- `common_epochs` keeps only the shared epoch, with its own state and rotation;
- it raises when nothing is shared, or the scales differ.

**Notebook section 12** reads the user's two FM134 files from paths set at its top (observed attitude only, `common_epochs`, `attitude_in_itrf`), or uses a circular polar orbit with the law when they are absent. It plots the direction of the velocity relative to the air in the body frame: the azimuth from +x in the x–y plane, and the elevation towards +z. It ran here both ways, without errors.

**First end-to-end result, from the user's files** (not committed):

- **493 shared observed seconds,** 09:52:13–10:00:27 GPS. The last three minutes of the overlap are repeated-value epochs, which `keep_observed` leaves out.
- **Azimuth −162.4°** (from −163.7° to −162.0°): FM134 flies **−x first**, turned about 18° in yaw.
- **Elevation −0.52°** (from −1.04° to +0.09°): the velocity lies within about a degree of the body x–y plane, consistent with body z at nadir.
- **Compared with the attitude law** (+x ahead, +z down), Spire's attitude is turned 165.0°–166.6°, in agreement with the attitude file's yaw near 180° (I2 plan).

**With the circular orbit and the law,** the azimuth swings between about −3.6° and +3.6°: the inertial flight direction (the law's +x) and the air's direction differ by the Earth's rotation, most at the equator.

## Done when

All three components are pushed, and notebook section 12 runs both ways. A4a is then complete, and A4b (each panel's angle to the flow, and the flow drawn on the spacecraft) can start.
