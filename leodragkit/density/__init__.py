"""Thermospheric density models behind one Protocol: ``DensityModel`` and ``AtmosphereState``.

Holds the interface and the models that live in this package (MSIS through ``pymsis``, and a
toy exponential model for tests). The den_pcaxg models live in the separate model package and
satisfy the same Protocol. Rules: ``.claude/rules/density.md``.

Import rule: may import from ``io`` only. Importing this package loads no model's
dependency; each builder imports its own.
Empty for now; the interface and MSIS arrive in task D1 (``docs/tasks.md``).
"""
