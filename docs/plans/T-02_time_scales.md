# T-02: Time scales

Step plan for task T-02 in `docs/tasks.md`; the first step of the A4 group (`docs/plans/A4_attitude_and_flow_overview.md`). Three components, one patch each, reviewed and pushed before the next (D-82).

## Goal

Hold every time as the same instants on three scales (UTC, GPS and SPICE ET), so that Spire's GPS-tagged files, the atmosphere model's UTC and SPICE's ET can be used together without anyone converting by hand. Conversions go through spiceypy with NAIF's leap-second kernel.

## Components

| # | Builds | Who | Status |
| --- | --- | --- | --- |
| 1 | the `spice_kernels` data directory in the main config; `io/http_download.py` (the shared downloader); `io/records.py` (`InputRecord`, D-15); `io/spice_kernels.py` (the leap-second kernel, four functions); spiceypy as a dependency | Claude | this patch |
| 2 | `Epochs` in `leodragkit/time_scales.py`: built from UTC, GPS or ET; conversions through spiceypy, loading the kernel once | Claude, with the user reviewing | next |
| 3 | tests against fixed values: GPS − UTC = 18 s after 2017; UTC 2000-01-01 12:00:00 is ET 64.184 s; agreement with the kernel's leap-second table | Claude | after 2 |

## Component 1 in detail

**The main config.** `data_directories.spice_kernels` is new and required. It is created on first load like the other data directories. A config written before it existed raises, saying a key added since may be missing and pointing at the example file. `create_main_config` writes it as `<data_root>/spice_kernels`.

**The leap-second kernel, `naif0012.tls`,** from `https://naif.jpl.nasa.gov/pub/naif/generic_kernels/lsk/`:

| Function | Does |
| --- | --- |
| `local_path_for_leap_second_kernel(directory)` | `<spice_kernels>/naif0012.tls`, NAIF's own name, so a copy fetched by another tool (contigo_edr) is reused |
| `download_leap_second_kernel(directory)` | downloads atomically, then checks the SHA-256; a different file is removed and raises |
| `read_leap_second_kernel_file(path)` | checks the first line is `KPL/LSK` (an HTML error page would not be); returns the `DELTET/DELTA_AT` table as (date, TAI − UTC) pairs and the input record |
| `load_leap_second_kernel(directory, allow_download)` | uses the local file, downloading only if missing and allowed; rejects a file whose SHA-256 is not the pinned one |

**Freshness:** the file is fixed once complete and never re-downloaded. NAIF publishes a new leap second as a new file (`naif0013.tls`), so taking one up is a deliberate change of `LEAP_SECOND_KERNEL_NAME` and the pinned hash, recorded as a decision. This differs from contigo_edr, which re-downloads when NAIF's copy is newer; a fixed name plus a pinned hash means a run is always reproducible.

**The pinned file:** 5257 bytes, SHA-256 `678e32bd…a039b`, 28 leap seconds from 10 s (1972-01-01) to 37 s (2017-01-01), as served on 2026-11-02.

## Tests (component 1)

- **Config:** `spice_kernels` read, created with a warning, written by `create_main_config`; an older config without it raises with the hint.
- **Downloader** (no network; `requests.get` is faked): a complete download lands under its name with no `.part` left; a short one raises and leaves nothing; an HTTP error keeps an existing file; a response without a size is accepted.
- **Kernel:**
  - offline, with a small hand-written kernel: name and location; the table and input record read; an HTML page and a file without the table rejected; a missing file without download says how to fix it; a present file is used without downloading; a different hash is rejected; a wrong download is removed;
  - marked `network`: the real file downloads with the pinned hash and 28 leap seconds.

## Done when

The fast suite passes, the network test passes when run, ruff passes, and the user's own `~/.leodragkit/main_config.yaml` has a `spice_kernels` entry.
