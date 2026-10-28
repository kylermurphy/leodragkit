---
paths:
  - "leodragkit/orbit/**"
  - "leodragkit/forecast/**"
  - "leodragkit/workflows/**"
  - "tests/orbit/**"
  - "tests/forecast/**"
  - "tests/workflows/**"
---

# Orbit, forecast and workflows

Rules for the Orekit-based workflows: start states, propagation with drag, comparison with observations, ballistic-coefficient estimation and ensemble forecasts. Conventions marked `swift D-NN` were decided in `swift_reentry/docs/decisions.md`. Each one gets its own entry in this repository's `docs/decisions.md` in the step that ports the code it governs.

## Science conventions (change only with the user's approval)

1. **Time.** Times are UTC throughout.
2. **Reentry** is the first downward crossing of 100 km geodetic altitude above WGS84 (swift D-01).
3. **Comparisons use the orbit-mean geodetic altitude** over one orbital period after an epoch, never a single osculating state (`swift_reentry/compare.py`, module docstring). It is named by source, with the method in brackets (swift D-38):
   - observed state: "state vector (zero-density propagation)" or "SP3 (zero-density propagation)";
   - "TLE (SGP4)";
   - "model run (decay log)".
4. **Matched observable for B estimation.** The observed state and the model's end state are reduced by the identical zero-density one-orbit procedure. Never average the drag run's own log instead (swift D-29).
5. **Drag depends only on B = Cd·A/m.** B estimation has two modes, chosen in config (D-22):
   - `constant`: one B per density model;
   - `scaled_aero`: one factor k per density model, with B(t) = k · B_aero(t).

   While time-varying B in Orekit is deferred (D-20), `scaled_aero` propagates with B_aero averaged per orbit.
6. **Solar radiation pressure** is refused in every B estimation, and in ensemble runs whenever a model has its own B (swift D-39). The estimated B sets the area, which SRP would also use.
7. **Ensemble members** replay historical space weather mapped onto the present: sim time `t` maps to historical time `h = h0 + (t − t0)`.
   - Drivers come from historical time; solar geometry, day of year, local time and frames come from sim time (swift D-02, D-04).
   - A member whose drivers run out is **truncated, never extended** (swift D-05).
8. **F10.7 for members** is a multiplicative anomaly on the NOAA baseline (swift D-08), built in `forecast/driver_futures.py` and passed through each model's `f107_features` (D-19).
   - The historical flux is observed flux (swift D-09).
   - Beyond the 45-day forecast, the baseline is held at the mean of its last 27 days (swift D-10).
   - Geomagnetic drivers are raw historical values, with no anomaly and no blending (swift D-11).
9. **Statistics:**
   - quantiles over historical members only, with the reference member reported separately;
   - non-reentered members censored at +∞, never dropped;
   - ECDFs normalised by the full member count (swift D-07).
10. **Density models stay free of Orekit types.** `orbit/atmosphere_adapter.py` is the only code that converts Orekit arguments into density-model inputs.
11. **JB2008**, when added, uses only real historical indices for its drivers. How its drivers are built for ensemble members needs a decision first.
12. **Integrator settings** start at 10 m position tolerance and 300 s maximum step, as measured for Swift (swift D-41). Another satellite or altitude range needs its own convergence check before a different setting is used.

The remaining swift_reentry B-estimation rules are reviewed and entered when `orbit/ballistic_coefficient.py` is ported. These cover the analytic κ, the weather-noise streams and lead-ins, and the nominal B as a median (swift D-30 to D-32).

## Orekit and JPype

- **Check every Orekit API against the installed jar** (`javap -cp <orekit jar> <class>` or `Class.getMethods()`). Names changed between Orekit 11, 12 and 13.
- **Implement every interface method in a JPype proxy, defaults included.** JPype proxies on Java 25 cannot call interface default methods (see `swift_reentry/atmosphere.py`, module docstring).
- **Field (automatic-differentiation) overloads that are not supported raise `UnsupportedOperationException`**, so a later change that starts using them fails loudly instead of dropping derivatives.
- **Keep the original Python exception** when an exception raised inside a Java callback comes back wrapped, so the caller can classify it (for example drivers running out → truncated member).
- **Start the JVM on first use, never on import.** Read Orekit data from the location in the main config, never from the network.
- **orekit_jpype is pinned** in `environment.yml`; do not bump it casually.

## Runs

- Seeds, member offsets and the drivers each member used are saved with the run.
- The ensemble forecast and the B Monte Carlo write each task as it finishes. A resume refuses a run whose settings or input records (D-15) differ from the saved ones, unless the user allows it and the manifest records that.
- Test new code on a small subset of members first. Long runs go in the background.

## Known pitfalls

- **pandas 3:** `pd.date_range` and `pd.to_datetime` default to microsecond resolution. Never assume int64 values are nanoseconds; use `.as_unit("ns")`.
- **TLEs** carry SGP4's own drag. Compare them through SGP4, never through a zero-drag numerical propagation (`swift_reentry/compare.py`, module docstring).
