"""Figures of leodragkit objects: spacecraft geometry first, then flows, attitude and orbits.

Plot functions take an optional figure or axes and return it, and never write files; saving is the
caller's choice. Interactive 3-D figures use plotly, an optional dependency imported only inside the
functions that need it; static figures use matplotlib.

Import rule: imports from the subpackages it draws (``aero`` first) and is imported by none of them.
A module that needs Orekit (orbit plots) is kept separate, so importing the others never starts the JVM.
Empty for now; the first module, ``spacecraft.py``, arrives in task A3p (``docs/tasks.md``).
"""
