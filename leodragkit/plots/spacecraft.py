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

from leodragkit.aero.frames import PanelFlowGeometry
from leodragkit.aero.geometry import PanelSet

COLOR_BY_OPTIONS = ("component", "material")

# Normals are drawn this fraction of the spacecraft's largest dimension long, unless a length is given.
NORMAL_LENGTH_FRACTION = 0.1

# Trace names, fixed so tests and later plot levels can find the traces.
TRIANGLE_EDGES_TRACE_NAME = "triangle edges"
NORMALS_TRACE_NAME = "outward normals"
NORMAL_TIPS_TRACE_NAME = "normal tips"
BODY_AXIS_TRACE_NAMES = ("body x", "body y", "body z")
BODY_AXIS_COLOURS = ("red", "green", "blue")
FLOW_TRACE_NAME = "flow (air past the spacecraft)"
PANELS_BY_INCIDENCE_TRACE_NAME = "panels by cos δ"
# cos δ from −1 (facing away, blue) through 0 (edge-on: the flow perpendicular to the normal, white) to +1
# (facing the flow squarely, red), fixed to [−1, 1] so colours compare between epochs and spacecraft (D-88).
INCIDENCE_COLORSCALE = [[0.0, "rgb(33, 102, 172)"], [0.5, "rgb(247, 247, 247)"], [1.0, "rgb(178, 24, 43)"]]
# Each triangle is drawn this fraction of the spacecraft's size out along its own normal (display only).
# The two sides of a two-sided plate occupy the same place, so without it the renderer shows one side from
# both directions; separated, each side is seen from its own side, coloured by its own cos δ.
DISPLAY_OFFSET_FRACTION = 0.002
NO_POSITIONS_NOTE = "no panel positions: normals drawn from the origin, length proportional to area"


def plot_panel_set_3d(
    panel_set: PanelSet,
    *,
    color_by: str = "component",
    show_normals: bool = True,
    normal_length_m: float | None = None,
    show_body_axes: bool = True,
    show_edges: bool = True,
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
    show_edges
        Outline every triangle in a thin dark line (``TRIANGLE_EDGES_TRACE_NAME``), so coplanar triangles
        and the mesh resolution are visible. Only when the set has triangles.
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
        if show_edges:
            _add_edge_traces(figure, go, panel_set.triangle_vertices_m)
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
        ),
    )
    # 7. Return the figure.
    return figure


def plot_flow_on_spacecraft(
    panel_set: PanelSet,
    geometry: PanelFlowGeometry,
    epoch_index: int = 0,
    *,
    show_edges: bool = True,
    show_body_axes: bool = True,
    figure=None,
):
    """Return a 3-D plotly figure of the panels coloured by cos δ at one epoch, with the flow drawn coming in.

    Colours run from blue (cos δ = −1, facing away), through white (0, edge-on: the flow skims along the
    panel), to red (+1, facing the flow squarely), on a scale fixed to [−1, 1] (``INCIDENCE_COLORSCALE``).
    Each triangle is drawn slightly out along its own normal (``DISPLAY_OFFSET_FRACTION``), so the two sides
    of a two-sided plate, which share one place, are each seen from their own side.
    The flow is an arrow arriving from upstream, pointing along û, the way the air moves past the spacecraft.

    Parameters
    ----------
    panel_set
        The panels the geometry was computed for (``panel_flow_geometry``).
    geometry
        The flow on every panel at every epoch.
    epoch_index
        Which epoch to draw (negative counts from the end, as in Python).
    show_edges, show_body_axes, figure
        As in ``plot_panel_set_3d``.

    Returns
    -------
    plotly.graph_objects.Figure
        With traces: ``PANELS_BY_INCIDENCE_TRACE_NAME`` (one ``Mesh3d`` coloured per triangle, when the set
        has triangles; otherwise a ``Scatter3d`` of normals from the origin, length proportional to area, with
        markers coloured by cos δ), ``FLOW_TRACE_NAME`` (a line and a ``Cone``), the triangle edges and the
        body axes. The title gives the time and the speed.

    Raises
    ------
    ValueError
        If the geometry is for a different number of panels, or ``epoch_index`` is out of range.

    Example::

        geometry = panel_flow_geometry(spacecraft.panel_set, attitude, states)
        plot_flow_on_spacecraft(spacecraft.panel_set, geometry, epoch_index=0).show()
    """
    # 1. The geometry must belong to these panels; the epoch must exist.
    if geometry.panel_count != panel_set.panel_count:
        raise ValueError(
            f"The geometry is for {geometry.panel_count} panels, but the panel set has "
            f"{panel_set.panel_count}."
        )
    if not -len(geometry) <= epoch_index < len(geometry):
        raise ValueError(f"epoch_index {epoch_index} is out of range for {len(geometry)} epochs.")
    go = _import_plotly()
    if figure is None:
        figure = go.Figure()
    cos_incidence = geometry.cos_incidence[epoch_index]
    size_m = _largest_dimension_m(panel_set)

    # 2. The panels, coloured by cos δ: one triangle per panel, or normals from the origin for a macro model.
    colour_scale = {"colorscale": INCIDENCE_COLORSCALE, "cmin": -1.0, "cmax": 1.0}
    hover = [
        f"panel {p}<br>cos δ {cos_incidence[p]:.3f}<br>area {panel_set.areas_m2[p]:.4g} m²"
        for p in range(len(cos_incidence))
    ]
    if panel_set.has_triangles:
        offset_m = DISPLAY_OFFSET_FRACTION * size_m * panel_set.outward_normals[:, np.newaxis, :]
        corners_m = (panel_set.triangle_vertices_m + offset_m).reshape(-1, 3)
        first_corner = np.arange(0, len(corners_m), 3)
        figure.add_trace(
            go.Mesh3d(
                x=corners_m[:, 0],
                y=corners_m[:, 1],
                z=corners_m[:, 2],
                i=first_corner,
                j=first_corner + 1,
                k=first_corner + 2,
                intensity=cos_incidence,
                intensitymode="cell",
                colorbar={"title": "cos δ"},
                flatshading=True,
                name=PANELS_BY_INCIDENCE_TRACE_NAME,
                hovertext=np.repeat(hover, 3),
                hoverinfo="text",
                **colour_scale,
            )
        )
        if show_edges:
            _add_edge_traces(figure, go, panel_set.triangle_vertices_m)
    else:
        relative_areas = panel_set.areas_m2 / panel_set.areas_m2.max()
        tips_m = size_m * relative_areas[:, np.newaxis] * panel_set.outward_normals
        figure.add_trace(
            go.Scatter3d(
                x=tips_m[:, 0],
                y=tips_m[:, 1],
                z=tips_m[:, 2],
                mode="markers",
                marker={"color": cos_incidence, "size": 6, "colorbar": {"title": "cos δ"}, **colour_scale},
                name=PANELS_BY_INCIDENCE_TRACE_NAME,
                hovertext=hover,
                hoverinfo="text",
            )
        )
        _add_normal_traces(figure, go, np.zeros_like(tips_m), tips_m)

    # 3. The flow: a line from upstream to just short of the spacecraft, and a cone at its end, along û.
    flow = geometry.flow_direction[epoch_index]
    start_m, tip_m = -2.0 * size_m * flow, -0.8 * size_m * flow
    figure.add_trace(
        go.Scatter3d(
            x=[start_m[0], tip_m[0]],
            y=[start_m[1], tip_m[1]],
            z=[start_m[2], tip_m[2]],
            mode="lines",
            line={"color": "black", "width": 6},
            name=FLOW_TRACE_NAME,
            legendgroup=FLOW_TRACE_NAME,
        )
    )
    figure.add_trace(
        go.Cone(
            x=[tip_m[0]],
            y=[tip_m[1]],
            z=[tip_m[2]],
            u=[flow[0]],
            v=[flow[1]],
            w=[flow[2]],
            anchor="tip",
            sizemode="absolute",
            sizeref=0.3 * size_m,
            colorscale=[[0, "black"], [1, "black"]],
            showscale=False,
            name=FLOW_TRACE_NAME,
            legendgroup=FLOW_TRACE_NAME,
            showlegend=False,
            hoverinfo="skip",
        )
    )

    # 4. Body axes and layout.
    if show_body_axes:
        _add_body_axes_traces(figure, go, size_m)
    time = str(geometry.times[epoch_index])[:19]
    speed = geometry.speed_m_per_s[epoch_index]
    figure.update_layout(
        title=f"{panel_set.source}: the flow at {time} {geometry.time_scale}, {speed:.0f} m/s",
        scene={"aspectmode": "data", "xaxis_title": "x (m)", "yaxis_title": "y (m)", "zaxis_title": "z (m)"},
    )
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
                x=corners_m[:, 0],
                y=corners_m[:, 1],
                z=corners_m[:, 2],
                i=first_corner,
                j=first_corner + 1,
                k=first_corner + 2,
                name=name,
                showlegend=True,
                flatshading=True,
                color=palette[name_index % len(palette)],
                hovertext=np.repeat(texts, 3),
                hoverinfo="text",
            )
        )


def _add_edge_traces(figure, go, triangle_vertices_m: np.ndarray) -> None:
    """Add every triangle's outline as one ``Scatter3d`` trace of lines, broken between triangles.

    Each triangle is drawn v₀ → v₁ → v₂ → v₀ followed by a break (None), so the trace holds five
    entries per triangle and can be switched off from the legend.
    """
    # 1. Each triangle as v0, v1, v2, v0 and a break; an object array can hold None, a float array cannot.
    count = len(triangle_vertices_m)
    points = np.full((count, 5, 3), None, dtype=object)
    points[:, :3] = triangle_vertices_m
    points[:, 3] = triangle_vertices_m[:, 0]
    points = points.reshape(-1, 3)

    # 2. One thin, dark trace without hover labels, so it never hides the panels' own hover text.
    figure.add_trace(
        go.Scatter3d(
            x=points[:, 0].tolist(),
            y=points[:, 1].tolist(),
            z=points[:, 2].tolist(),
            mode="lines",
            line={"color": "black", "width": 1},
            name=TRIANGLE_EDGES_TRACE_NAME,
            hoverinfo="skip",
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
    figure.add_trace(
        go.Scatter3d(
            x=x_coords,
            y=y_coords,
            z=z_coords,
            mode="lines",
            name=NORMALS_TRACE_NAME,
            legendgroup=NORMALS_TRACE_NAME,
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=ends_m[:, 0],
            y=ends_m[:, 1],
            z=ends_m[:, 2],
            mode="markers",
            marker={"size": 3},
            name=NORMAL_TIPS_TRACE_NAME,
            legendgroup=NORMALS_TRACE_NAME,
        )
    )


def _add_body_axes_traces(figure, go, length_m: float) -> None:
    """Add the body x, y and z axes as three ``Scatter3d`` lines from the origin, named and coloured."""
    # 1. For each axis: a line from the origin to length_m along it, named BODY_AXIS_TRACE_NAMES[i],
    #    coloured BODY_AXIS_COLOURS[i], with its label as text at the tip.
    figure.add_trace(
        go.Scatter3d(
            x=[0, length_m],
            y=[0, 0],
            z=[0, 0],
            mode="lines",
            name=BODY_AXIS_TRACE_NAMES[0],
            line=dict(color=BODY_AXIS_COLOURS[0]),
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=[0, 0],
            y=[0, length_m],
            z=[0, 0],
            mode="lines",
            name=BODY_AXIS_TRACE_NAMES[1],
            line=dict(color=BODY_AXIS_COLOURS[1]),
        )
    )
    figure.add_trace(
        go.Scatter3d(
            x=[0, 0],
            y=[0, 0],
            z=[0, length_m],
            mode="lines",
            name=BODY_AXIS_TRACE_NAMES[2],
            line=dict(color=BODY_AXIS_COLOURS[2]),
        )
    )


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
