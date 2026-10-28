"""One module per task. Each workflow takes typed settings and returns one result object.

A workflow writes files only when given an output folder; each result type has ``save_*`` and
``load_*`` in the module that produces it. Composite workflows chain others in memory.

Import rule: may import from every other leodragkit subpackage.
Empty for now; workflows are added as their building blocks land (task W1, ``docs/tasks.md``).
"""
