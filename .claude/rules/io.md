---
paths:
  - "leodragkit/io/**"
  - "tests/io/**"
---

# io: reading and downloading orbit data

`leodragkit.io` reads, downloads and caches **orbit data only**: TLEs, SP3 files and attitude files. Space-weather data comes from the model package (D-11, D-13). A state vector typed by the user needs no I/O; it goes straight to `orbit/start_state.py` (D-14).

## The template: every source module has the same four functions

| Function | Does | Rules |
|---|---|---|
| `local_path_for_<source>(data_directory, ...)` | where the file lives | pure; uses the provider's own file names and folders, so files fetched by other tools are reused |
| `download_<source>(..., data_directory)` | fetches the file only when the remote copy is newer; returns its path | goes through `io/http_download.py`; writes atomically |
| `read_<source>_file(path)` | parses one file into a pandas DataFrame | pure: no network, no other files; tested on fixtures in `tests/fixtures/` |
| `load_<source>(data_directory, start_utc, end_utc, allow_download)` | what the rest of the package calls | returns the data and its input records (D-15) |

A module may add private helpers but no other public functions without the user's approval. A reader who knows one source module can then read any other.

## Downloading

- **One shared check.** The "is the remote newer?" check lives once, in `io/http_download.py`. It compares the server's modification time and size with the local file's.
- **Declared behaviour when the server gives neither.** Each source module states in its docstring what happens: always download, or treat the file as fixed once complete. Which servers report what is open (Q-05). Never guess silently.
- **Atomic writes.** Write to a `.part` file, then rename, so a half-written file never appears under its final name. Write the bytes exactly as received, so hashes match the provider's file (`swift_reentry/ephemeris.py::save_atomically`).
- **Snapshots.** A file the provider replaces in place is saved as a dated snapshot, never overwritten (D-13).
- **requests details.** Use `requests` with an explicit timeout and a `User-Agent` on every call. No retry loops unless the plan names them.
- **Missing data.** When a needed file is missing and `allow_download` is false, raise an error naming the file, the time range and how to fix it.
- **Directories.** The data directory comes from the main config. Never hard-code a path; never write outside the data directory.

## Space-Track (TLEs)

- **Credentials are typed** at a prompt with `getpass` (standard library), so the password is not echoed (D-30).
  - They are asked for once, when a download is about to happen, before any long computation starts.
  - They are used to log in and then discarded; the logged-in `requests.Session` carries the rest of the queries.
  - They are never written to the repository, a config file, a log, a manifest or an error message.
  - **Planned, not yet approved for implementation:** environment variables, so production runs (for example on GitHub) can load TLEs without a prompt. Do not implement this until Q-07 is answered and recorded as a decision.
- **"Newer"** means TLEs with epochs after the newest one cached. Query from there, append, and remove duplicates by epoch and element-set number, reporting how many were removed. Port from `swift_reentry/tle_history.py`: `fetch_space_track`, `save_new_tles`, `history_query_start`, `write_history_marker`.
- **Usage policy.** Keep queries few and small, respecting Space-Track's usage policy. Check its current limits before writing the downloader; they are not recorded here.

## Parsing

- **Standard columns.** Readers return standard column names with units (`epoch_utc`, `position_m`, `velocity_m_per_s`) and times in UTC.
- **Malformed input raises** with the file name and line number. Never skip lines silently.
- **SP3 headers are read, not assumed.** Take the time system, frame and sampling interval from the header; convert the time system explicitly (GPS to UTC) and record the frame. Positions are in km and velocities in dm/s in the file; convert them to m and m/s.
- **Overlaps and duplicates are reported, never dropped silently.** This applies to overlapping SP3 arcs, duplicate epochs, and position records without a matching velocity record. The caller decides what to do with them.
- **Attitude readers** return the scalar position and frame pair with the quaternions (D-27). A reader is written only once a real file exists to test against.

## Tests

- Parsers are tested on small fixture files, with no network.
- Downloaders are marked `network`. Test the freshness check with a fake server response, not the live site.
