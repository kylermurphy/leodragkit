"""Reading spacecraft description files (YAML) written by users, and the mesh files they name.

These are the user's own files, not downloaded data, so only the reading part of the io template applies:
``read_spacecraft_description_file`` returns the parsed mapping, and ``leodragkit.aero.spacecraft``
checks and builds it (aero never parses files). ``load_spacecraft_description`` also reads every mesh
file a description names (``shape: mesh``) and adds its triangles, in metres, so it can be built.

The format is described in ``docs/guides/describing_a_spacecraft.md``; an example is
``config/geometry/cubesat_3u_example.yaml``.
"""

from pathlib import Path

import yaml

from leodragkit.io.mesh_files import read_obj_file, read_stl_file

MESH_READERS = {".stl": read_stl_file, ".obj": read_obj_file}


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


def load_spacecraft_description(path: str | Path) -> dict:
    """Read a description and every mesh file it names, ready for ``build_spacecraft``.

    For each component with ``shape: mesh``, the file named by its ``file`` key is read, relative to the
    description's own folder, in its ``length_unit``, with its ``reverse_winding`` (default false). Two keys
    are added to the component: ``triangle_vertices_m`` (the triangles in metres) and ``mesh_source``.
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

    # 2. Each mesh component: read its file and add the triangles.
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
