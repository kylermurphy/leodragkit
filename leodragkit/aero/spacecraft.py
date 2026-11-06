"""A whole spacecraft from a description: its panels, materials and mass, checked.

A description is a mapping, usually read from a YAML file by ``leodragkit.io.geometry_files`` (aero itself
never parses files). ``build_spacecraft`` checks every key and value, building each component from a
primitive placed at its pose, joining them (which runs the orientation checks), and attaching the materials.
Every error names its place in the description, such as ``components[1] (panel_plus_y)``.

The format, with worked examples of placing parts, is in ``docs/guides/describing_a_spacecraft.md``; an
example file is ``config/geometry/cubesat_3u_example.yaml``.

Read first: ``Spacecraft``, then ``build_spacecraft``.
"""

from collections.abc import Mapping
from dataclasses import dataclass

import numpy as np

from leodragkit.aero.geometry import PanelSet
from leodragkit.aero.geometry_builder import (
    Component,
    Pose,
    build_box_triangles,
    build_cylinder_triangles,
    build_plate_triangles,
    join_components,
    make_pose,
    make_pose_from_rotation,
    place_triangles,
    turn_pose_about_own_axis,
)
from leodragkit.aero.materials import SurfaceMaterial
from leodragkit.aero.repeated_warnings import warn_every_time

TOP_LEVEL_KEYS = {"name", "mass_kg", "max_edge_length_m", "materials", "components"}
MATERIAL_KEYS = {"wall_temperature_kelvin", "energy_accommodation"}
COMMON_COMPONENT_KEYS = {"name", "shape", "material", "pose"}
OPTIONAL_COMPONENT_KEYS = {"max_edge_length_m"}
SHAPE_KEYS = {  # required keys, optional keys
    "box": ({"size_m"}, set()),
    "plate": ({"size_m"}, {"two_sided"}),
    "cylinder": ({"radius_m", "height_m"}, {"capped"}),
}
SIZE_LENGTHS = {"box": 3, "plate": 2}
AXES_POSE_KEYS = {"centre_m", "x_axis", "z_axis"}
ROTATION_POSE_KEYS = {"centre_m", "rotation_axis", "rotation_angle_deg"}
COMBINED_POSE_KEYS = AXES_POSE_KEYS | ROTATION_POSE_KEYS  # orient by axes, then turn about an own axis
ALLOWED_POSE_KEY_SETS = (AXES_POSE_KEYS, ROTATION_POSE_KEYS, COMBINED_POSE_KEYS)


class SpacecraftDescriptionWarning(UserWarning):
    """Something in a description is valid but possibly a mistake, such as a material no component uses."""


@dataclass(frozen=True)
class Spacecraft:
    """A spacecraft ready for the aero solver: panels, the material of every panel, and mass.

    ``materials[i]`` is the material named ``panel_set.material_names[i]``, so a panel's properties are
    ``materials[panel_set.material_ids[p]]``.
    """

    name: str
    mass_kg: float
    panel_set: PanelSet
    materials: tuple[SurfaceMaterial, ...]

    def __post_init__(self) -> None:
        if not np.isfinite(self.mass_kg) or self.mass_kg <= 0:
            raise ValueError(f"Spacecraft {self.name!r}: mass_kg must be > 0, got {self.mass_kg!r}.")
        names = tuple(material.name for material in self.materials)
        if names != self.panel_set.material_names:
            raise ValueError(
                f"Spacecraft {self.name!r}: materials {names} must match the panel set's material names "
                f"{self.panel_set.material_names}, in the same order."
            )


def build_spacecraft(description: Mapping, source: str) -> Spacecraft:
    """Build a ``Spacecraft`` from a description: check it, build and join its components, attach materials.

    Parameters
    ----------
    description
        The parsed description: ``name``, ``mass_kg``, ``max_edge_length_m`` (may be None, the coarsest
        mesh), ``materials`` (name → wall temperature and accommodation) and ``components`` (a list).
    source
        Where the description came from (a file path, or a note), for provenance.

    Raises
    ------
    ValueError
        Naming the place in the description: an unknown or missing key, a value of the wrong kind, an
        undefined material, a bad pose, or a component that fails the orientation checks.

    Warns
    -----
    SpacecraftDescriptionWarning
        For materials defined but used by no component; they are left out.

    Example::

        description = read_spacecraft_description_file("config/geometry/cubesat_3u_example.yaml")
        cubesat = build_spacecraft(description, source="cubesat_3u_example.yaml")
    """
    # 1. The top level.
    _check_keys(description, required=TOP_LEVEL_KEYS, optional=set(), where="the description")
    name = _non_empty_string(description["name"], "name")
    mass_kg = _positive_number(description["mass_kg"], "mass_kg")
    resolution = description["max_edge_length_m"]
    default_resolution_m = None if resolution is None else _positive_number(resolution, "max_edge_length_m")

    # 2. Materials, by name.
    if not isinstance(description["materials"], Mapping) or not description["materials"]:
        raise ValueError("materials must be a non-empty mapping of material name to its properties.")
    materials = {}
    for material_name, properties in description["materials"].items():
        where = f"materials.{material_name}"
        _check_keys(properties, required=MATERIAL_KEYS, optional=set(), where=where)
        materials[material_name] = SurfaceMaterial(
            name=_non_empty_string(material_name, where),
            wall_temperature_kelvin=_positive_number(
                properties["wall_temperature_kelvin"], f"{where}.wall_temperature_kelvin"
            ),
            energy_accommodation=_number(properties["energy_accommodation"], f"{where}.energy_accommodation"),
        )

    # 3. Components: check each entry, then build it.
    entries = description["components"]
    if not isinstance(entries, list) or not entries:
        raise ValueError("components must be a non-empty list.")
    components = []
    for index, entry in enumerate(entries):
        where = _component_label(index, entry)
        _check_component_entry(entry, materials, where)
        try:
            components.append(_build_component(entry, default_resolution_m))
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error

    # 4. Join (runs the orientation checks) and warn about unused materials.
    panel_set = join_components(components, source=source)
    unused = sorted(set(materials) - set(panel_set.material_names))
    if unused:
        warn_every_time(
            f"{source}: materials {unused} are defined but used by no component, so they are left out. "
            "If a component should use one, check its 'material' spelling.",
            SpacecraftDescriptionWarning,
            caller_depth=1,
        )

    # 5. The materials in the panel set's order.
    return Spacecraft(
        name=name,
        mass_kg=mass_kg,
        panel_set=panel_set,
        materials=tuple(materials[material_name] for material_name in panel_set.material_names),
    )


def _build_component(entry: Mapping, default_resolution_m: float | None) -> Component:
    """Build one checked component entry: its primitive, at its resolution, placed at its pose.

    The entry has already been checked: its keys are right for its shape, sizes are positive numbers, its
    material is defined, and its pose has ``centre_m`` with the axes, a turn, or both. So this function only
    has to build.

    Parameters
    ----------
    entry
        One item of ``components``: ``name``, ``shape`` ("box", "plate" or "cylinder"), ``material``,
        ``pose``, the shape's own keys, and optionally ``max_edge_length_m``.
    default_resolution_m
        The spacecraft's ``max_edge_length_m``, used unless the entry has its own.

    Returns
    -------
    Component
        Named after the entry, with its material, and its triangles placed in the body frame.
    """
    # 1. The resolution: the entry's own max_edge_length_m if it has one, else the default.
    res_m = entry.get("max_edge_length_m", default_resolution_m)
    # 2. The triangles in the primitive's own frame, by shape (the checks guarantee a known shape):
    #    box → *size_m; plate → *size_m and two_sided (default False);
    #    cylinder → radius_m, height_m and capped (default True).
    if entry["shape"] == "box":
        triangles_m = build_box_triangles(*entry["size_m"], max_edge_length_m=res_m)
    elif entry["shape"] == "plate":
        triangles_m = build_plate_triangles(
            *entry["size_m"], two_sided=entry.get("two_sided", False), max_edge_length_m=res_m
        )
    else:
        triangles_m = build_cylinder_triangles(
            entry["radius_m"], entry["height_m"], max_edge_length_m=res_m, capped=entry.get("capped", True)
        )

    # 3. The pose, in any of its three forms.
    pose = _pose_from_entry(entry["pose"])
    # 4. Place the triangles and wrap them in a Component(name, material, triangles).
    return Component(entry["name"], entry["material"], place_triangles(triangles_m, pose))


def _pose_from_entry(pose: Mapping) -> Pose:
    """The pose from an entry's ``pose``: by axes, by a turn, or by axes and then a turn about an own axis.

    Without axes the component starts unrotated; ``rotation_axis`` is always in the component's own frame,
    which for an unrotated component is the body frame.
    """
    if "x_axis" in pose:
        placed = make_pose(pose["centre_m"], pose["x_axis"], pose["z_axis"])
        if "rotation_axis" not in pose:
            return placed
        return turn_pose_about_own_axis(placed, pose["rotation_axis"], pose["rotation_angle_deg"])
    return make_pose_from_rotation(pose["centre_m"], pose["rotation_axis"], pose["rotation_angle_deg"])


def _check_component_entry(entry: Mapping, materials: Mapping, where: str) -> None:
    """Raise ValueError, naming ``where``, if a component entry's keys or values are wrong."""
    # 1. A mapping with a known shape; then exactly the keys that shape allows.
    if not isinstance(entry, Mapping):
        raise ValueError(f"{where} must be a mapping of keys to values, got {entry!r}.")
    shape = entry.get("shape")
    if shape not in SHAPE_KEYS:
        raise ValueError(f"{where}: shape must be one of {sorted(SHAPE_KEYS)}, got {shape!r}.")
    required, optional = SHAPE_KEYS[shape]
    _check_keys(
        entry,
        required=COMMON_COMPONENT_KEYS | required,
        optional=OPTIONAL_COMPONENT_KEYS | optional,
        where=where,
    )

    # 2. Name and material.
    _non_empty_string(entry["name"], f"{where}.name")
    if entry["material"] not in materials:
        raise ValueError(
            f"{where}: material {entry['material']!r} is not defined; defined: {sorted(materials)}."
        )

    # 3. Sizes, by shape.
    if shape in SIZE_LENGTHS:
        size = entry["size_m"]
        if not isinstance(size, list) or len(size) != SIZE_LENGTHS[shape]:
            raise ValueError(
                f"{where}.size_m must be a list of {SIZE_LENGTHS[shape]} sizes for a {shape}, got {size!r}."
            )
        for axis, value in enumerate(size):
            _positive_number(value, f"{where}.size_m[{axis}]")
    else:
        _positive_number(entry["radius_m"], f"{where}.radius_m")
        _positive_number(entry["height_m"], f"{where}.height_m")
    for flag in ("two_sided", "capped"):
        if flag in entry and not isinstance(entry[flag], bool):
            raise ValueError(f"{where}.{flag} must be true or false, got {entry[flag]!r}.")
    if entry.get("max_edge_length_m") is not None:
        _positive_number(entry["max_edge_length_m"], f"{where}.max_edge_length_m")

    # 4. The pose: centre_m with the axes, a turn, or both (axes then a turn about an own axis).
    pose = entry["pose"]
    if not isinstance(pose, Mapping):
        raise ValueError(f"{where}.pose must be a mapping, got {pose!r}.")
    if set(pose) not in ALLOWED_POSE_KEY_SETS:
        raise ValueError(
            f"{where}.pose must have centre_m with x_axis and z_axis, or with rotation_axis and "
            f"rotation_angle_deg, or with all four; got {sorted(pose)}."
        )


def _check_keys(mapping: Mapping, required: set, optional: set, where: str) -> None:
    """Raise ValueError naming ``where`` if ``mapping`` is not a mapping, or has missing or unknown keys."""
    if not isinstance(mapping, Mapping):
        raise ValueError(f"{where} must be a mapping of keys to values, got {mapping!r}.")
    missing = sorted(required - set(mapping))
    unknown = sorted(set(mapping) - required - optional)
    problems = ([f"is missing {missing}"] if missing else []) + (
        [f"has unknown keys {unknown}"] if unknown else []
    )
    if (
        problems
    ):  # both at once, so a misspelt key reads as "missing 'size_m'" and "unknown 'sizes_m'" together
        raise ValueError(f"{where} {' and '.join(problems)}; allowed: {sorted(required | optional)}.")


def _component_label(index: int, entry) -> str:
    """'components[i] (name)', or just 'components[i]' when the entry has no usable name."""
    name = entry.get("name") if isinstance(entry, Mapping) else None
    return f"components[{index}] ({name})" if isinstance(name, str) and name else f"components[{index}]"


def _number(value, where: str) -> float:
    """``value`` as a float; raise ValueError naming ``where`` if it is not a finite number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not np.isfinite(value):
        raise ValueError(f"{where} must be a number, got {value!r}.")
    return float(value)


def _positive_number(value, where: str) -> float:
    """``value`` as a float; raise ValueError naming ``where`` unless it is a finite number > 0."""
    number = _number(value, where)
    if number <= 0:
        raise ValueError(f"{where} must be > 0, got {value!r}.")
    return number


def _non_empty_string(value, where: str) -> str:
    """``value`` itself; raise ValueError naming ``where`` unless it is a non-empty string."""
    if not isinstance(value, str) or not value:
        raise ValueError(f"{where} must be a non-empty string, got {value!r}.")
    return value
