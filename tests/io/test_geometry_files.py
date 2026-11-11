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


# --- load_spacecraft_description (A3d1) --------------------------------------------------------------


def write_description_with_a_mesh(folder, mesh_file="body.obj", unit="mm", extra=""):
    (folder / "spacecraft.yaml").write_text(
        "name: meshed\nmass_kg: 1.0\nmax_edge_length_m: null\n"
        "materials: {aluminium: {wall_temperature_kelvin: 300.0, energy_accommodation: 0.9}}\n"
        "components:\n"
        f"  - {{name: body, shape: mesh, file: {mesh_file}, length_unit: {unit},\n"
        f"     material: aluminium,{extra}\n"
        "     pose: {centre_m: [0, 0, 0], x_axis: [1, 0, 0], z_axis: [0, 0, 1]}}\n",
        encoding="utf-8",
    )
    return folder / "spacecraft.yaml"


def test_mesh_files_are_read_relative_to_the_description_in_metres(tmp_path):
    from leodragkit.io.geometry_files import load_spacecraft_description

    (tmp_path / "body.obj").write_text("v 0 0 0\nv 1000 0 0\nv 0 1000 0\nf 1 2 3\n", encoding="utf-8")
    description = load_spacecraft_description(write_description_with_a_mesh(tmp_path))
    (entry,) = description["components"]
    assert entry["triangle_vertices_m"].tolist() == [[[0, 0, 0], [1, 0, 0], [0, 1, 0]]]
    assert entry["mesh_source"] == "body.obj (mm)"


def test_a_mesh_file_of_another_type_raises_naming_the_component(tmp_path):
    from leodragkit.io.geometry_files import load_spacecraft_description

    (tmp_path / "body.ply").write_text("ply\n", encoding="utf-8")
    with pytest.raises(ValueError, match="components\\[0\\] \\(body\\): mesh files must be"):
        load_spacecraft_description(write_description_with_a_mesh(tmp_path, mesh_file="body.ply"))
