"""Reading spacecraft description files (YAML) written by users.

These are the user's own files, not downloaded data, so only the reading part of the io template applies:
``read_spacecraft_description_file`` returns the parsed mapping, and ``leodragkit.aero.spacecraft``
checks and builds it (aero never parses files). The format is described in
``docs/guides/describing_a_spacecraft.md``; an example is ``config/geometry/cubesat_3u_example.yaml``.
"""

from pathlib import Path

import yaml


def read_spacecraft_description_file(path: str | Path) -> dict:
    """Read a YAML spacecraft description and return its top-level mapping, unchecked.

    Raises
    ------
    FileNotFoundError
        If there is no file at ``path``.
    ValueError
        If the file is not valid YAML, or does not hold a mapping of keys to values. The message names
        the file.

    Example::

        description = read_spacecraft_description_file("config/geometry/cubesat_3u_example.yaml")
    """
    # 1. The file must exist; read it as UTF-8 (Windows' default encoding differs).
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"No spacecraft description at {file_path}.")
    text = file_path.read_text(encoding="utf-8")

    # 2. Parse, and insist on a mapping at the top.
    try:
        description = yaml.safe_load(text)
    except yaml.YAMLError as error:
        raise ValueError(f"{file_path} is not valid YAML: {error}") from error
    if not isinstance(description, dict):
        kind = type(description).__name__
        raise ValueError(f"{file_path} must hold a mapping of keys to values (name, mass_kg, …), got {kind}.")
    return description
