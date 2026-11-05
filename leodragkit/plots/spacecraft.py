"""Interactive 3-D plot of a spacecraft's panels: plot level 1, the spacecraft on its own.

Shows what was built or loaded before any physics runs: the shape, which component and material each
panel belongs to, and which way every outward normal points. Later levels (the flow on the spacecraft,
the spacecraft relative to the Earth) add traces to the same figure.

Uses plotly, an optional dependency imported only inside the plotting function, so importing this
module never needs it. Nothing is written to disk: call ``figure.show()`` or
``figure.write_html("spacecraft.html")`` yourself.

Read first: ``plot_panel_set_3d``.
"""

import numpy as np

from leodragkit.aero.geometry import PanelSet

COLOR_BY_OPTIONS = ("component", "material")

# Normals are drawn this fraction of the spacecraft's largest dimension long, unless a length is given.
NORMAL_LENGTH_FRACTION = 0.1

# Trace names, fixed so tests and later plot levels can find the traces.
NORMALS_TRACE_NAME = "outward normals"
NORMAL_TIPS_TRACE_NAME = "normal tips"
BODY_AXIS_TRACE_NAMES = ("body x", "body y", "body z")
BODY_AXIS_COLOURS = ("red", "green", "blue")
NO_POSITIONS_NOTE = "no panel positions: normals drawn from the origin, length proportional to area"


def plot_panel_set_3d(
    panel_set: PanelSet,
    *,
    color_by: str = "component",
    show_normals: bool = True,
    normal_length_m: float | None = None,
    show_body_axes: bool = True,
    figure=None,
):
    """Return an interactive 3-D plotly figure of the panels, their outward normals and the body axes.

    Parameters
    ----------
    panel_set
        The panels to draw (``leodragkit.aero.geometry.PanelSet``).
    color_by
        ``"component"`` or ``"material"``: one mesh trace per name, so the legend lists them and each
        can be hidden by clicking it.
    show_normals
        Draw each panel's outward normal as a line with a marker at its tip.
    normal_length_m
        Length of the normal lines in metres; by default ``NORMAL_LENGTH_FRACTION`` of the largest dimension.
    show_body_axes
        Draw the body x, y and z axes from the origin, in red, green and blue.
    figure
        An existing ``plotly.graph_objects.Figure`` to add the traces to; a new one when None.

    Returns
    -------
    plotly.graph_objects.Figure
        The figure, with traces:

        - one ``Mesh3d`` per component or material, named after it (only when the set has triangles);
        - ``NORMALS_TRACE_NAME`` (``Scatter3d``, lines: start, end, None per panel) and
          ``NORMAL_TIPS_TRACE_NAME`` (``Scatter3d``, one marker per panel);
        - ``BODY_AXIS_TRACE_NAMES``.

        Normals start at the centroids when they are known. Without positions they start at the origin,
        panel i drawn ``largest dimension × area_i / largest area`` long, and the title says so
        (``NO_POSITIONS_NOTE``).

    Raises
    ------
    ValueError
        If ``color_by`` is not one of ``COLOR_BY_OPTIONS``.
    ImportError
        If plotly is not installed, with the command to install it.

    Example::

        figure = plot_panel_set_3d(panel_set, color_by="material")
        figure.show()
    """
    # 1. Check color_by (raise naming COLOR_BY_OPTIONS), then go = _import_plotly().
    if color_by not in COLOR_BY_OPTIONS:
        raise ValueError(f"color_by must be one of {COLOR_BY_OPTIONS}, not {color_by!r}")
    go = _import_plotly()
    # 2. Use the given figure, or make a new go.Figure().
    if figure is None:
        figure = go.Figure()
    # 3. Mesh: if the set has triangles, _add_mesh_traces(figure, go, panel_set, color_by).
    if panel_set.triangle_vertices_m is not None:
        _add_mesh_traces(figure, go, panel_set, color_by)
    # 4. Normals: work out each line's start and end (centroids, or the origin scaled by area; the length
    #    from normal_length_m or _largest_dimension_m), then _add_normal_traces(figure, go, starts, ends).
    if show_normals:
        size_m = _largest_dimension_m(panel_set)
        if panel_set.has_positions:
            length_m = normal_length_m if normal_length_m is not None else NORMAL_LENGTH_FRACTION * size_m
            starts_m = panel_set.centroids_m
            ends_m = starts_m + length_m * panel_set.outward_normals
        else:
            starts_m = np.zeros_like(panel_set.outward_normals)
            relative_areas = panel_set.areas_m2 / panel_set.areas_m2.max()
            ends_m = size_m * relative_areas[:, np.newaxis] * panel_set.outward_normals

        _add_normal_traces(figure, go, starts_m, ends_m)

    # 5. Body axes: _add_body_axes_traces(figure, go, _largest_dimension_m(panel_set)).
    if show_body_axes:
        _add_body_axes_traces(figure, go, _largest_dimension_m(panel_set))
    # 6. Layout: scene aspectmode="data", axis titles "x (m)", "y (m)", "z (m)", and a title with the
    #    source (plus NO_POSITIONS_NOTE when the set has no positions).
    figure.update_layout(
        title=f"Spacecraft panels from {panel_set.source}"
        + (f"<br>{NO_POSITIONS_NOTE}" if not panel_set.has_positions else ""),
        scene=dict(
            aspectmode="data",
            xaxis_title="x (m)",
            yaxis_title="y (m)",
            zaxis_title="z (m)",
        )
    )
    # 7. Return the figure.
    return figure


def _add_mesh_traces(figure, go, panel_set: PanelSet, color_by: str) -> None:
    """Add one ``go.Mesh3d`` per component (or material), named after it, coloured from a qualitative palette.

    Each trace gets its triangles' corners as x, y, z (corners need not be shared between triangles) and
    i, j, k indexing them, with flatshading=True and hover text giving panel index, component, material,
    area in m² and normal.
    """
    import plotly.colors
    # 1. Choose the ids and names (component or material).
    if color_by == "component":
        ids, names = panel_set.component_ids, panel_set.component_names
    else:
        ids, names = panel_set.material_ids, panel_set.material_names
    palette = plotly.colors.qualitative.Plotly

    # 2. One trace per name: its triangles' corners, flattened, with i, j, k pointing at them in threes.
    for name_index, name in enumerate(names):
        panels = np.flatnonzero(ids == name_index)
        if len(panels) == 0:
            continue
        corners_m = panel_set.triangle_vertices_m[panels].reshape(-1, 3)
        first_corner = np.arange(0, len(corners_m), 3)

        # 3. Hover text per triangle, repeated for its three corners (Mesh3d text belongs to vertices).
        texts = [
            f"panel {p}<br>component {panel_set.component_names[panel_set.component_ids[p]]}"
            f"<br>material {panel_set.material_names[panel_set.material_ids[p]]}"
            f"<br>area {panel_set.areas_m2[p]:.4g} m²<br>normal {np.round(panel_set.outward_normals[p], 3)}"
            for p in panels
        ]

        figure.add_trace(
            go.Mesh3d(
                x=corners_m[:, 0], y=corners_m[:, 1], z=corners_m[:, 2],
                i=first_corner, j=first_corner + 1, k=first_corner + 2,
                name=name, showlegend=True, flatshading=True,
                color=palette[name_index % len(palette)],
                hovertext=np.repeat(texts, 3), hoverinfo="text",
            )
        )


def _add_normal_traces(figure, go, starts_m: np.ndarray, ends_m: np.ndarray) -> None:
    """Add the normal lines and their tips: two ``Scatter3d`` traces, modes "lines" and "markers".

    The line trace holds start, end, None for each panel, so all lines are one trace; both traces share a
    legend group, so clicking either hides both.
    """
    # 1. Interleave starts, ends and None rows into x, y, z lists of length 3n.
    # The None is needed to break the lines between panels, else all normals are one long line.
    x_coords, y_coords, z_coords = [], [], []
    for start, end in zip(starts_m, ends_m):
        x_coords += [start[0], end[0], None]
        y_coords += [start[1], end[1], None]
        z_coords += [start[2], end[2], None]
    # 2. Add the lines trace (NORMALS_TRACE_NAME) and the tips trace (NORMAL_TIPS_TRACE_NAME, at the ends).
    figure.add_trace(go.Scatter3d(x=x_coords, y=y_coords, z=z_coords, mode='lines',
                                  name=NORMALS_TRACE_NAME,legendgroup=NORMALS_TRACE_NAME))
    figure.add_trace(go.Scatter3d(x=ends_m[:, 0], y=ends_m[:, 1], z=ends_m[:, 2],
                                   mode="markers", marker={"size": 3},
                                   name=NORMAL_TIPS_TRACE_NAME, legendgroup=NORMALS_TRACE_NAME))


def _add_body_axes_traces(figure, go, length_m: float) -> None:
    """Add the body x, y and z axes as three ``Scatter3d`` lines from the origin, named and coloured."""
    # 1. For each axis: a line from the origin to length_m along it, named BODY_AXIS_TRACE_NAMES[i],
    #    coloured BODY_AXIS_COLOURS[i], with its label as text at the tip.
    figure.add_trace(go.Scatter3d(x=[0,length_m], y=[0,0], z=[0,0], mode='lines',
                                      name=BODY_AXIS_TRACE_NAMES[0], 
                                      line=dict(color=BODY_AXIS_COLOURS[0])))
    figure.add_trace(go.Scatter3d(x=[0,0], y=[0,length_m], z=[0,0], mode='lines',
                                          name=BODY_AXIS_TRACE_NAMES[1],
                                      line=dict(color=BODY_AXIS_COLOURS[1])))
    figure.add_trace(go.Scatter3d(x=[0,0], y=[0,0], z=[0,length_m], mode='lines',
                                              name=BODY_AXIS_TRACE_NAMES[2],
                                      line=dict(color=BODY_AXIS_COLOURS[2])))


def _largest_dimension_m(panel_set: PanelSet) -> float:
    """Largest extent of the spacecraft in metres, to scale normals and axes.

    From the triangle corners when known, else the centroids; without positions (or with all centroids at
    one point), the square root of the total area.
    """
    points = (
        panel_set.triangle_vertices_m.reshape(-1, 3) if panel_set.has_triangles else panel_set.centroids_m
    )
    if points is not None:
        extent = float(np.max(np.ptp(points, axis=0)))
        if extent > 0:
            return extent
    return float(np.sqrt(np.sum(panel_set.areas_m2)))


def _import_plotly():
    """Return ``plotly.graph_objects``; raise ImportError saying how to install plotly if it is missing."""
    try:
        import plotly.graph_objects as go
    except ImportError as error:
        raise ImportError(
            "Interactive 3-D plots need plotly, an optional dependency of leodragkit. "
            "Install it with: conda install -c conda-forge plotly"
        ) from error
    return go
