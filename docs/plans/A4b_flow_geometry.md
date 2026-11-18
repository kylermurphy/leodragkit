# A4b: The flow on each panel

Step plan for task A4b in `docs/tasks.md`; part of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Three components, one patch each.

**Status: done 2026-11-04 (D-88), pending the user's review of component 3.** The user's answers are at the end.

## Goal

For every panel and every epoch, find what the gas-surface models need about the flow's geometry: how squarely the flow meets the panel (cos δ), and which way the shear acts on it (t̂). Together with the speed and flow direction, these make up `PanelFlowGeometry`, the first input of every gas-surface model (D-52, D-53).

## Conventions (fixed by the gas-surface contract, D-50)

All vectors are in the **body frame**. With v_rel the spacecraft's velocity relative to the air (in ITRF this is the ITRF velocity, D-25, D-79), turned into the body frame by `attitude.body_from_reference`:

| Quantity | Formula | Meaning |
| --- | --- | --- |
| speed | V = \|v_rel\| | m/s |
| flow direction | û = −v_rel / V | the direction the air moves past the spacecraft |
| cos δ | n̂ · v̂_rel = −n̂ · û | +1: the panel faces the flow squarely (ram); 0: edge-on; negative: facing away (wake) |
| shear direction | t̂ = (û − (û · n̂) n̂) / \|û − (û · n̂) n̂\|, or **0** where sin δ = 0 | the flow direction projected onto the panel; with zero length when there is nothing to project |

These give the plate force of D-50, q·A·(C_p·(−n̂) + C_τ·t̂), and its drag C_d = C_p cos δ + C_τ sin δ, the form `gas_surface_sentman.py` already returns.

## Components

| # | Builds | Who |
| --- | --- | --- |
| 1 | `PanelFlowGeometry` (in `aero/frames.py`) and its checks | Claude (done) |
| 2 | `panel_flow_geometry(panel_set, attitude, states)`: V, û; and `incidence_and_shear(normals, û)`: cos δ (T, N), t̂ (T, N, 3), for normals (N, 3) or (T, N, 3) | user (done) |
| 3 | plot level 2: `plot_flow_on_spacecraft(panel_set, flow_geometry, epoch_index)`, the panels coloured by cos δ and the flow drawn as an arrow coming in; notebook section 13 | Claude (done) |

**`PanelFlowGeometry`:**

| Field | Shape | Checked |
| --- | --- | --- |
| `times`, `time_scale` | (T,) | as `Attitude` |
| `speed_m_per_s` | (T,) | finite, > 0 |
| `flow_direction` | (T, 3) | unit length |
| `cos_incidence` | (T, N) | in [−1, 1] |
| `shear_directions` | (T, N, 3) | unit length or zero; û · t̂ = sin δ = √(1 − cos²δ), which ties t̂ to cos δ without needing the normals, and catches a t̂ pointing upstream |

**Component 2, step by step:**

1. check that the attitude is in `"ITRF"` and shares the states' epochs (`check_same_epochs`);
2. v_rel in the body frame;
3. V, raising for zero, naming the epoch;
4. û;
5. cos δ for all panels at once, written so the normals can be (N, 3) or (T, N, 3) (D-88): with the normals as (T or 1, N, 3), `np.einsum("tk,tnk->tn", …)` after broadcasting, or the same with `@`;
6. t̂ by broadcasting û as (T, 1, 3) against the normals, with zero where the projection's length is below a small tolerance.

**Component 3:** Mesh3d faces coloured by cos δ on a diverging scale, from −1 (wake, blue) through 0 (edge-on, white) to +1 (ram, red), fixed so colours compare between epochs. The flow is an arrow arriving from upstream, pointing along û. For macro models (no triangles), the normals are drawn from the origin, coloured the same way. Notebook section 13: the 3U CubeSat example under the attitude law and under FM134's measured attitude, labelled clearly as **not FM134's geometry** (Spire's geometry is not in the project).

## Tests planned

**Component 2:**

- a cube flying +x first: the +x face has cos δ = 1 and t̂ = 0; the ±y and ±z faces have cos δ = 0 and t̂ = û; the −x face has −1;
- a plate turned 45°: cos δ = √2/2, with t̂ along the plate, downstream;
- t̂ always perpendicular to n̂, of length 1 or 0, for random attitudes;
- the drag of a whole closed convex body, Σ A (C_p cos δ + C_τ sin δ), unchanged by turning the body about the flow direction;
- a Spire-attitude case agrees with the law case (from A4a's tests);
- normals given as (T, N, 3), the same at every epoch, give the same result as (N, 3) (D-88);
- a slice of epochs gives the same rows as the full computation, which is what makes A5's chunking safe (D-88);
- zero speed, a non-ITRF attitude, and different epochs each raise.

**Component 3:** the figure's traces, colours fixed to [−1, 1], the arrow along û, and a macro model drawn without triangles.

## Component 1: done

`PanelFlowGeometry` is in `aero/frames.py`, with `UNIT_LENGTH_TOLERANCE` (10⁻⁹) for unit or zero lengths. It checks:

- the times;
- each array's shape and finiteness;
- positive speeds, unit flow directions, and cosines in [−1, 1];
- shear directions of unit length or zero;
- û · t̂ = sin δ to 10⁻⁶.

**Tests (component 1):** 11, in `tests/aero/test_flow_geometry.py`.

- **Hand-worked:** a cube flying +x first, plus a plate turned 45°. The +x face has cos δ = 1 and no shear; the four side faces are edge-on, with shear along û; the −x face has −1. The 45° plate has cos δ = sin δ = 1/√2, with t̂ = (−1, 1, 0)/√2.
- **The definitions:** the hand values are recomputed from cos δ = −n̂ · û and t̂ = û − (û · n̂) n̂.
- **Eight inconsistencies,** each named, including a shear pointing upstream.
- **Times** that aren't increasing.

## Component 2: the user's part

Two functions, in `aero/frames.py`, each with its formula and numbered steps:

| Function | Does |
| --- | --- |
| `panel_flow_geometry(panel_set, attitude, states)` | refuses an attitude not in ITRF, and different epochs (`check_same_epochs`); v_rel in the body frame; V, refusing zero and naming the epoch; û = −v_rel / V; then `incidence_and_shear` with the panels' (N, 3) normals; a `PanelFlowGeometry` on the attitude's times |
| `incidence_and_shear(outward_normals, flow_direction)` | cos δ = −n̂ · û and t̂ = the projection of û onto each panel, made unit length (zero below `SHEAR_PROJECTION_TOLERANCE`, 10⁻¹²), for normals (N, 3) or (T, N, 3) by broadcasting: the normals as (1 or T, N, 3), û as (T, 1, 3) |

Splitting the maths into `incidence_and_shear` lets moving parts pass (T, N, 3) normals later (D-88) without touching `panel_flow_geometry`.

**Required reading:**

- this plan's "Conventions";
- D-50 and D-88;
- `PanelFlowGeometry`'s docstring and checks;
- numpy broadcasting: arrays of shapes (T, 1, 3) and (1, N, 3) combine into (T, N, 3);
- `np.divide` with `out=` and `where=`.

About 30 min.

**Tests (component 2):** 11.

- **`incidence_and_shear`:**
  - the hand-worked cube and plate;
  - (T, N, 3) normals, the same at every epoch, equal to (N, 3);
  - normals that turn round between epochs change every cos δ's sign;
  - turning 40 random panels about the flow direction keeps every cos δ and turns every t̂ with them;
  - for random flows, t̂ lies in each panel's plane, has unit length, and û · t̂ = sin δ.
- **`panel_flow_geometry`:**
  - the whole calculation reproduces the hand-worked values (body axes = ITRF, flying +x);
  - under the attitude law on a polar orbit at the equator, the +x face's cos δ = cos(atan(ωR / V)), the Earth's rotation of about 3.6°;
  - a slice of epochs gives exactly the same rows as the full calculation (D-88: what makes chunking safe);
  - a non-ITRF attitude, different epochs, and zero speed (naming epoch 1) are each refused.

At the start: 11 failed (all `NotImplementedError`), 484 passed. Against a scratch implementation kept out of the repository, all 495 pass.

**Traps:**

- **The sign of cos δ:** it is −n̂ · û. û is where the air goes, so a face meeting it head-on has n̂ · û = −1.
- **Broadcasting the normals:** give (N, 3) a leading axis of 1, `normals[np.newaxis]`. (T, N, 3) needs nothing.
- **Dividing by a zero projection:** `np.divide(projection, length[..., np.newaxis], out=np.zeros_like(projection), where=length[..., np.newaxis] > SHEAR_PROJECTION_TOLERANCE)`. `where` needs the same shape as the result, hence the `[..., np.newaxis]`.
- **The check on `PanelFlowGeometry`** (û · t̂ = sin δ) will catch a t̂ pointing upstream, so a sign slip in the projection shows up as a clear error.

## The user's answers (2026-11-04; D-88)

1. **Inputs:** yes.
2. **Centroids:** left out of `PanelFlowGeometry`, with the maths written for normals of shape (N, 3) or (T, N, 3), so moving parts can come in later as time-dependent component poses.
3. **Chunking:** in A5, not here, plus a slice test here; no parallel work until A5's benchmark shows a need.
4. **Zero speed** raises: yes.
5. **Colours:** yes. Edge-on, white, means the flow is perpendicular to the panel's normal: it skims along the surface.

## Review of component 2

All 495 tests passed, and both functions follow the plan. The one change: `panel_flow_geometry` called `common_epochs` after `check_same_epochs`. Once the check has passed the two inputs share every epoch, so the call changed nothing but cost a sort and a copy, and suggested matching happens here. It was removed, with the rest using `attitude` and `states` directly. Ruff: one long error message, and comment spacing.

## Component 3: the flow drawn on the spacecraft

`plot_flow_on_spacecraft(panel_set, geometry, epoch_index=0)`, in `plots/spacecraft.py`:

- **with triangles:** one `Mesh3d`, each triangle coloured by its cos δ (`intensitymode="cell"`), on `INCIDENCE_COLORSCALE` fixed to [−1, 1];
- **macro models:** normals from the origin, length proportional to area, with markers coloured by cos δ;
- **the flow:** a line from upstream ending in a cone along û;
- **also:** the triangle edges and body axes as in `plot_panel_set_3d`, and a title with the time and speed;
- **refuses** a geometry for a different number of panels, and an epoch out of range.

**Tests (component 3):** 5, in `tests/plots/test_flow_plot.py`.

- the unit cube flying +x first: each triangle's colour equals its cos δ (+1 on the +x face, −1 on −x, 0 on the sides), with the scale fixed;
- the second epoch (+y first) colours the +y face;
- the flow cone points along −x and comes in from +x;
- a macro model's markers are coloured by cos δ;
- refusals.

**Notebook section 13:** the 3U CubeSat example (1700 panels) under section 12's attitude, coloured at the first epoch, and the **area facing the flow**, Σ A·max(cos δ, 0), by component. It ran here both ways:

| | Bus | Each panel | Antenna | Total |
| --- | --- | --- | --- | --- |
| FM134's attitude (−x first, 18° yaw; 493 epochs) | 0.043 m² | 0.029 m² | 0.002 m² | 0.102 m² |
| attitude law (+x first; 540 epochs) | 0.036 m² | 0.030 m² | 0.002 m² | 0.097 m² |

These check by hand. Under FM134's attitude, the bus's −x face (0.1 × 0.34 m) at cos 18° is 0.032 m², plus 0.011 m² from the −y side at sin 18°; each panel (0.3 × 0.1 m) at cos 18° is 0.029 m². The panels are more than half the area facing the flow.

**Fix after the user's first look (2026-11-04):** in the notebook, both sides of each solar panel looked blue, though the numbers were right: the −x side had cos δ = +0.957 (red) and the +x side −0.957 (blue). A two-sided plate's two sides are triangles in exactly the same place, so the renderer showed one of them from both directions. `plot_flow_on_spacecraft` now draws each triangle `DISPLAY_OFFSET_FRACTION` (0.2 %) of the spacecraft's size out along its own normal. That is display only, never used in a calculation, and each side is then seen from its own side. A test with a two-sided plate checks that the side facing the flow is drawn on the upstream side; it fails without the offset.
