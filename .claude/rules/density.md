---
paths:
  - "leodragkit/density/**"
  - "tests/density/**"
---

# density: thermospheric density models

`leodragkit.density` defines what a density model is and holds the models that live in this package: MSIS through `pymsis`, and a toy exponential model for tests. The den_pcaxg models live in the separate model package and satisfy the same Protocol (D-11).

## The interface (interface file: change only with the user's approval)

`leodragkit/density/interface.py` holds the `DensityModel` Protocol and the `AtmosphereState` dataclass (D-10).

- **`density(times_utc, latitude_deg, longitude_deg, altitude_km)`** returns `density_kg_per_m3` as a float64 array of length n.
  - Inputs are sim-time UTC, geodetic latitude and longitude in degrees (longitude in [−180, 180]) and geodetic altitude above WGS84 in km.
  - All inputs are broadcast to one common length n first, so a scalar time with n positions can never silently become an n × n grid (`swift_reentry/density/msis.py::broadcast_points`).
- **`f107_features(f107_table)`** builds the model's F10.7 features from a daily series. Its column names match the model's cached features.
- **The F10.7 window** (lead-in and lead-out days) is declared by each model. Centred averages need future values.
- **`AtmosphereState`** holds temperature in K, the number density of each species in m⁻³, and the model's name. It is returned only by models that provide these. A model that cannot provide them says so; it never fills them in.
- Model types map to builder functions in a plain dictionary. Each builder imports its model's dependency inside the function, so importing `leodragkit.density` stays light.

## Science conventions (change only with the user's approval)

1. **MSIS runs through `pymsis`**, versions 0 (NRLMSISE-00) and 2.1. It uses the storm-time 7-element ap array, `geomagnetic_activity = -1`, passed explicitly because pymsis defaults to daily Ap (swift D-16).
2. **MSIS 2.0 is not run**: pymsis 0.13 returned identical mass density for 2.0 and 2.1 (swift D-17). Recheck if the pinned pymsis version changes.
3. **No extrapolation past the drivers.** A request beyond the last available driver raises an error naming that date (D-11). A member whose drivers run out is truncated by the caller, never extended.
4. **Non-finite drivers raise an error that names the input** (for example `f107a`), never a fill (`swift_reentry/density/msis.py::msis_mass_density`).
5. **Models are vectorised and free of Orekit types** (D-05).
6. **Model-package models are used through their own functions, never re-implemented here.** Any change to a model's features, shapes or training is a new model with a new name (from the swift_reentry OH_sur rules). Their features are causal, using only drivers available at t − τ. Do not wrap them in a way that adds look-ahead.
7. **The exponential model is for tests only.** It must never appear in a workflow's list of density models.

## pymsis pitfalls (checked for pymsis 0.13, the current release on 2026-10-27)

- Switch 9 (index 8) is `geomagnetic_activity` and defaults to 1 (daily Ap only). Build the options once with `create_options(geomagnetic_activity=-1)` and pass them on every call.
- When dates, longitudes, latitudes and altitudes all have the same length, the call is point-wise. Otherwise pymsis broadcasts to a 4-D grid. Always broadcast to a common length first.
- pymsis returns float32; convert to float64.
- Select outputs by the `pymsis.Variable` names (for example `Variable.MASS_DENSITY`), never by raw column index.
- The argument order is `calculate(dates, lons, lats, alts, ...)`: longitude before latitude, the opposite of the Protocol's order.

## Performance

The Orekit adapter calls a model once per force evaluation, one point at a time. Measure before adding any cache, and put the measurement in the report (CLAUDE.md, principle 7).
