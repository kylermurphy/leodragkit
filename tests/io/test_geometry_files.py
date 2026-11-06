"""Tests for reading spacecraft description files (task A3c).

Run: ``pytest tests/io/test_geometry_files.py``
"""

import pytest

from leodragkit.io.geometry_files import read_spacecraft_description_file


def test_a_description_file_is_read_as_a_mapping(tmp_path):
    path = tmp_path / "spacecraft.yaml"
    path.write_text("name: test\nmass_kg: 4.0\n", encoding="utf-8")
    assert read_spacecraft_description_file(path) == {"name": "test", "mass_kg": 4.0}


def test_a_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError, match="absent.yaml"):
        read_spacecraft_description_file(tmp_path / "absent.yaml")


@pytest.mark.parametrize(
    ("text", "message"), [("name: [unclosed\n", "not valid YAML"), ("- a\n- list\n", "mapping")]
)
def test_invalid_yaml_or_a_non_mapping_raises_naming_the_file(tmp_path, text, message):
    path = tmp_path / "broken.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        read_spacecraft_description_file(path)
