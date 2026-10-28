"""Main config: where leodragkit reads data and writes outputs.

The main config is one small YAML file that gives the output directory and one directory per
data source, so existing data can be reused wherever it lives. Its default location is
``~/.leodragkit/main_config.yaml``, for clones and pip installs alike; every loader also
accepts an explicit path. ``config/main_config.example.yaml`` shows the format.

Read first: ``load_main_config``, then ``create_main_config``.
"""

import dataclasses
import warnings
from dataclasses import dataclass
from pathlib import Path

import yaml


class ConfigError(ValueError):
    """A config file is missing or malformed, or one of its paths is invalid.

    The message names the file, the key and how to fix it.
    """


@dataclass(frozen=True)
class DataDirectories:
    """One directory per data source that leodragkit reads itself.

    Each source gets its key in the task that first reads it.
    """

    geometry: Path  # spacecraft panel tables, read by aero
    tles: Path  # TLE history downloaded from Space-Track
    orekit_data: Path | None  # an Orekit data folder; None: the orekit-data pip package


@dataclass(frozen=True)
class MainConfig:
    """The output directory and the data directories, with the file they came from."""

    output_directory: Path
    data_directories: DataDirectories
    source_file: Path  # provenance: the YAML this config was loaded from


def default_main_config_path() -> Path:
    """Return the default location of the main config, ``~/.leodragkit/main_config.yaml``."""
    return Path.home() / ".leodragkit" / "main_config.yaml"


def load_main_config(path: str | Path | None = None) -> MainConfig:
    """Read and validate the main config, creating any missing data or output directory.

    Parameters
    ----------
    path
        The YAML file to read; ``None`` reads ``default_main_config_path()``.

    Returns
    -------
    MainConfig
        Absolute paths, with ``~`` expanded.

    Raises
    ------
    ConfigError
        If the file is missing or malformed, a key is missing or unknown, a path is relative or
        names a file, or ``orekit_data`` names a folder that does not exist.

    Example::

        main_config = load_main_config()
        main_config.data_directories.tles
    """
    # 1. Read the file: the default location unless a path is given.
    config_path = default_main_config_path() if path is None else Path(path).expanduser()
    raw = _read_yaml_mapping(config_path)

    # 2. Check the keys at both levels, so a typo is reported by name instead of ignored.
    _check_keys(raw, {"output_directory", "data_directories"}, config_path, section="the top level")
    raw_directories = raw["data_directories"]
    if not isinstance(raw_directories, dict):
        raise ConfigError(f"{config_path}: 'data_directories' must be a mapping of source name to directory.")
    # The allowed source names are the dataclass fields: adding a field adds the key.
    source_names = {field.name for field in dataclasses.fields(DataDirectories)}
    _check_keys(raw_directories, source_names, config_path, section="'data_directories'")

    # 3. Check every path before creating anything, so an invalid config leaves no folders behind.
    output_directory = _require_absolute(raw["output_directory"], "output_directory", config_path)
    geometry = _require_absolute(raw_directories["geometry"], "data_directories.geometry", config_path)
    tles = _require_absolute(raw_directories["tles"], "data_directories.tles", config_path)
    orekit_data = None  # null in the file: Orekit data comes from the orekit-data pip package
    if raw_directories["orekit_data"] is not None:
        orekit_data = _require_absolute(raw_directories["orekit_data"], "data_directories.orekit_data", config_path)
        # An Orekit data folder must already hold its files: an empty new folder would only fail later.
        if not orekit_data.is_dir():
            raise ConfigError(f"{config_path}: 'data_directories.orekit_data' is not an existing folder: "
                              f"{orekit_data}. Fix the path, or set it to null to use the orekit-data pip package.")
    # The directories leodragkit may create; none of them may name an existing file.
    creatable = {"output_directory": output_directory, "data_directories.geometry": geometry,
                 "data_directories.tles": tles}
    for key, path in creatable.items():
        if path.exists() and not path.is_dir():
            raise ConfigError(f"{config_path}: '{key}' is a file, not a directory: {path}")

    # 4. Every path is valid: create the missing directories, with one warning each so a
    #    mistyped path is noticed the first time it is used.
    for key, path in creatable.items():
        if not path.exists():
            path.mkdir(parents=True)
            warnings.warn(f"Created the '{key}' directory {path} (from {config_path}).", stacklevel=2)

    # 5. Return a frozen config, recording which file it came from (provenance).
    return MainConfig(
        output_directory=output_directory,
        data_directories=DataDirectories(geometry=geometry, tles=tles, orekit_data=orekit_data),
        source_file=config_path.resolve(),
    )


def create_main_config(data_root: str | Path, output_directory: str | Path, path: str | Path | None = None) -> Path:
    """Write a new main config with each data directory set to ``<data_root>/<source>``.

    Edit the file afterwards to point any source at data you already have. ``orekit_data`` is
    written as ``null`` (the orekit-data pip package). Directories are created on first load.

    Returns
    -------
    Path
        The file written (``default_main_config_path()`` when ``path`` is None).

    Raises
    ------
    ConfigError
        If the file already exists (it is never overwritten) or a path is relative.

    Example::

        create_main_config(data_root="D:/data/leodragkit", output_directory="D:/outputs/leodragkit")
    """
    # 1. Never overwrite: an existing main config may hold paths the user has edited.
    config_path = default_main_config_path() if path is None else Path(path).expanduser()
    if config_path.exists():
        raise ConfigError(f"{config_path} already exists. Edit it, or delete it first to create a new one.")

    # 2. Build the content: one folder per source under data_root. Forward slashes read the same
    #    on every operating system.
    data_root_path = _require_absolute(data_root, "data_root", config_path)
    content = {
        "output_directory": _require_absolute(output_directory, "output_directory", config_path).as_posix(),
        "data_directories": {
            "geometry": (data_root_path / "geometry").as_posix(),
            "tles": (data_root_path / "tles").as_posix(),
            "orekit_data": None,
        },
    }
    # 3. Write it, creating the parent folder (~/.leodragkit/) if needed.
    header = "# leodragkit main config. Edit any path to point at data you already have.\n"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(header + yaml.safe_dump(content, sort_keys=False), encoding="utf-8")
    return config_path


def _read_yaml_mapping(config_path: Path) -> dict:
    """Return the YAML mapping in ``config_path``; raise ConfigError if missing, malformed or not a mapping."""
    if not config_path.is_file():
        raise ConfigError(
            f"No config file at {config_path}. Create one with "
            "leodragkit.config.create_main_config(data_root=..., output_directory=...), "
            "or copy config/main_config.example.yaml there and edit it."
        )
    try:
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ConfigError(f"{config_path} is not valid YAML: {error}") from error
    if not isinstance(raw, dict):
        raise ConfigError(f"{config_path} is empty or not a YAML mapping of keys to values.")
    return raw


def _check_keys(raw: dict, expected_keys: set[str], config_path: Path, section: str) -> None:
    """Raise ConfigError naming any missing or unknown key in one section of a config file."""
    missing_keys = expected_keys - raw.keys()
    unknown_keys = raw.keys() - expected_keys
    if missing_keys:
        raise ConfigError(f"{config_path}: {section} is missing {sorted(missing_keys)}.")
    if unknown_keys:
        raise ConfigError(
            f"{config_path}: {section} has unknown keys {sorted(unknown_keys)}; allowed: {sorted(expected_keys)}."
        )


def _require_absolute(value: object, key: str, config_path: Path) -> Path:
    """Return ``value`` as an absolute path with ``~`` expanded; raise ConfigError if it is not one."""
    if not isinstance(value, (str, Path)):
        raise ConfigError(f"{config_path}: '{key}' must be a path, got {value!r}.")
    path = Path(value).expanduser()
    if not path.is_absolute():
        raise ConfigError(f"{config_path}: '{key}' must be an absolute path (or start with ~), got '{value}'.")
    return path
