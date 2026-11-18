# A4b: The flow on each panel

Step plan for task A4b in `docs/tasks.md`; part of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Three components, one patch each.

**Status: agreed 2026-11-04 (D-88); component 1 done.** The user's answers are at the end.

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
| 2 | `panel_flow_geometry(panel_set, attitude, states)`: V, û, cos δ (T, N), t̂ (T, N, 3) | user |
| 3 | plot level 2: `plot_flow_on_spacecraft(panel_set, flow_geometry, epoch_index)`, the panels coloured by cos δ and the flow drawn as an arrow coming in; notebook section 13 | Claude |

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

## The user's answers (2026-11-04; D-88)

1. **Inputs:** yes.
2. **Centroids:** left out of `PanelFlowGeometry`, with the maths written for normals of shape (N, 3) or (T, N, 3), so moving parts can come in later as time-dependent component poses.
3. **Chunking:** in A5, not here, plus a slice test here; no parallel work until A5's benchmark shows a need.
4. **Zero speed** raises: yes.
5. **Colours:** yes. Edge-on, white, means the flow is perpendicular to the panel's normal: it skims along the surface.
