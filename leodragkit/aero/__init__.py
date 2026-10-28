"""Spacecraft drag from panel geometry and attitude: Cd·A(t) and B(t) = Cd·A(t)/m.

A free-molecular panel method (Sentman flat plates, diffuse reflection with incomplete
accommodation) summed over panels rotated by attitude quaternions (D-28). Used on its own,
for example by contigo_edr, and by B estimation in ``scaled_aero`` mode (D-22).
Method: ``docs/methods/``; rules: ``.claude/rules/aero.md``.

Import rule: imports only numpy and scipy, and nothing from leodragkit (D-04), so other
programs can use it without Orekit or the density models.
Empty for now; the first module arrives in task A1 (``docs/tasks.md``).
"""
