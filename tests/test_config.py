"""Tests for the main config: loading, validation, directory creation and ``create_main_config``.

Run: ``pytest tests/test_config.py``
"""

import dataclasses
from pathlib import Path

import pytest
import yaml

from leodragkit import config
from leodragkit.config import ConfigError, DataDirectories, MainConfig, create_main_config, load_main_config

EXAMPLE_CONFIG = Path(__file__).resolve().parents[1] / "config" / "main_config.example.yaml"


def write_main_config(tmp_path: Path, **changes) -> Path:
    """Write a valid main config under ``tmp_path`` with ``changes`` applied, and return its path.

    A change whose value is ``...`` removes the key; ``data_directories`` changes go in a dict.
    """
    content = {
        "output_directory": str(tmp_path / "outputs"),
        "data_directories": {
            "geometry": str(tmp_path / "data" / "geometry"),
            "tles": str(tmp_path / "data" / "tles"),
            "orekit_data": None,
        },
    }
    for key, value in changes.items():
        if key == "data_directories" and isinstance(value, dict):
            content["data_directories"].update(value)
        elif value is ...:
            del content[key]
        else:
            content[key] = value
    config_path = tmp_path / "main_config.yaml"
    config_path.write_text(yaml.safe_dump(content), encoding="utf-8")
    return config_path


def test_load_main_config_reads_every_directory(tmp_path):
    for name in ("outputs", "data/geometry", "data/tles"):
        (tmp_path / name).mkdir(parents=True)
    main_config = load_main_config(write_main_config(tmp_path))
    assert main_config.output_directory == tmp_path / "outputs"
    assert main_config.data_directories.geometry == tmp_path / "data" / "geometry"
    assert main_config.data_directories.tles == tmp_path / "data" / "tles"
    assert main_config.data_directories.orekit_data is None  # null: the orekit-data pip package
    assert main_config.source_file == (tmp_path / "main_config.yaml").resolve()


def test_missing_directories_are_created_with_a_warning_each(tmp_path):
    with pytest.warns(UserWarning, match="Created the") as warnings_raised:
        main_config = load_main_config(write_main_config(tmp_path))
    assert len(warnings_raised) == 3  # output_directory, geometry, tles; orekit_data is null
    assert "'data_directories.tles'" in str(warnings_raised[-1].message)
    assert main_config.data_directories.tles.is_dir() and main_config.output_directory.is_dir()


def test_an_invalid_config_creates_no_directories(tmp_path):
    config_path = write_main_config(tmp_path, data_directories={"orekit_data": str(tmp_path / "no-orekit-data")})
    with pytest.raises(ConfigError, match="not an existing folder"):
        load_main_config(config_path)
    assert not (tmp_path / "outputs").exists() and not (tmp_path / "data").exists()


def test_tilde_expands_to_the_home_folder(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))  # read by Path.expanduser on Linux and macOS
    monkeypatch.setenv("USERPROFILE", str(tmp_path))  # and on Windows
    config_path = write_main_config(tmp_path, output_directory="~/outputs")
    with pytest.warns(UserWarning):
        main_config = load_main_config(config_path)
    assert main_config.output_directory == tmp_path / "outputs"


def test_no_path_reads_the_default_location(tmp_path, monkeypatch):
    config_path = write_main_config(tmp_path)
    monkeypatch.setattr(config, "default_main_config_path", lambda: config_path)
    with pytest.warns(UserWarning):
        assert load_main_config().source_file == config_path.resolve()


def test_default_location_is_in_the_home_folder():
    assert config.default_main_config_path() == Path.home() / ".leodragkit" / "main_config.yaml"


def test_an_existing_orekit_data_folder_is_used(tmp_path):
    orekit_folder = tmp_path / "orekit-data"
    orekit_folder.mkdir()
    with pytest.warns(UserWarning):
        main_config = load_main_config(write_main_config(tmp_path, data_directories={"orekit_data": str(orekit_folder)}))
    assert main_config.data_directories.orekit_data == orekit_folder


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"output_directory": ...}, "missing \\['output_directory'\\]"),
        ({"output_directroy": "/x"}, "unknown keys \\['output_directroy'\\]"),
        ({"data_directories": {"tle": "/x"}}, "unknown keys \\['tle'\\]"),
        ({"output_directory": "relative/outputs"}, "must be an absolute path"),
        ({"output_directory": None}, "must be a path"),
                ({"data_directories": "/data"}, "must be a mapping"),
    ],
)
def test_invalid_configs_raise_naming_the_problem(tmp_path, changes, message):
    with pytest.raises(ConfigError, match=message):
        load_main_config(write_main_config(tmp_path, **changes))


def test_a_missing_file_says_how_to_create_one(tmp_path):
    with pytest.raises(ConfigError, match="create_main_config"):
        load_main_config(tmp_path / "absent.yaml")


@pytest.mark.parametrize("text", ["", "- just\n- a list\n", "key: [unclosed\n"])
def test_an_empty_or_malformed_file_is_rejected(tmp_path, text):
    config_path = tmp_path / "main_config.yaml"
    config_path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigError, match=str(config_path).replace("\\", "\\\\")):
        load_main_config(config_path)


def test_a_path_that_names_a_file_is_rejected(tmp_path):
    a_file = tmp_path / "not_a_directory.txt"
    a_file.write_text("x", encoding="utf-8")
    with pytest.raises(ConfigError, match="is a file, not a directory"):
        load_main_config(write_main_config(tmp_path, output_directory=str(a_file)))


def test_create_main_config_writes_a_file_that_loads_back(tmp_path):
    config_path = create_main_config(tmp_path / "data", tmp_path / "outputs", path=tmp_path / "main_config.yaml")
    with pytest.warns(UserWarning):
        main_config = load_main_config(config_path)
    assert main_config == MainConfig(
        output_directory=tmp_path / "outputs",
        data_directories=DataDirectories(geometry=tmp_path / "data" / "geometry", tles=tmp_path / "data" / "tles",
                                         orekit_data=None),
        source_file=config_path.resolve(),
    )


def test_create_main_config_never_overwrites(tmp_path):
    config_path = write_main_config(tmp_path)
    with pytest.raises(ConfigError, match="already exists"):
        create_main_config(tmp_path / "data", tmp_path / "outputs", path=config_path)


def test_create_main_config_rejects_a_relative_data_root(tmp_path):
    with pytest.raises(ConfigError, match="'data_root' must be an absolute path"):
        create_main_config("data", tmp_path / "outputs", path=tmp_path / "main_config.yaml")


def test_example_file_has_exactly_the_keys_the_code_reads():
    example = yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))
    assert set(example) == {"output_directory", "data_directories"}
    assert set(example["data_directories"]) == {field.name for field in dataclasses.fields(DataDirectories)}
