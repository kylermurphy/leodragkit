"""Shared test fixtures: small spacecraft geometries built by hand, used by the aero and plots tests."""

import numpy as np
import pytest

from leodragkit.aero.geometry import PanelSet, panel_set_from_triangles


def build_unit_cube_triangles_m() -> np.ndarray:
    """The 12 triangles of a unit cube centred on the origin, each counter-clockwise seen from outside.

    Faces in order −x, +x, −y, +y, −z, +z, two triangles each.
    """
    corners = np.array(
        [[x, y, z] for x in (-0.5, 0.5) for y in (-0.5, 0.5) for z in (-0.5, 0.5)]
    )  # index = 4·(x > 0) + 2·(y > 0) + (z > 0)
    faces = [  # each face as four corners, counter-clockwise seen from outside
        (0, 1, 3, 2),  # −x
        (4, 6, 7, 5),  # +x
        (0, 4, 5, 1),  # −y
        (2, 3, 7, 6),  # +y
        (0, 2, 6, 4),  # −z
        (1, 5, 7, 3),  # +z
    ]
    triangles = []
    for a, b, c, d in faces:
        triangles += [corners[[a, b, c]], corners[[a, c, d]]]
    return np.array(triangles)


@pytest.fixture
def unit_cube_triangles_m() -> np.ndarray:
    """The 12 triangles of a unit cube centred on the origin (see ``build_unit_cube_triangles_m``)."""
    return build_unit_cube_triangles_m()


@pytest.fixture
def unit_cube_panel_set() -> PanelSet:
    """A unit cube with two components and two materials, for tests that need variety.

    The four side faces (±x, ±y) are the component "body" and the two z faces are "end_caps"; the ±x
    and ±z faces are "aluminium" and the ±y faces are "solar_cell".
    """
    component_ids = np.array([0] * 8 + [1] * 4)
    material_ids = np.array([0, 0, 0, 0, 1, 1, 1, 1, 0, 0, 0, 0])
    return panel_set_from_triangles(
        build_unit_cube_triangles_m(),
        component_ids,
        material_ids,
        ("body", "end_caps"),
        ("aluminium", "solar_cell"),
        source="unit cube (test fixture)",
    )


# A leap-second kernel in NAIF's text format, with the values of naif0012.tls (SPICE's parameters for
# TDB − TT, and TAI − UTC from 1972 to 2017), so time-scale tests run without downloading the real file.
LEAP_SECOND_KERNEL_FOR_TESTS = r"""KPL/LSK

Leap-second kernel for leodragkit's tests: the data of NAIF's naif0012.tls.

\begindata

DELTET/DELTA_T_A       =   32.184
DELTET/K               =    1.657D-3
DELTET/EB              =    1.671D-2
DELTET/M               = (  6.239996D0   1.99096871D-7 )

DELTET/DELTA_AT        = ( 10,   @1972-JAN-1
                           11,   @1972-JUL-1
                           12,   @1973-JAN-1
                           13,   @1974-JAN-1
                           14,   @1975-JAN-1
                           15,   @1976-JAN-1
                           16,   @1977-JAN-1
                           17,   @1978-JAN-1
                           18,   @1979-JAN-1
                           19,   @1980-JAN-1
                           20,   @1981-JUL-1
                           21,   @1982-JUL-1
                           22,   @1983-JUL-1
                           23,   @1985-JUL-1
                           24,   @1988-JAN-1
                           25,   @1990-JAN-1
                           26,   @1991-JAN-1
                           27,   @1992-JUL-1
                           28,   @1993-JUL-1
                           29,   @1994-JUL-1
                           30,   @1996-JAN-1
                           31,   @1997-JUL-1
                           32,   @1999-JAN-1
                           33,   @2006-JAN-1
                           34,   @2009-JAN-1
                           35,   @2012-JUL-1
                           36,   @2015-JUL-1
                           37,   @2017-JAN-1 )

\begintext
"""


@pytest.fixture(scope="session")
def leap_second_kernel(tmp_path_factory):
    """A checked LeapSecondKernel read from LEAP_SECOND_KERNEL_FOR_TESTS (no network)."""
    from leodragkit.io.spice_kernels import read_leap_second_kernel_file

    path = tmp_path_factory.mktemp("spice_kernels") / "test_leap_seconds.tls"
    path.write_bytes(LEAP_SECOND_KERNEL_FOR_TESTS.encode("ascii"))
    return read_leap_second_kernel_file(path)
