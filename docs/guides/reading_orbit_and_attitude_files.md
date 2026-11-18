# Reading orbit and attitude files

How to read a satellite's orbit (SP3 files) and attitude (Spire leoAtt files) into leodragkit, from one file or many, and how to hand them to the drag calculation. The tutorial notebook (`notebooks/aero_tutorial.ipynb`, section 12) runs the same steps on your own files.

## 1. What you need first: the leap-second kernel

Orbit and attitude files are tagged in GPS time, the atmosphere model works in UTC, and planetary ephemerides in SPICE ephemeris time (ET). Every reader therefore returns its times as `Epochs`, which hold each instant on all three scales. Converting between them needs NAIF's leap-second kernel, `naif0012.tls`, kept in the `spice_kernels` directory of your main config (`~/.leodragkit/main_config.yaml`):

```python
from leodragkit.config import load_main_config
from leodragkit.io.spice_kernels import load_leap_second_kernel

main_config = load_main_config()
kernel = load_leap_second_kernel(main_config.data_directories.spice_kernels, allow_download=True)
```

The kernel is downloaded once, if it is missing, and checked against a pinned SHA-256 every time. Load it once and pass it to every reader.

## 2. One file

```python
from leodragkit.io.sp3_files import read_sp3_file
from leodragkit.io.spire_attitude_files import read_spire_attitude_file

states = read_sp3_file("D:/data/spire/spire_nav_L1B_leoOrb_v06_02_2023-12-18T09-51-49_FM134.sp3", kernel)
records = read_spire_attitude_file("D:/data/spire/spire_att_L1A_leoAtt_v06_01_2023-12-18T07-57-00_FM134.log", kernel)
```

| You get | Holds |
| --- | --- |
| `states` (`SatelliteStates`) | `epochs` (UTC, GPS, ET); `positions_m` and `velocities_m_per_s`, (N, 3) in ITRF; `frame` (`"ITRF"`) and `frames_as_written` (e.g. `("IGS08",)`); `satellite_id`; `dropped_records`; `input_records` |
| `records` (`AttitudeRecords`) | `epochs`; `quaternions` exactly as written; their conventions (`scalar_position`, `algebra`, `direction`) and `frame` (`"orbit_level_spire"`); `quality_flags` and `flag_meanings`; `satellite_id`, `file_version`; `dropped_records`; `input_records` |

Files may be plain text or compressed with gzip, bzip2 or xz. A reader drops records it cannot use (a bad value, a position without its velocity, a repeated epoch), keeps their file and line numbers in `dropped_records`, and says so in one warning.

## 3. Several files

Providers deliver data in overlapping pieces: Spire processes in 2-hour windows that overlap by an hour, so a day of one satellite comes as many files, and an epoch can be in two of them. Pass the files as a list; they are read one by one and merged:

```python
from pathlib import Path

from leodragkit.io.merging import read_sp3_files, read_spire_attitude_files

spire = Path("D:/data/spire")
sp3_paths = sorted(spire.glob("spire_nav_L1B_leoOrb_*_FM134.sp3"))
attitude_paths = sorted(spire.glob("spire_att_L1A_leoAtt_*_FM134.log"))

states = read_sp3_files(sp3_paths, kernel)
records = read_spire_attitude_files(attitude_paths, kernel)
```

The list can come from anywhere: `glob` as here, a list you type, or a search by date. Reading is not tied to Spire's file names.

**What the merge keeps where files overlap:**

| Kind | Kept | Why |
| --- | --- | --- |
| orbit | the value from the file in which that epoch lies **furthest from either end** of the file's span | an orbit-determination filter's solution is least reliable near the ends of its arc |
| attitude | an **observed** value over a repeated or default one | a gap in one file may be observed in another |

Ties go to the earlier file in your list. Every file read is kept in `input_records`. One `RecordsMergedWarning` says how many epochs were in more than one file and how much the files disagreed there, for example:

```
2 files merged into 3306 epochs; 500 repeated epochs resolved, keeping the value from the file where each
lies furthest from the ends. Differences in overlaps: position up to 0.5 m (median 0.5); velocity up to …
```

The merge refuses records from different satellites, and attitude files of different versions, whose flags mean different things. SP3 files in different ITRF realisations (IGS08 in one, IGS14 in another) are merged, and every name is kept in `frames_as_written`.

**Comparing files without merging them.** `overlap_differences` gives, for each pair of files that share epochs, the count and the median and maximum differences. For orbits, that is a direct measure of how consistent the provider's solutions are:

```python
from leodragkit.io.merging import overlap_differences
from leodragkit.io.sp3_files import read_sp3_file

pieces = [read_sp3_file(path, kernel) for path in sp3_paths]
for difference in overlap_differences(pieces):
    print(difference.first_source, difference.second_source, difference.shared_epochs,
          difference.quantity, f"median {difference.median:.3f} {difference.unit}",
          f"max {difference.maximum:.3f} {difference.unit}")
```

## 4. Observed attitude only

Attitude records keep every epoch with its quality flag. For Spire's version 1.2 files: 0 observed, 1 repeated (the previous value), 2 default (`[0, 0, 0, 1]`, which is not an attitude). Keep the observed ones for drag work:

```python
from leodragkit.io.records import keep_observed

observed = keep_observed(records)
```

`records` is left as it was, so you can save both. One `UnobservedAttitudeWarning` gives the counts left out, for example "kept 6284 observed attitude epochs of 7561; left out repeated 726, default 551".

## 5. Handing them to the drag calculation

The drag code (`aero`) uses its own types and works on times on one scale; it never converts times or reads files. Build them from what you read, on GPS times:

```python
from leodragkit.aero.frames import OrbitStates, attitude_from_quaternions, attitude_in_itrf, common_epochs
from leodragkit.io.records import source_names

orbit = OrbitStates(
    states.epochs.gps, "GPS", states.positions_m, states.velocities_m_per_s, states.frame, source_names(states)
)
attitude = attitude_from_quaternions(
    observed.epochs.gps, "GPS", observed.quaternions,
    scalar_position=observed.scalar_position, algebra=observed.algebra, direction=observed.direction,
    frame=observed.frame, source=source_names(observed),
)

attitude, orbit = common_epochs(attitude, orbit)   # the epochs both hold exactly; nothing is interpolated
attitude = attitude_in_itrf(attitude, orbit)       # Spire's orbit frame → ITRF, with the orbit at each epoch
```

`common_epochs` keeps only the instants the attitude and the orbit share exactly. Spire's files are both at whole seconds, so they match second for second; data at different instants would need resampling first, which is a separate step and never done silently.

## 6. What the messages mean

| Message | What to do |
| --- | --- |
| `The leap-second kernel … is missing` | load it with `allow_download=True`, or download `naif0012.tls` into your `spice_kernels` directory |
| `data_directories is missing ['spice_kernels']` | your main config is older than the kernel: add a `spice_kernels:` line (see `config/main_config.example.yaml`) |
| `holds 2 satellites; choose one with satellite_id` | an SP3 file with several satellites: pass `satellite_id="…"` to `read_sp3_file` or `read_sp3_files` |
| `coordinate system 'XXX' is not on the list of ITRF realisations` | the file's frame is not one leodragkit reads as ITRF; check the provider's documentation before adding it |
| `Cannot merge AttitudeRecords with different file_version` | read the versions separately; their flags mean different things |
| `share no epoch` (from `common_epochs`) | the orbit and attitude files cover different times: check their spans (`states.epochs.gps[[0, -1]]`) |
