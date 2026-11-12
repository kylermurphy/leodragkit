"""Tests for whole spacecraft from descriptions (task A3c): building, checking, materials and warnings.

Descriptions are plain dicts here, as ``leodragkit.io.geometry_files`` would return them; the example file in
``config/geometry/`` is read once to check that it builds.

Run: ``pytest tests/aero/test_spacecraft_description.py``
"""

import copy
from pathlib import Path

import numpy as np
import pytest

from leodragkit.aero.geometry_checks import summarise_geometry
from leodragkit.aero.spacecraft import Spacecraft, SpacecraftDescriptionWarning, build_spacecraft
from leodragkit.io.geometry_files import read_spacecraft_description_file

EXAMPLE_FILE = Path(__file__).resolve().parents[2] / "config" / "geometry" / "cubesat_3u_example.yaml"

DESCRIPTION = {
    "name": "test spacecraft",
    "mass_kg": 4.0,
    "max_edge_length_m": None,
    "materials": {
        "aluminium": {"wall_temperature_kelvin": 300.0, "energy_accommodation": 0.9},
        "solar_cell": {"wall_temperature_kelvin": 320.0, "energy_accommodation": 0.85},
    },
    "components": [
        {
            "name": "bus",
            "shape": "box",
            "size_m": [0.1, 0.1, 0.34],
            "material": "aluminium",
            "pose": {"centre_m": [0, 0, 0], "x_axis": [1, 0, 0], "z_axis": [0, 0, 1]},
        },
        {
            "name": "panel",
            "shape": "plate",
            "size_m": [0.3, 0.1],
            "two_sided": True,
            "material": "solar_cell",
            "pose": {"centre_m": [0, 0.2, 0.12], "rotation_axis": [0, 0, 1], "rotation_angle_deg": 90},
        },
        {
            "name": "antenna",
            "shape": "cylinder",
            "radius_m": 0.005,
            "height_m": 0.2,
            "capped": False,
            "material": "aluminium",
            "pose": {"centre_m": [0, 0, -0.27], "x_axis": [1, 0, 0], "z_axis": [0, 0, 1]},
        },
    ],
}


def described(**changes):
    """A deep copy of DESCRIPTION with changes: top-level keys, or 'components[i].key' for one component."""
    description = copy.deepcopy(DESCRIPTION)
    for key, value in changes.items():
        if key.startswith("components["):
            index, field = int(key[11]), key.split(".", 1)[1]
            if value is ...:
                del description["components"][index][field]
            else:
                description["components"][index][field] = value
        elif value is ...:
            del description[key]
        else:
            description[key] = value
    return description


# --- building -----------------------------------------------------------------------------------


def test_a_description_builds_a_spacecraft_with_its_parts_materials_and_mass():
    spacecraft = build_spacecraft(DESCRIPTION, source="test")
    assert isinstance(spacecraft, Spacecraft)
    assert spacecraft.name == "test spacecraft" and spacecraft.mass_kg == 4.0
    assert spacecraft.panel_set.component_names == ("bus", "panel", "antenna")
    assert spacecraft.panel_set.source == "test"


def test_the_materials_line_up_with_the_panel_sets_material_names():
    spacecraft = build_spacecraft(DESCRIPTION, source="test")
    assert tuple(m.name for m in spacecraft.materials) == spacecraft.panel_set.material_names
    solar = spacecraft.materials[spacecraft.panel_set.material_names.index("solar_cell")]
    assert solar.wall_temperature_kelvin == 320.0 and solar.energy_accommodation == 0.85


def test_the_rotation_form_of_a_pose_is_used():
    # The panel is rotated 90° about z: its own x (the 0.3 m side) now runs along body y.
    spacecraft = build_spacecraft(DESCRIPTION, source="test")
    panel = spacecraft.panel_set.triangle_vertices_m[spacecraft.panel_set.component_ids == 1].reshape(-1, 3)
    np.testing.assert_allclose(np.ptp(panel, axis=0), [0.1, 0.3, 0.0], atol=1e-12)


def test_a_pose_can_place_by_axes_and_then_turn_about_an_own_axis():
    # The panel in the y–z plane facing +x, then turned 20° about its own x (its long side, along body y).
    pose = {
        "centre_m": [0, 0.2, 0.12],
        "x_axis": [0, 1, 0],
        "z_axis": [1, 0, 0],
        "rotation_axis": [1, 0, 0],
        "rotation_angle_deg": 20,
    }
    spacecraft = build_spacecraft(described(**{"components[1].pose": pose}), source="test")
    front = spacecraft.panel_set.outward_normals[spacecraft.panel_set.component_ids == 1][
        :2
    ]  # two-sided: front first
    angle = np.radians(20)
    np.testing.assert_allclose(front, [[np.cos(angle), 0, -np.sin(angle)]] * 2, atol=1e-12)


def test_a_component_can_override_the_resolution():
    coarse = build_spacecraft(DESCRIPTION, source="test")
    finer = build_spacecraft(described(**{"components[0].max_edge_length_m": 0.05}), source="test")
    bus_coarse = np.sum(coarse.panel_set.component_ids == 0)
    bus_finer = np.sum(finer.panel_set.component_ids == 0)
    assert bus_coarse == 12 and bus_finer > bus_coarse


def test_the_example_file_builds_and_passes_every_check():
    spacecraft = build_spacecraft(read_spacecraft_description_file(EXAMPLE_FILE), source=EXAMPLE_FILE.name)
    assert spacecraft.panel_set.component_names == ("bus", "panel_plus_y", "panel_minus_y", "antenna")
    assert all(row["status"].startswith("ok") for row in summarise_geometry(spacecraft.panel_set).rows())


# --- mistakes are named ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"mass": 4.0}, "unknown keys \\['mass'\\]"),
        ({"mass_kg": ...}, "missing \\['mass_kg'\\]"),
        ({"mass_kg": -1.0}, "mass_kg must be > 0"),
        ({"components": []}, "components must be a non-empty list"),
        ({"components[0].shape": "sphere"}, "components\\[0\\] \\(bus\\): shape must be one of"),
        (
            {"components[0].sizes_m": [1, 1, 1]},
            "components\\[0\\] \\(bus\\) has unknown keys \\['sizes_m'\\]",
        ),
        ({"components[0].size_m": [0.1, 0.1]}, "list of 3 sizes for a box"),
        ({"components[1].size_m": [0.3, -0.1]}, "components\\[1\\] \\(panel\\).size_m\\[1\\] must be > 0"),
        ({"components[2].radius_m": "thin"}, "radius_m must be a number"),
        ({"components[1].material": "gold"}, "material 'gold' is not defined"),
        ({"components[1].two_sided": "yes"}, "two_sided must be true or false"),
        ({"components[0].pose": {"centre_m": [0, 0, 0]}}, "pose must have centre_m with"),
        (
            {"components[0].pose": {"centre_m": [0, 0, 0], "x_axis": [1, 0, 0], "rotation_axis": [0, 0, 1]}},
            "pose must have centre_m with",
        ),
        (
            {"components[0].pose": {"centre_m": [0, 0, 0], "x_axis": [1, 0, 0], "z_axis": [0.5, 0, 0.866]}},
            "components\\[0\\] \\(bus\\): x_axis and z_axis must be perpendicular",
        ),
    ],
)
def test_a_mistake_raises_naming_where_it_is(changes, message):
    with pytest.raises(ValueError, match=message):
        build_spacecraft(described(**changes), source="test")


def test_a_bad_material_raises_naming_it():
    materials = copy.deepcopy(DESCRIPTION["materials"])
    materials["aluminium"]["energy_accommodation"] = 1.2
    with pytest.raises(ValueError, match="'aluminium': energy_accommodation must be in \\[0, 1\\]"):
        build_spacecraft(described(materials=materials), source="test")


def test_a_repeated_component_name_raises():
    components = copy.deepcopy(DESCRIPTION["components"])
    components[2]["name"] = "bus"
    with pytest.raises(ValueError, match="'bus'"):
        build_spacecraft(described(components=components), source="test")


# --- unused materials -----------------------------------------------------------------------------


def test_an_unused_material_warns_naming_it_and_is_left_out():
    materials = copy.deepcopy(DESCRIPTION["materials"])
    materials["gold_foil"] = {"wall_temperature_kelvin": 300.0, "energy_accommodation": 0.8}
    with pytest.warns(SpacecraftDescriptionWarning, match="gold_foil"):
        spacecraft = build_spacecraft(described(materials=materials), source="test")
    assert "gold_foil" not in spacecraft.panel_set.material_names


# --- meshes (A3d1) ----------------------------------------------------------------------------------


def test_a_mesh_component_uses_triangles_loaded_from_its_file():
    from leodragkit.aero.geometry_builder import build_box_triangles

    mesh_entry = {
        "name": "body",
        "shape": "mesh",
        "file": "body.stl",
        "length_unit": "mm",
        "material": "aluminium",
        "pose": {"centre_m": [0, 0, -0.5], "x_axis": [1, 0, 0], "z_axis": [0, 0, 1]},
        "triangle_vertices_m": build_box_triangles(0.2, 0.2, 0.2),  # as load_spacecraft_description adds
        "mesh_source": "body.stl (mm)",
    }
    only_aluminium = {"aluminium": DESCRIPTION["materials"]["aluminium"]}
    components = [DESCRIPTION["components"][0], mesh_entry]
    spacecraft = build_spacecraft(described(components=components, materials=only_aluminium), source="t")
    body = spacecraft.panel_set.triangle_vertices_m[spacecraft.panel_set.component_ids == 1].reshape(-1, 3)
    np.testing.assert_allclose(body.mean(axis=0), [0, 0, -0.5], atol=1e-12)  # placed at its pose


def test_a_mesh_that_was_not_loaded_raises_saying_how_to_load_it():
    mesh_entry = {
        "name": "body",
        "shape": "mesh",
        "file": "body.stl",
        "length_unit": "mm",
        "material": "aluminium",
        "pose": {"centre_m": [0, 0, 0], "x_axis": [1, 0, 0], "z_axis": [0, 0, 1]},
    }
    with pytest.raises(ValueError, match="load_spacecraft_description"):
        build_spacecraft(described(components=[mesh_entry]), source="t")


def test_a_spacecraft_can_be_built_straight_from_triangles():
    from leodragkit.aero.geometry_builder import build_box_triangles
    from leodragkit.aero.materials import SurfaceMaterial
    from leodragkit.aero.spacecraft import build_spacecraft_from_triangles

    aluminium = SurfaceMaterial("aluminium", 300.0, 0.9)
    spacecraft = build_spacecraft_from_triangles(
        build_box_triangles(0.1, 0.2, 0.3), name="box", material=aluminium, mass_kg=2.0, source="box (test)"
    )
    assert spacecraft.panel_set.component_names == ("box",) and spacecraft.materials == (aluminium,)


def test_an_inside_out_mesh_cannot_be_built_straight_from_triangles():
    from leodragkit.aero.geometry_builder import build_box_triangles
    from leodragkit.aero.materials import SurfaceMaterial
    from leodragkit.aero.spacecraft import build_spacecraft_from_triangles

    with pytest.raises(ValueError, match="inward"):
        build_spacecraft_from_triangles(
            build_box_triangles(0.1, 0.2, 0.3)[:, ::-1, :],
            name="box",
            material=SurfaceMaterial("aluminium", 300.0, 0.9),
            mass_kg=2.0,
            source="inside out",
        )


# --- macro models (A3d2) ------------------------------------------------------------------------------

MACRO_EXAMPLE = Path(__file__).resolve().parents[2] / "config" / "geometry" / "cubesat_3u_macro_model.yaml"


def test_the_macro_model_example_builds_without_triangles():
    from leodragkit.io.geometry_files import load_spacecraft_description

    spacecraft = build_spacecraft(load_spacecraft_description(MACRO_EXAMPLE), source=MACRO_EXAMPLE.name)
    panels = spacecraft.panel_set
    assert panels.panel_count == 10 and not panels.has_triangles and panels.has_positions
    assert panels.component_names == ("bus", "panel_plus_y", "panel_minus_y")
    assert panels.areas_m2.sum() == pytest.approx(4 * 0.034 + 2 * 0.01 + 4 * 0.03)
    statuses = {row["status"] for row in summarise_geometry(panels).rows()}
    assert statuses == {"not checkable (no triangles)"}


def test_the_direct_path_gives_the_same_spacecraft_as_the_description():
    from leodragkit.aero.spacecraft import build_spacecraft_from_macro_model
    from leodragkit.io.geometry_files import load_spacecraft_description, read_macro_model_file

    from_description = build_spacecraft(load_spacecraft_description(MACRO_EXAMPLE), source="example")
    table = read_macro_model_file(MACRO_EXAMPLE.with_suffix(".csv"))
    direct = build_spacecraft_from_macro_model(
        table,
        name=from_description.name,
        materials=dict(zip(from_description.panel_set.material_names, from_description.materials)),
        mass_kg=4.0,
        source="example",
    )
    for field in ("outward_normals", "areas_m2", "centroids_m", "component_ids", "material_ids"):
        np.testing.assert_array_equal(
            getattr(direct.panel_set, field), getattr(from_description.panel_set, field)
        )


def test_rounded_macro_model_normals_are_normalised_and_bad_ones_raise():
    from types import SimpleNamespace

    from leodragkit.aero.materials import SurfaceMaterial
    from leodragkit.aero.spacecraft import build_spacecraft_from_macro_model

    def table(normal):
        return SimpleNamespace(
            component_names=("panel",),
            material_names=("al",),
            outward_normals=np.array([normal]),
            areas_m2=np.array([0.1]),
            centroids_m=None,
        )

    materials = {"al": SurfaceMaterial("al", 300.0, 0.9)}
    rounded = build_spacecraft_from_macro_model(
        table([0.7071, 0.7071, 0]), name="t", materials=materials, mass_kg=1.0, source="t"
    )
    assert np.linalg.norm(rounded.panel_set.outward_normals[0]) == pytest.approx(1.0, abs=1e-15)
    with pytest.raises(ValueError, match="outward_normals"):
        build_spacecraft_from_macro_model(
            table([0.9, 0, 0]), name="t", materials=materials, mass_kg=1.0, source="t"
        )


def test_a_macro_model_with_an_undefined_material_raises():
    from types import SimpleNamespace

    from leodragkit.aero.spacecraft import build_spacecraft_from_macro_model

    table = SimpleNamespace(
        component_names=("panel",),
        material_names=("gold",),
        outward_normals=np.array([[1.0, 0, 0]]),
        areas_m2=np.array([0.1]),
        centroids_m=None,
    )
    with pytest.raises(ValueError, match="'gold'"):
        build_spacecraft_from_macro_model(table, name="t", materials={}, mass_kg=1.0, source="t")


def test_a_description_with_both_components_and_a_macro_model_raises():
    with pytest.raises(ValueError, match="either components or a macro_model"):
        build_spacecraft(described(macro_model={"file": "panels.csv"}), source="t")


def test_a_macro_model_that_was_not_read_says_how_to_load_it():
    description = {
        "name": "t",
        "mass_kg": 1.0,
        "materials": DESCRIPTION["materials"],
        "macro_model": {"file": "panels.csv"},
    }
    with pytest.raises(ValueError, match="load_spacecraft_description"):
        build_spacecraft(description, source="t")


def test_the_grace_macro_model_builds_from_the_published_table():
    # Bettadpur (2012), GRACE 327-720, section I.5.3.5: eight flat surfaces (the boom is left out).
    from leodragkit.io.geometry_files import load_spacecraft_description

    path = MACRO_EXAMPLE.with_name("grace_macro_model.yaml")
    grace = build_spacecraft(load_spacecraft_description(path), source=path.name)
    panels = grace.panel_set
    assert panels.panel_count == 8 and not panels.has_positions and grace.mass_kg == 487.2
    assert panels.areas_m2.sum() == pytest.approx(16.9163284, abs=1e-7)
    assert grace.panel_set.material_names == ("siox_kapton", "si_glass_solar_array", "teflon_fep")
    np.testing.assert_allclose(
        np.linalg.norm(panels.outward_normals, axis=1), 1.0, atol=1e-15
    )  # 0.766044, 0.642787
