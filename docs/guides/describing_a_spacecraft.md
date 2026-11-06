# Describing a spacecraft

How to describe a spacecraft's shape and surfaces so leodragkit can compute its aerodynamics: the shapes you can use, how to place and turn each part, the YAML file format, and what the checks will tell you. No programming is needed beyond running one function. A complete example is `config/geometry/cubesat_3u_example.yaml`; the tutorial notebook (`notebooks/aero_tutorial.ipynb`, sections 5–9) shows every step as a picture.

## 1. The body frame

Everything is described in the spacecraft's **body frame**: three perpendicular axes, x, y and z, fixed to the spacecraft, with lengths in **metres**. You choose where its origin is and which way its axes point, usually along the bus's edges. Later, the spacecraft's attitude says how the body frame is turned in space; the description never needs to know that.

## 2. The three shapes

Every part is one of three shapes. Each is built in its **own frame**, centred on its own origin, and then placed in the body frame (section 3).

| Shape | In its own frame | Sizes | Which way it faces |
| --- | --- | --- | --- |
| `plate` | a flat rectangle in the own x–y plane | `size_m: [x, y]`: the side along own x, then the side along own y | its front face points along own **+z**. With `two_sided: true` it also has a back face, pointing along −z |
| `box` | a closed box with its edges along own x, y and z | `size_m: [x, y, z]` | every face points outward |
| `cylinder` | a tube whose axis runs along own z | `radius_m`, `height_m` | the side faces point away from the axis. With `capped: true` (the default) both ends are closed |

A real spacecraft is usually a box (the bus), some plates (solar panels, radiators, antennas) and perhaps cylinders (booms, whip antennas).

## 3. Placing a part: its pose

A **pose** says where a part goes and which way it faces:

- `centre_m`: where the part's own origin (its centre) goes in the body frame;
- an orientation: by axes (section 4), by a turn (section 5), or both (section 5).

Every component needs a pose, even an unmoved one. That is deliberate: a forgotten pose is more likely a mistake than a choice.

## 4. Orientation by axes

Give two directions in the body frame:

- **`z_axis`**: where the part's own +z ends up. For a plate, this is **the direction its front face points**.
- **`x_axis`**: where the part's own x ends up. For a plate, this is **the direction of its first side** (`size_m[0]`).

They must be perpendicular. The third axis is worked out for you as **y = z × x**, which keeps the axes right-handed, so the plate's second side (`size_m[1]`) runs along that y.

**The recipe:** decide which way the face should point (that is `z_axis`); decide which way its long side should run, at right angles to that (that is `x_axis`).

### Plates in the three planes

A 0.3 × 0.1 m plate, with its 0.3 m side along the first direction listed:

| The plate lies in | and faces | `x_axis` | `z_axis` | Its 0.1 m side runs along |
| --- | --- | --- | --- | --- |
| the x–y plane | +z | [1, 0, 0] | [0, 0, 1] | +y |
| the x–y plane | −z | [1, 0, 0] | [0, 0, −1] | −y |
| the x–z plane | +y | [1, 0, 0] | [0, 1, 0] | −z |
| the x–z plane | −y | [1, 0, 0] | [0, −1, 0] | +z |
| the y–z plane | +x | [0, 1, 0] | [1, 0, 0] | +z |
| the y–z plane | −x | [0, 1, 0] | [−1, 0, 0] | −z |

To run the long side along a different direction in the same plane, choose a different `x_axis` in that plane; for the y–z plane facing +x, `x_axis: [0, 0, 1]` puts the 0.3 m side along z.

### Tilted and arbitrary directions

Any unit vectors work, not only the coordinate axes:

| Placement | `x_axis` | `z_axis` |
| --- | --- | --- |
| facing +z, tilted 30° towards +y about the x axis | [1, 0, 0] | [0, sin 30°, cos 30°] = [0, 0.5, 0.866] |
| facing +x, tilted 20° towards +z about its long side (along y) | [0, 1, 0] | [cos 20°, 0, sin 20°] = [0.940, 0, 0.342] |
| facing the direction (1, 1, 1) | [0.7071, −0.7071, 0] | [0.5774, 0.5774, 0.5774] |

Typed values may be rounded: lengths and perpendicularity within 10⁻³ are accepted and made exact. To check two axes are perpendicular, their dot product (multiply matching entries and add) must be 0, or nearly so.

## 5. Orientation by a turn

Often easier for a tilt: turn the part about one of **its own** axes.

```yaml
pose: {centre_m: [0, 0.2, 0.12], rotation_axis: [1, 0, 0], rotation_angle_deg: 30}
```

`rotation_axis` is given in the part's own frame: [1, 0, 0] is its own x (a plate's first side), [0, 1, 0] its own y (the second side), [0, 0, 1] its own z (a plate's normal). The direction of turning follows the **right-hand rule**: point your right thumb along the axis; a positive angle turns the way your fingers curl. The turn is about the part's centre. The axis can have any length; only its direction counts.

### A turn on its own

With no axes, the part starts unrotated, so its own axes are the body axes, and the turn is about a body direction:

| Turn | Moves the plate's face (own +z) to |
| --- | --- |
| +30° about [1, 0, 0] | [0, −0.5, 0.866]: tilted towards **−y** |
| −30° about [1, 0, 0] | [0, 0.5, 0.866]: tilted towards +y |
| +30° about [0, 1, 0] | [0.5, 0, 0.866]: tilted towards +x |
| +90° about [0, 0, 1] | unchanged (+z); the plate spins in its own plane, its first side now along +y |

### Axes, then a turn

Give both: the axes put the part in its plane (section 4), and the turn then tilts it about its own axis, without working out where that axis ended up in the spacecraft. For example, a panel in the y–z plane facing +x, tilted 20° about its long side:

```yaml
pose:
  centre_m: [0, 0.2, 0.12]
  x_axis: [0, 1, 0]          # its long side runs along body y
  z_axis: [1, 0, 0]          # it faces +x
  rotation_axis: [1, 0, 0]   # then turn about its own x, the long side
  rotation_angle_deg: 20     # its face moves from +x towards −z: [0.940, 0, −0.342]
```

| Pose keys | Meaning |
| --- | --- |
| `centre_m`, `x_axis`, `z_axis` | orient by axes |
| `centre_m`, `rotation_axis`, `rotation_angle_deg` | start unrotated, then turn |
| all five | orient by axes, then turn about the part's own axis |

Each pair must be complete: `x_axis` with `z_axis`, and `rotation_axis` with `rotation_angle_deg`.

## 6. One side or two

A plate's front face is the only one exposed unless you say otherwise. A deployed solar panel, open to the flow on both sides, needs `two_sided: true`; a panel mounted flat on the bus (only one side exposed) does not. This matters twice: for drag, because both faces of a two-sided plate meet the flow; and for the checks (section 10).

## 7. Resolution

Each face is split into triangles. `max_edge_length_m` at the top of the file sets the longest side of any triangle cell, for every part; `null` means as few triangles as possible. A part can set its own `max_edge_length_m`, for example finer for a thin antenna. The force on the spacecraft doesn't depend on the resolution; shadowing (one part hiding another from the flow) does, because each triangle is either wholly hidden or wholly exposed.

## 8. Materials and mass

Each material has a wall temperature (`wall_temperature_kelvin`) and an energy accommodation coefficient (`energy_accommodation`, between 0 and 1: how much of their energy molecules hand to the surface before leaving). Neither has a default; both affect the drag. Every component names one material. A part with two materials, such as a bus with solar cells on two faces, is two components. `mass_kg` is the spacecraft's mass, needed for the ballistic coefficient B = Cd·A/m.

## 9. The file

```yaml
name: 3U CubeSat with deployed panels (example)
mass_kg: 4.0
max_edge_length_m: 0.02

materials:
  aluminium:  {wall_temperature_kelvin: 300.0, energy_accommodation: 0.9}
  solar_cell: {wall_temperature_kelvin: 300.0, energy_accommodation: 0.9}

components:
  - name: bus
    shape: box
    size_m: [0.1, 0.1, 0.34]
    material: aluminium
    pose: {centre_m: [0, 0, 0], x_axis: [1, 0, 0], z_axis: [0, 0, 1]}
  - name: panel_plus_y
    shape: plate
    size_m: [0.3, 0.1]
    two_sided: true
    material: solar_cell
    pose: {centre_m: [0, 0.2, 0.12], x_axis: [0, 1, 0], z_axis: [1, 0, 0]}
```

| Key | Where | Meaning |
| --- | --- | --- |
| `name`, `mass_kg`, `max_edge_length_m`, `materials`, `components` | top level, all required | as above |
| `name`, `shape`, `material`, `pose` | every component, required | names must be unique |
| `size_m` | `box` (three numbers), `plate` (two) | side lengths in m |
| `radius_m`, `height_m` | `cylinder` | in m |
| `two_sided` | `plate`, optional, default false | |
| `capped` | `cylinder`, optional, default true | |
| `max_edge_length_m` | any component, optional | overrides the top-level value |

To build it, in Python or a notebook:

```python
from leodragkit.aero.spacecraft import build_spacecraft
from leodragkit.io.geometry_files import read_spacecraft_description_file

spacecraft = build_spacecraft(read_spacecraft_description_file("my_spacecraft.yaml"), source="my_spacecraft.yaml")
```

Keep your own descriptions in the `geometry` directory from your main config.

## 10. What is checked

Before anything else, every key and value is checked, and an error names its place, such as `components[1] (panel_plus_y) is missing ['size_m'] and has unknown keys ['sizes_m']`. Then every part is checked to face outward:

| Part | Check | If it fails |
| --- | --- | --- |
| closed (a box, a capped cylinder) | every triangle wound the same way, enclosing a positive volume | an error: a face is flipped, or the part is inside out |
| two-sided plate | none needed: it faces both ways | – |
| one-sided plate or open tube | if most of its area faces the spacecraft's centre | a `GeometryOrientationWarning`: possibly typed the wrong way round |

A one-sided panel facing the body can be deliberate, so it is only a warning; check its `z_axis`, or make it two-sided if both faces are exposed. A material that no component uses gives a `SpacecraftDescriptionWarning`, in case a component's material name is misspelt. To turn these warnings into errors, for example in a production run:

```python
import warnings
from leodragkit.aero.geometry_checks import GeometryOrientationWarning
from leodragkit.aero.spacecraft import SpacecraftDescriptionWarning

warnings.simplefilter("error", GeometryOrientationWarning)
warnings.simplefilter("error", SpacecraftDescriptionWarning)
```

## 11. Look at it

```python
from leodragkit.aero.geometry_checks import summarise_geometry
from leodragkit.plots.spacecraft import plot_panel_set_3d

plot_panel_set_3d(spacecraft.panel_set)        # every normal should point away from the spacecraft
summarise_geometry(spacecraft.panel_set)       # one row per part; rows needing attention are shaded
```

## Limits

- **Parts may touch, but must not overlap.** Triangles buried inside another part would still be counted; nothing checks for this.
- **Hinged parts** (a panel turned about its hinge line rather than its centre) are placed by working out the panel's centre and axes once. Moving parts come in a later task (A13).
- **Other shapes** come from mesh files (STL or OBJ) in a later task (A3d).
