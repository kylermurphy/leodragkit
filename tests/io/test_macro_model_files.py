"""Tests for reading macro-model tables (task A3d2): columns, rows, and the line of every problem.

Run: ``pytest tests/io/test_macro_model_files.py``
"""

import numpy as np
import pytest

from leodragkit.io.geometry_files import read_macro_model_file

HEADER = "component,material,normal_x,normal_y,normal_z,area_m2"
CENTROIDS = ",centroid_x_m,centroid_y_m,centroid_z_m"


def write_table(folder, text):
    path = folder / "panels.csv"
    path.write_text(text, encoding="utf-8")
    return path


def test_a_table_with_centroids_is_read_row_by_row(tmp_path):
    path = write_table(
        tmp_path,
        HEADER + CENTROIDS + "\nbus,aluminium,1,0,0,0.034,0.05,0,0\npanel,solar_cell,0,0,1,0.03,0,0.2,0.1\n",
    )
    table = read_macro_model_file(path)
    assert table.component_names == ("bus", "panel")
    assert table.material_names == ("aluminium", "solar_cell")
    np.testing.assert_array_equal(table.outward_normals, [[1, 0, 0], [0, 0, 1]])
    np.testing.assert_array_equal(table.areas_m2, [0.034, 0.03])
    np.testing.assert_array_equal(table.centroids_m, [[0.05, 0, 0], [0, 0.2, 0.1]])
    assert table.source == "panels.csv"


def test_a_table_without_centroids_has_none(tmp_path):
    table = read_macro_model_file(write_table(tmp_path, HEADER + "\nbus,aluminium,1,0,0,0.034\n"))
    assert table.centroids_m is None and table.areas_m2.shape == (1,)


def test_spaces_around_values_are_allowed(tmp_path):
    table = read_macro_model_file(write_table(tmp_path, HEADER + "\n bus , aluminium , 1, 0, 0, 0.034\n"))
    assert table.component_names == ("bus",) and table.material_names == ("aluminium",)


@pytest.mark.parametrize(
    ("text", "message"),
    [
        ("component,material,normal_x,normal_y,area_m2\nbus,al,1,0,0.1\n", "missing \\['normal_z'\\]"),
        (HEADER + ",colour\nbus,al,1,0,0,0.1,red\n", "unknown \\['colour'\\]"),
        (HEADER + ",centroid_x_m\nbus,al,1,0,0,0.1,0\n", "all three centroid columns or none"),
        (HEADER + "\n", "no panels"),
        (HEADER + "\nbus,al,1,0,0,0.1\nbus,al,one,0,0,0.1\n", "line 3, column normal_x"),
        (HEADER + "\nbus,al,1,0,0,\n", "line 2, column area_m2"),
        (HEADER + "\n,al,1,0,0,0.1\n", "line 2, column component"),
    ],
    ids=[
        "missing column",
        "unknown column",
        "one centroid column",
        "no rows",
        "not a number",
        "empty",
        "no name",
    ],
)
def test_a_bad_table_raises_naming_the_problem(tmp_path, text, message):
    with pytest.raises(ValueError, match=message):
        read_macro_model_file(write_table(tmp_path, text))


def test_a_missing_table_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_macro_model_file(tmp_path / "absent.csv")
