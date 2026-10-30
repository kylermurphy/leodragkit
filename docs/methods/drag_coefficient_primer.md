# Drag coefficient primer

The method behind `leodragkit.aero`: how a satellite's drag area Cd·A(t), and its ballistic coefficient B(t) = Cd·A(t)/m, follow from its geometry, its attitude and the atmosphere. Written 2026-10-27 in a planning discussion; brought into the repository 2026-10-28 after a citation pass and two corrections (see "Changes from the planning version" at the end).

Decisions are cited as `D-NN` (`docs/decisions.md`). This document holds no run results; those go in `docs/results_log.md` (`R-NN`).

## What we are building

The goal is one number per epoch: **Cd·A(t)/m** for a satellite with known geometry and attitude. It lives in `leodragkit.aero`. contigo_edr uses it for effective-density retrieval, and leodragkit's own ballistic-coefficient estimation can use it in `scaled_aero` mode (D-22). It is tractable because at 400–600 km the drag on each flat face has a closed-form formula, and the whole satellite is the sum over its faces.

The calculation has four inputs:

1. **Geometry:** a list of flat panels (outward normal in the body frame, area).
2. **Attitude:** quaternions, which rotate each panel normal into the frame of the relative velocity.
3. **Atmosphere:** gas temperature and composition from NRLMSIS (through leodragkit's density interface), which set the molecular speed ratio.
4. **Surface physics:** an energy accommodation coefficient α and a wall temperature T_w.

Sentman's flat-plate formula is applied to each panel, the results are summed over panels, and the sum is divided by mass. The judgement lives in the inputs, mainly α and geometry, and in a few conventions that the literature handles inconsistently ("Choices and pitfalls").

## Core concepts

| Concept | Plain-language meaning | Source |
| --- | --- | --- |
| Free-molecular flow | Air molecules almost never collide with each other near the satellite, so each one hits the surface independently. The panel method agrees with DSMC for convex shapes where the Knudsen number Kn ≥ 10; 400–600 km is well inside this regime. | Mehta et al. 2023, §2.1; Sinpetru et al. 2022b |
| Molecular speed ratio s | Orbital speed divided by the most probable thermal speed of the gas. Large s means molecules arrive almost as a beam; smaller s means thermal motion lets them also hit side and rear faces. | March et al. 2021, eq. 1 |
| Specular vs diffuse reflection | Specular: a molecule bounces off like a mirror. Diffuse: it forgets its incoming direction and leaves in a cosine-law spray. At 400–600 km the standard model is diffuse reflection with incomplete accommodation (DRIA). | Mehta et al. 2023 |
| Energy accommodation α | How much of its energy a molecule gives up to the wall before leaving. α = 1: it leaves at wall temperature (slow). α = 0: it keeps its energy (fast). | Sinpetru et al. 2022a, eq. 2 |
| Why Cd > 2 | Incoming momentum alone gives Cd ≈ 2 per unit projected area. Re-emitted molecules add a backward recoil, which grows as α falls; thermal motion and shear on side faces add more. | Moe & Moe 2005 |
| Panel method | Treat each face as an isolated flat plate, add up the forces, zero out faces hidden behind others (shadowing), and ignore molecules that bounce between faces. It degrades for concave features and faces parallel to the flow. | Sinpetru et al. 2022a, 2022b |

The key sensitivity is α. Observed α falls with altitude, from about **1.00** near 200 km to about **0.86** near 300 km, as atomic-oxygen contamination of surfaces thins out (Moe & Moe 2005). A model run for ADBSat's validation gave **0.81** at 400 km (Sinpetru et al. 2022b, Table 1), and March et al. (2021) found **0.85** best for consistency across Swarm.

## Equations, step by step

Symbols: V is the satellite speed relative to the co-rotating atmosphere (D-25), m is molecular mass, k_B is Boltzmann's constant, T∞ the ambient gas temperature, T_w the wall temperature. Equation numbers for Sinpetru et al. 2022a are those of its preprint (arXiv:2104.05543v2), which may differ from the journal version.

### Step 1: speed ratio

The most probable thermal speed sets the scale (March et al. 2021, eq. 1):

```math
s = \frac{V}{\sqrt{2 k_B T_\infty / m}}
```

Use the most probable speed, not the rms or mean speed. With a gas mixture, ADBSat uses one mean molecular mass; step 5 gives the per-species alternative.

### Step 2: speed of re-emitted molecules

Accommodation is defined on energies (Sinpetru et al. 2022a, eq. 2):

```math
\alpha = \frac{E_i - E_r}{E_i - E_w}
```

This becomes a ratio r of re-emitted to incoming speed. Two conventions exist, differing by a constant k and the definition of the incident temperature T_i:

```math
r = \frac{V_r}{V_i} = \sqrt{k\left[1 + \alpha\left(\frac{T_w}{T_i} - 1\right)\right]}
```

- **Cook / Moe:** k = 2/3 and T_i = mV²/(3k_B) (Moe & Moe 2005; March et al. 2021, eq. 3).
- **Koppenwallner / ADBSat code:** k = 1/2 and T_i = mV²/(4k_B) = ½ s² T∞. The header of ADBSat's `coeff_sentman.m` says it uses Koppenwallner's factor of 1/2 rather than Moe's 2/3, and the code sets `Ti = 1/2*s.^2*Tinf`.

Since s² = mV²/(2k_B T∞), both conventions give **T_i = k s² T∞** (derived). At α = 1 both reduce to r = √(T_w / (s² T∞)), so they agree; they diverge as α falls ("Choices and pitfalls"). leodragkit defaults to k = 1/2 (D-24).

The preprint's eq. 6 prints the re-emission factor as αT_w/(T_i − 1); the intended form, used in the code, is α(T_w/T_i − 1). As laid out in the preprint, eq. 6 also carries the factor 2/3 inside the square root, while the code uses 1/2.

### Step 3: one flat plate (Sentman, diffuse reflection)

Let δ be the angle between the oncoming flow and the plate's **outward** normal: δ = 0 faces straight into the flow, δ > 90° faces backward. With n̂ the outward normal and v̂ the satellite's velocity direction relative to the atmosphere, cos δ = n̂·v̂. This is Sinpetru et al. 2022a, eq. 25, which writes δ = arccos(−n̂_v·n̂) with n̂_v the direction of the flow, opposite to v̂.

Pressure and shear coefficients, referenced to the plate's own area (Sinpetru et al. 2022a, eqs. 6–7, written with r from step 2):

```math
C_p = \left(\cos^2\delta + \frac{1}{2s^2}\right)\left[1 + \mathrm{erf}(s\cos\delta)\right] + \frac{\cos\delta}{s\sqrt{\pi}}e^{-s^2\cos^2\delta} + \frac{r}{2}\left[\sqrt{\pi}\cos\delta\left(1 + \mathrm{erf}(s\cos\delta)\right) + \frac{1}{s}e^{-s^2\cos^2\delta}\right]
```

```math
C_\tau = \sin\delta\cos\delta\left[1 + \mathrm{erf}(s\cos\delta)\right] + \frac{\sin\delta}{s\sqrt{\pi}}e^{-s^2\cos^2\delta}
```

The plate's drag coefficient is their component along the flow:

```math
c_d = C_p\cos\delta + C_\tau\sin\delta
```

Moe & Moe (2005, eq. 4) give the same drag coefficient in a compact form, a useful cross-check.

**Back faces need no special case, but they are not zero.** For a back-facing plate (cos δ < 0), molecules striking and leaving the rear face push the plate forward, so c_d is small and **negative**. At s = 7 it is negligible (about −1 × 10⁻²⁵); at s = 1 it is about −0.05 (α = 0.9, T∞ = 1000 K, T_w = 300 K). Compute 1 + erf(x) as erfc(−x): on a back face the erf form loses every digit and, from s ≈ 7, even the sign (R-03). Never clip it to zero: summed over a sphere, the plate formula matches Bird's closed-form sphere drag only with this sign (R-01).

### Step 4: whole satellite → Cd·A/m

Rotate each body-frame normal with the quaternion, compute its δ, and sum the plate drags weighted by panel area, with shadowed panels set to zero (Sinpetru et al. 2022a, eq. 26):

```math
\cos\delta_i(t) = \big(R(q(t))\,\hat n_i^{\,body}\big)\cdot\hat v(t), \qquad (C_dA)(t) = \sum_i A_i\, c_{d,i}(t)\,\big(1 - \mathrm{shadow}_i(t)\big), \qquad B(t) = \frac{(C_dA)(t)}{m_{sat}}
```

The sum keeps each panel's sign (step 3). ADBSat's force sum, eq. 26 and `calc_coeff.m`, is likewise signed.

Store Cd·A rather than Cd: Cd alone is meaningless without its reference area, and ADBSat's default reference area is half the total surface area (Sinpetru et al. 2022a, §3). Lift is not computed (D-26): it acts perpendicular to the relative velocity, so it does no work in the co-rotating frame and never enters the energy dissipation rate.

### Step 5: gas mixtures

The exact treatment computes Cd per species with its own speed ratio and mass-weights the result (Mehta et al. 2023, eq. 11):

```math
C_D = \frac{\sum_k \chi_k m_k C_{D,k}}{\sum_k \chi_k m_k}, \qquad \chi_k = \frac{n_k}{\sum_j n_j}
```

Number densities n_k and T∞ come from leodragkit's `AtmosphereState` (D-10). Start with the single mean-mass version and add per-species later as a sensitivity test.

### Step 6: accommodation from atomic oxygen (later refinement)

Adsorbed atomic oxygen raises α. The standard model treats the fraction θ of the surface covered by oxygen as a Langmuir isotherm, and blends clean and covered surfaces (Mehta et al. 2023, eqs. 6–7, 13–14):

```math
\theta = \frac{k_L P_O}{1 + k_L P_O}, \qquad P_O = n_O k_B T_\infty, \qquad C_D = (1-\theta)\,C_{D,s} + \theta\,C_{D,ads}
```

The covered surface has α_ads = 1. The clean surface uses Goodman's α_s = K_s μ/(1+μ)², with μ the gas-to-surface-atom mass ratio and K_s between 2.4 and 3.6 (Mehta et al. 2023, eq. 5). For DRIA, k_L = **1.44 × 10⁶** (Mehta et al. 2023, citing Walker et al. 2014). Walker et al. (2014) give K in Pa⁻¹ (their nomenclature), with 2.89 × 10⁶ Pa⁻¹ for CLL; Dey et al. (2025a, eq. 2.15) use the same values. Begin with a fixed α swept over a range, and add this model once the rest works.

## Choices and pitfalls

Each of these can change Cd·A by percent-level amounts or more, so each one is an explicit, recorded parameter.

| Choice | Options | Effect | leodragkit |
| --- | --- | --- | --- |
| Reflected-speed convention (step 2) | k = 1/2 (ADBSat code) or 2/3 (Cook, Moe, March) | Identical at α = 1; head-on plate differs by 2.4% at α = 0.9 and 5.9% at α = 0 (derived) | Parameter, default 1/2 (D-24) |
| Energy accommodation α | Fixed value, or Langmuir oxygen model | The dominant uncertainty; the gas-surface model moves densities by tens of percent above about 450 km at solar minimum (Mehta et al. 2023) | Explicit input, no default; swept first (D-23) |
| Wall temperature T_w | 300 K (Parham & Barba 2014) or 400 K (Mehta et al. 2023; March et al. 2021) | Enters only through √T_w in the re-emission term; small next to α (derived) | Explicit input, no default (D-23) |
| Angle convention | Angle to outward vs inward normal; flow direction vs satellite velocity | A sign slip turns ram faces into wake faces | cos δ = n̂_outward · v̂_rel, unit-tested (D-28) |
| Back faces | Keep the sign, or clip to zero | Clipping overestimates drag at low s (R-01) | Keep the sign |
| Reference area | Projected area, half total area (ADBSat default), anything else | Cd values not comparable across sources | Store Cd·A only (D-28) |
| Relative velocity | Inertial vs co-rotating atmosphere; winds | Several percent in speed and direction | Co-rotating, no winds (D-25) |
| Mixture treatment | Single mean mass vs per-species | Matters more at higher altitude, where helium grows | Mean mass first; per-species as sensitivity (D-28) |
| Shadowing | None vs barycentre-projection test | Deployed panels can hide body faces at some attitudes | Added once a geometry needs it |
| Panel-method limits | Concave features, faces parallel to the flow, multiple reflections | ADBSat's verification adopts an error interval of up to 3% (Sinpetru et al. 2022b) | Check against a test-particle code once for a real geometry |
| ADBSat paper typos | Eq. 6 bracket; eq. 4 lift sign; eq. 28 does not normalise the shear direction | Wrong numbers if copied from the paper | Follow the corrected forms here |

On the last row: the code normalises the shear direction after computing it as in eq. 28 (`calc_coeff.m`). The eq. 4 lift-sign typo is the planning version's reading and was not rechecked; lift is not computed here.

## Verification cases for unit tests

The open sources give no tabulated Cd numbers for a plate, so the plate reference values below are **derived** from the equations above. They are regression values, not published results. They become test references only after task A2 reproduces them independently (Q-04).

| Case | Inputs | Reference Cd |
| --- | --- | --- |
| Sphere, fully diffuse (Bird's formula; Parham & Barba 2014, eq. 4) | T∞ = 922 K, T_w = 300 K, s = 5 | 2.2140 |
| Same | s = 7.5 | 2.1253 |
| Same | s = 10 | 2.0874 |
| Flat plate head-on (δ = 0), k = 1/2 | s = 7, T∞ = 1000 K, T_w = 300 K, α = 1.0 | 2.1591 |
| Same | α = 0.9 | 2.4380 |
| Same | α = 0.0 | 3.2737 |
| Flat plate head-on, k = 2/3 | s = 7, T∞ = 1000 K, T_w = 300 K, α = 1.0 | 2.1591 |
| Same | α = 0.9 | 2.4966 |
| Same | α = 0.0 | 3.4676 |

Bird's formula, as given by Parham & Barba (2014, eq. 4), with S_W the speed ratio at the wall temperature (1/S_W = r at α = 1):

```latex
C_D = \frac{e^{-S^2}}{\sqrt{\pi}\,S^3}\left(1 + 2S^2\right) + \frac{4S^4 + 4S^2 - 1}{2S^4}\,\mathrm{erf}(S) + \frac{2\sqrt{\pi}}{3 S_W}
```

Structural tests that need no reference numbers:

- **Single panel.** A single-panel plate summed through step 4 equals the closed form to machine precision. ADBSat's verification shows panel versus closed form within 0.1% (Sinpetru et al. 2022b).
- **Sphere.** A finely meshed sphere converges to Bird's formula. An integral of the plate formula over the sphere already matches it to six decimals for s from 0.5 to 10 (R-01).
- **Hyperthermal limit.** As s → ∞, Sentman approaches Cook's hyperthermal formula (Sinpetru et al. 2022a, eq. 18). With no re-emission as well (r = 0), the pressure coefficient reduces to Newton's C_p = 2cos²δ (eq. 20), and the drag coefficient to **2cos δ**, because the shear term adds 2sin²δ cos δ. Eq. 18 gives the same 2cos δ when its re-emission term is removed.
- **Back faces.** A back-facing plate gives a small negative c_d, negligible at s = 7 and growing in size as s falls.
- **Symmetry.** Rotating a cube by any attitude and summing gives a smooth, symmetric Cd·A; a 180° yaw of a symmetric 3U leaves Cd·A unchanged.
- **ADBSat.** Compare with ADBSat itself for the same mesh and inputs, once a real geometry exists.

## Existing tools

No open-source Python package does this with variable accommodation, so leodragkit has its own small module, checked against existing codes. Software is cited by repository and licence.

| Tool | Language | Fit for this work |
| --- | --- | --- |
| [ADBSat](https://github.com/nhcrisp/ADBSat) (GPL-3.0) | MATLAB | Right physics (panel method, Sentman and other models, shadowing). Used as a reference and test oracle, never as a dependency or a source to translate (D-28, D-32). The relevant files are `toolbox/fmf_eq/coeff_sentman.m` and `toolbox/calc/calc_coeff.m`. |
| [VLEO Aerodynamics Tool](https://github.com/ifrunistuttgart/vleo-aerodynamics-tool) (GPL-3) | C++20, MATLAB bindings | Six reflection models, meshes, shadowing, hinged panels; needs Windows, Visual Studio and an OpenGL 4.3 GPU; no Python interface |
| [panelsolver](https://github.com/pandorobo11/panelsolver) (Apache-2.0) | Python | STL input, ray-cast shadowing, Sentman; assumes full accommodation (α = 1); v0.1.0, unproven. A quick shadowing sanity check at most |
| [LANL RSM tool suite](https://github.com/AndrewCWalker/rsm_tool_suite) (GPL-2) | C test-particle Monte Carlo, MATLAB response-surface fit | The C code (`TPM/tpm.c`) reads an STL and handles shadowing and multiple reflections; use it to check the panel method on a real geometry |
| [VLEO-DSMC](https://github.com/John-Auerbach/VLEO-DSMC) | SPARTA DSMC with NRLMSIS 2.1 | Full DSMC; reference only, far too heavy per epoch |

Only ADBSat's licence and files were checked in the citation pass; the other rows are from the planning version.

Where the steps live in leodragkit:

| Step | Module |
| --- | --- |
| 2–3 | `aero/gas_surface.py` (the contract), `aero/gas_surface_sentman.py` |
| 4 | `aero/panel_geometry.py`, `aero/attitude.py`, `aero/drag_area.py` |
| 1, 5 | `aero/drag_area.py`, with the atmosphere state from `density` |

## References

Read roughly in this order; the first five cover everything needed to write the code.

1. Mehta, P. M., Paul, S. N., Crisp, N. H., Sheridan, P. L., Siemes, C., March, G., et al. (2023). Satellite drag coefficient modeling for thermosphere science and mission operations. *Advances in Space Research*, 72, 5443–5459. doi:[10.1016/j.asr.2022.05.064](https://doi.org/10.1016/j.asr.2022.05.064). Open access. The best modern overview: reflection models, accommodation, the oxygen-adsorption model, and why it matters for density.
2. Moe, K., & Moe, M. M. (2005). Gas–surface interactions and satellite drag coefficients. *Planetary and Space Science*, 53, 793–801. doi:[10.1016/j.pss.2005.03.005](https://doi.org/10.1016/j.pss.2005.03.005). Physical intuition: measured α against altitude, and why Cd exceeds 2.
3. Sinpetru, L. A., Crisp, N. H., Mostaza-Prieto, D., Livadiotti, S., & Roberts, P. C. E. (2022a). ADBSat: Methodology of a novel panel method tool for aerodynamic analysis of satellites. *Computer Physics Communications*, 275, 108326. doi:[10.1016/j.cpc.2022.108326](https://doi.org/10.1016/j.cpc.2022.108326). Preprint read: [arXiv:2104.05543v2](https://arxiv.org/abs/2104.05543). Every flat-plate formula, shadowing and the panel sum in one place; mind the typos.
4. ADBSat source code, [github.com/nhcrisp/ADBSat](https://github.com/nhcrisp/ADBSat), GPL-3.0. The reference implementation to check against.
5. Sinpetru, L. A., Crisp, N. H., Mostaza-Prieto, D., Livadiotti, S., & Roberts, P. C. E. (2022b). ADBSat: Verification and validation of a novel panel method for quick aerodynamic analysis of satellites. *Computer Physics Communications*, 275, 108327. doi:[10.1016/j.cpc.2022.108327](https://doi.org/10.1016/j.cpc.2022.108327). Preprint: [arXiv:2110.06118](https://arxiv.org/abs/2110.06118). What panel methods get right and wrong.
6. March, G., van den IJssel, J., Siemes, C., Visser, P. N. A. M., Doornbos, E. N., & Pilinski, M. (2021). Gas-surface interactions modelling influence on satellite aerodynamics and thermosphere mass density. *Journal of Space Weather and Space Climate*, 11, 54. doi:[10.1051/swsc/2021035](https://doi.org/10.1051/swsc/2021035). Open access. How the α choice propagates into CHAMP, GOCE and Swarm densities; relevant to the CHAMP validation (task A6).
7. Parham, J., & Barba, L. A. (2014). Finding the Force: Consistent Particle Seeding for Satellite Aerodynamics. *AIAA Modeling and Simulation Technologies Conference*. doi:[10.2514/6.2014-1492](https://doi.org/10.2514/6.2014-1492). Version read: [arXiv:1312.3691](https://arxiv.org/abs/1312.3691), whose comment says it was presented at that conference. Closed-form sphere Cd (eq. 4), used as a test oracle.
8. Doornbos, E. (2012). *Thermospheric Density and Wind Determination from Satellite Dynamics*. Springer Theses. doi:[10.1007/978-3-642-25129-0](https://doi.org/10.1007/978-3-642-25129-0). The published version of the 2011 TU Delft thesis: the panel models and Sentman vector form used for CHAMP and GRACE densities. Not read; section numbers to be confirmed against this version (Q-03).
9. Walker, A., Mehta, P., & Koller, J. (2014). *Journal of Spacecraft and Rockets*, 51. doi:[10.2514/1.A32677](https://doi.org/10.2514/1.A32677). Paywalled. Origin of the Langmuir k_L values and their units.
10. Pilinski, M. D., Argrow, B. M., & Palo, S. E. (2010). Semiempirical model for satellite energy-accommodation coefficients. *Journal of Spacecraft and Rockets*, 47. doi:[10.2514/1.49330](https://doi.org/10.2514/1.49330). Paywalled. The α-versus-oxygen model behind ADBSat's validation runs.

## Citation check (2026-10-28)

Every DOI above was resolved through Crossref, and its title, authors, venue and year match. Beyond that, these claims were rechecked against the source:

| Source | Rechecked | Not rechecked |
| --- | --- | --- |
| Sinpetru et al. 2022a (preprint v2) | eqs. 2, 6–7 (and the eq. 6 bracket typo), 18, 20–21, 25, 26, 28; reference area of half the mesh surface | eq. 4 lift sign |
| ADBSat code (master branch) | GPL-3.0 licence; k = 1/2 and T_i = ½ s² T∞ in `coeff_sentman.m`; the shear direction normalised and the force sum signed in `calc_coeff.m` | |
| Parham & Barba (arXiv version) | eq. 4, Bird's sphere drag; presented at the AIAA conference of the DOI | equation numbering in the AIAA version |
| Moe & Moe 2005 | α from about 1.00 near 200 km to about 0.86 near 300 km | eq. 4 (equations not extractable from the copy read) |
| Sinpetru et al. 2022b | preprint linked to the journal DOI | Table 1 (0.81 at 400 km), the 3% error interval |
| March et al. 2021; Mehta et al. 2023 | | equation numbers and quoted values (publisher sites block automated access) |
| Walker et al. 2014 (added 2026-10-29, PDF) | K in Pa⁻¹ | |
| Pilinski et al. 2010; Doornbos 2012 | | content (Pilinski read for `docs/aero_plan.md` only; Doornbos not read) |

## Changes from the planning version

- **Hyperthermal limit corrected.** The planning version said drag approaches Newton's 2cos³δ. Drag approaches 2cos δ; only the pressure coefficient approaches 2cos²δ. Sinpetru et al. 2022a, eq. 18, gives 2cos δ.
- **Back-face sign corrected.** The planning version said a back-facing plate gives a non-negative c_d. It is small and negative (R-01). The value at s = 7 first quoted here (3 × 10⁻²³) was a rounding error of the 1 + erf form; corrected 2026-10-29 (R-03).
- **Citations.** The Moe & Moe link to an unofficial mirror is replaced by its DOI. Links are now DOIs, with the preprints read listed alongside.
- **Other changes:**
  - the derived identity T_i = k s² T∞ is added;
  - Bird's formula is written out;
  - the "next step" checklist is removed (the order of work is in `docs/tasks.md`);
  - the package name and module names now match leodragkit.
