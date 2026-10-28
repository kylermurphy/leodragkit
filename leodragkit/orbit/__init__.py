"""Everything that needs Orekit: start states, propagation with drag, orbit-mean altitude,
ballistic-coefficient estimation, and the atmosphere adapter between Orekit and the density models.

All JPype and Orekit code in leodragkit lives here (D-05). The JVM starts on first use,
never on import. Rules: ``.claude/rules/orbit_and_forecast.md``.

Import rule: may import from ``io`` and ``density`` (D-03).
Empty for now; the first modules arrive in task B2 (``docs/tasks.md``).
"""
