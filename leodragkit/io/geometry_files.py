"""Reading spacecraft description files (YAML) written by users, and the mesh files they name.

These are the user's own files, not downloaded data, so only the reading part of the io template applies:
``read_spacecraft_description_file`` returns the parsed mapping, and ``leodragkit.aero.spacecraft``
checks and builds it (aero never parses files). ``load_spacecraft_description`` also reads every mesh
file a description names (``shape: mesh``) and adds its triangles, in metres, so it can be built.

The format is described in ``docs/guides/describing_a_spacecraft.md``; an example is
``config/geometry/cubesat_3u_example.yaml``.
"""

import csv
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import yaml

from leodragkit.io.mesh_files import read_obj_file, read_stl_file

MESH_READERS = {".stl": read_stl_file, ".obj": read_obj_file}

# Macro-model tables: the columns every table has, and the position columns it may have (all three or none).
MACRO_MODEL_COLUMNS = ("component", "material", "normal_x", "normal_y", "normal_z", "area_m2")
MACRO_MODEL_CENTROID_COLUMNS = ("centroid_x_m", "centroid_y_m", "centroid_z_m")


@dataclass(frozen=True)
class MacroModelTable:
    """A macro model as read from its table: one entry per panel (row), in file order."""

    component_names: tuple[str, ...]  # per panel
    material_names: tuple[str, ...]  # per panel
    outward_normals: np.ndarray  # (N, 3) as written; normalised later if within rounding (D-63)
    areas_m2: np.ndarray  # (N,)
    centroids_m: np.ndarray | None  # (N, 3), or None when the table has no position columns
    source: str  # the file


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


def read_macro_model_file(path: str | Path) -> MacroModelTable:
    """Read a macro-model table (CSV): one row per flat panel, with its component, material, normal and area.

    Columns: ``component``, ``material``, ``normal_x``, ``normal_y``, ``normal_z``, ``area_m2``, and
    optionally all three of ``centroid_x_m``, ``centroid_y_m``, ``centroid_z_m``. Lengths in metres, areas in
    m². The table is not checked for physics here (``leodragkit.aero`` checks normals and areas); only that
    every value is present and of the right kind.

    Raises
    ------
    FileNotFoundError
        If there is no file.
    ValueError
        For a missing or unknown column, only some of the centroid columns, no rows, or a value that is
        empty or not a number. The message gives the file and line.

    Example::

        table = read_macro_model_file("config/geometry/cubesat_3u_macro_model.csv")
        table.areas_m2.sum()
    """
    # 1. The file, read as UTF-8; the header must have the required columns and all or none of the centroids.
    file_path = Path(path).expanduser()
    if not file_path.is_file():
        raise FileNotFoundError(f"No macro-model table at {file_path}.")
    with file_path.open(encoding="utf-8", newline="") as file:
        reader = csv.DictReader(file)
        columns = set(reader.fieldnames or [])
        missing = sorted(set(MACRO_MODEL_COLUMNS) - columns)
        unknown = sorted(columns - set(MACRO_MODEL_COLUMNS) - set(MACRO_MODEL_CENTROID_COLUMNS))
        centroid_columns = columns & set(MACRO_MODEL_CENTROID_COLUMNS)
        if missing or unknown:
            raise ValueError(
                f"{file_path}: columns must be {list(MACRO_MODEL_COLUMNS)}, optionally with "
                f"{list(MACRO_MODEL_CENTROID_COLUMNS)}; missing {missing}, unknown {unknown}."
            )
        if centroid_columns and len(centroid_columns) != 3:
            raise ValueError(
                f"{file_path}: give all three centroid columns or none; got {sorted(centroid_columns)}."
            )

        # 2. The rows into arrays (your part), with the line of every problem.
        rows = list(reader)
    if not rows:
        raise ValueError(f"{file_path} has a header but no panels.")
    return _macro_model_from_rows(rows, has_centroids=bool(centroid_columns), file_path=file_path)


def _macro_model_from_rows(rows: list[dict], has_centroids: bool, file_path: Path) -> MacroModelTable:
    """Turn the table's rows (dicts of strings, as ``csv.DictReader`` gives) into a ``MacroModelTable``.

    Row r (counting from 0) is on line r + 2 of the file: line 1 is the header.

    Raises
    ------
    ValueError
        For an empty ``component`` or ``material``, or a numeric field that is empty or not a number, naming
        the file, the line and the column.
    """
    comp = []
    mat = []
    normal_x = []
    normal_y = []
    normal_z = []
    areas = []
    centroids = [] if has_centroids else None

    for r, row in enumerate(rows):
        # 1. For each row: the two names, which must not be empty (strip spaces first).
        if not row["component"].strip():
            raise ValueError(f"{file_path}, line {r + 2}, column component: empty value")
        if not row["material"].strip():
            raise ValueError(f"{file_path}, line {r + 2}, column material: empty value")
        comp.append(row["component"].strip())
        mat.append(row["material"].strip())
        # 2. The numbers: normal_x, normal_y, normal_z, area_m2, and the three centroid columns when present;
        # float(value) for each, raising ValueError(f"{file_path}, line {r + 2}, column {name}: …") 
        # on failure.
        try:
            normal_x.append(float(row["normal_x"]))
        except ValueError:
            raise ValueError(f"{file_path}, line {r + 2}, column normal_x: invalid value '{row['normal_x']}'")
        try:
            normal_y.append(float(row["normal_y"]))
        except ValueError:
            raise ValueError(f"{file_path}, line {r + 2}, column normal_y: invalid value '{row['normal_y']}'")
        try:
            normal_z.append(float(row["normal_z"]))
        except ValueError:
            raise ValueError(f"{file_path}, line {r + 2}, column normal_z: invalid value '{row['normal_z']}'")
        try:
            areas.append(float(row["area_m2"]))
        except ValueError:
            raise ValueError(f"{file_path}, line {r + 2}, column area_m2: invalid value '{row['area_m2']}'")
        if has_centroids:
            try:
                centroids.append([float(row["centroid_x_m"]), float(row["centroid_y_m"]),
                                  float(row["centroid_z_m"])])
            except ValueError:
                raise ValueError(f"{file_path}, line {r + 2}, centroid columns: invalid values "
                                 f"'{row['centroid_x_m']}', '{row['centroid_y_m']}', '{row['centroid_z_m']}'")

    # 3. Collect them into a MacroModelTable: tuples of names, an (N, 3) normal array, an (N,) area array,
    #    an (N, 3) centroid array or None, and source=file_path.name.
    return MacroModelTable(tuple(comp), tuple(mat), np.array([normal_x, normal_y, normal_z]).T, np.array(areas),
                           np.array(centroids) if has_centroids else None, file_path.name)

def load_spacecraft_description(path: str | Path) -> dict:
    """Read a description and every mesh file it names, ready for ``build_spacecraft``.

    A description with ``macro_model: {file: …}`` has its table read (``read_macro_model_file``) and added as
    ``macro_model["table"]``. For each component with ``shape: mesh``, the file named by its ``file`` key is
    read, relative to the description's own folder, in its ``length_unit``, with its ``reverse_winding``
    (default false). Two keys are added to the component: ``triangle_vertices_m`` (the triangles in metres)
    and ``mesh_source``.
    Everything else is checked later, by ``build_spacecraft``.

    Raises
    ------
    FileNotFoundError
        If the description or a mesh file is missing.
    ValueError
        If a mesh component lacks ``file`` or ``length_unit``, names a file that is not ``.stl`` or ``.obj``,
        or its mesh is malformed. The message names the component.

    Example::

        description = load_spacecraft_description("my_spacecraft.yaml")
        spacecraft = build_spacecraft(description, source="my_spacecraft.yaml")
    """
    # 1. The description itself.
    description_path = Path(path).expanduser()
    description = read_spacecraft_description_file(description_path)

    # 2. A macro-model description: read its table and add it as macro_model["table"].
    macro_model = description.get("macro_model")
    if isinstance(macro_model, dict):
        if "file" not in macro_model:
            raise ValueError("macro_model needs a 'file': the table of panels, relative to the description.")
        macro_model["table"] = read_macro_model_file(description_path.parent / macro_model["file"])

    # 3. Each mesh component: read its file and add the triangles.
    for index, entry in enumerate(description.get("components") or []):
        if not isinstance(entry, dict) or entry.get("shape") != "mesh":
            continue
        where = f"components[{index}] ({entry.get('name')})"
        missing = [key for key in ("file", "length_unit") if key not in entry]
        if missing:
            raise ValueError(f"{where}: a mesh component needs {missing}.")
        mesh_path = description_path.parent / entry["file"]
        reader = MESH_READERS.get(mesh_path.suffix.lower())
        if reader is None:
            raise ValueError(f"{where}: mesh files must be {sorted(MESH_READERS)}, got {mesh_path.name!r}.")
        try:
            mesh = reader(
                mesh_path, entry["length_unit"], reverse_winding=bool(entry.get("reverse_winding", False))
            )
        except ValueError as error:
            raise ValueError(f"{where}: {error}") from error
        entry["triangle_vertices_m"] = mesh.triangle_vertices_m
        entry["mesh_source"] = mesh.source
    return description
