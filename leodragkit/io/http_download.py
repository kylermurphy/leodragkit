"""Downloading one file over HTTP(S), atomically: the shared downloader every ``io`` source module uses.

A download is written to a ``.part`` file beside its target and moved into place only when complete, so a
cut-off transfer never leaves a truncated file under the real name. The bytes are written exactly as
received, so a file's hash matches the provider's. Every request has a timeout and a ``User-Agent``.

The "is the remote copy newer?" check also belongs here; it is added by the first source that needs it
(Q-05). A source whose file never changes says so in its own docstring.
"""

import os
from pathlib import Path

import requests

from leodragkit import __version__

USER_AGENT = f"leodragkit/{__version__} (+https://github.com/kylermurphy/leodragkit)"
TIMEOUT_S = 60.0


def download_file(url: str, target_path: Path) -> Path:
    """Download ``url`` to ``target_path``, never leaving a partial file there, and return the path.

    Raises
    ------
    requests.RequestException
        On a network or HTTP error (the status is checked).
    OSError
        If fewer bytes arrive than the server announced, or on a file error. ``target_path`` is then
        unchanged, and the ``.part`` file removed.
    """
    # 1. Stream into a .part file beside the target.
    target_path.parent.mkdir(parents=True, exist_ok=True)
    part_path = target_path.with_name(f"{target_path.name}.{os.getpid()}.part")
    try:
        with requests.get(
            url, headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S, stream=True
        ) as response:
            response.raise_for_status()
            announced = response.headers.get("Content-Length")
            with part_path.open("wb") as file:
                for chunk in response.iter_content(chunk_size=1 << 16):
                    file.write(chunk)

        # 2. Complete? Compare with the announced size, when the server gave one.
        received = part_path.stat().st_size
        if announced is not None and received != int(announced):
            raise OSError(f"Incomplete download of {url}: {received} of {announced} bytes.")

        # 3. Move into place in one step.
        os.replace(part_path, target_path)
    finally:
        part_path.unlink(missing_ok=True)
    return target_path
