"""leodragkit: satellite drag in low Earth orbit.

Import as ``import leodragkit as ldk``. The package covers both sides of drag: the
atmosphere (``density``) and the spacecraft (``aero``), plus Orekit-based propagation
(``orbit``), ensemble forecasts (``forecast``) and one function per task (``workflows``).

This module imports no subpackage, so ``import leodragkit`` stays light: it never starts
the JVM or loads a density model (D-04, D-05).

Read first: ``README.md``, then ``docs/code_tour.md``.
"""

from importlib.metadata import version

__version__ = version("leodragkit")
