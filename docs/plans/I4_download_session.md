# I4: Downloading through a logged-in session

Step plan for task I4 in `docs/tasks.md` (D-51): a small data-input step, in its own commit, before A4c. Proposed as B1a; named I4 to sit with the other data-input steps (I1 SP3, I2 attitude, I3 merging), since its first user is reading Spire files and B1 (Space-Track) comes later.

**Status: approved and implemented 2026-11-04; for review, not committed.**

## Goal

Let `leodragkit/io/http_download.py::download_file` send its request through a logged-in `requests.Session`, so a caller can download files that need authorisation. **Claude writes it.**

First users:

- a local notebook (not in this repository) downloading Spire leoOrb and leoAtt files from NASA CSDA with a bearer token;
- later, B1 (Space-Track), where `.claude/rules/io.md` already says the logged-in `requests.Session` carries the rest of the queries.

## Files

| File | Change |
| --- | --- |
| `leodragkit/io/http_download.py` | `download_file(url, target_path, session=None)`: the request goes through `session.get` when one is given, `requests.get` otherwise; docstring gains a Parameters section |
| `tests/io/test_http_download.py` | two tests added; the four existing ones unchanged |
| `docs/code_tour.md` | the `http_download` entry mentions the optional session |
| `docs/tasks.md` | a row for I4 |
| `docs/plans/I4_download_session.md` | this plan |

## Reused

- **`leodragkit/io/http_download.py::download_file`:** everything stays as it is:
  - the `.part` file beside the target;
  - the `Content-Length` check;
  - `os.replace`;
  - `USER_AGENT`, `TIMEOUT_S` and `stream=True` on the request.
- **`tests/io/test_http_download.py`:** `FakeResponse` and `fake_get`; the new `FakeSession.get` is `fake_get`.

## Modules used instead of writing code

`requests.Session`. Its `get` has the same signature as `requests.get`, so one name, `http_client`, serves both. Headers passed to `get` are merged with the session's own: the User-Agent is ours, and the session's `Authorization` header and cookies are kept.

For redirects, `requests.Session.should_strip_auth` drops `Authorization` when a redirect leaves the original host. Checked here with requests 2.34.2:

- `True` from `https://csdap.earthdata.nasa.gov/a` to `https://bucket.s3.amazonaws.com/b`;
- `False` within one host.

That matters for CSDA, whose files redirect to pre-signed storage URLs that would refuse a second credential. One test pins this behaviour, so an upgrade that changed it would fail loudly.

## Deleted

Nothing.

## Tests

The four existing tests pass unchanged: they fake `requests.get`, still the path with no session.

New:

1. **With a session,** the file comes from `session.get`. `requests.get` is replaced by a function that fails the test if called. The call carries the User-Agent, a positive timeout and `stream=True`; the file lands complete, with no `.part` left.
2. **`requests.Session().should_strip_auth(...)`** is `True` from `https://csdap.earthdata.nasa.gov/a` to `https://bucket.s3.amazonaws.com/b`, and `False` within the same host.

At the start: the four existing tests pass. Done when all six pass, along with the fast suite, `ruff format .` and `ruff check .`.

## Size

About 8 lines of code in `download_file` (signature, one assignment, the call, the docstring's Parameters), about 40 lines of tests, and the three documentation edits.

## Subagents

None.

## Not in this step

- retries;
- a freshness check (Q-05);
- anything specific to CSDA or Spire (the token, file lists, URLs);
- a new dependency.

## Decision entry

None, I agree. It's an optional argument with a default that keeps today's behaviour; no interface file, config key, output or science convention changes. The redirect point is recorded in the docstring and pinned by a test, which is where a reader of `download_file` will look.
