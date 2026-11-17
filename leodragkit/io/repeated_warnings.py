"""Warnings that Python never hides as repeats, for ``io`` readers.

``warnings.warn`` shows a warning only the first time it comes from a given line, so a file read twice in a
notebook would warn once and then stay silent. ``warn_every_time`` issues it through
``warnings.warn_explicit`` with no registry: it has no memory of earlier warnings, but still obeys filters, so
``warnings.simplefilter("error", SomeWarning)`` turns it into an error as usual.

DUPLICATE OF leodragkit/aero/repeated_warnings.py::warn_every_time: aero may import nothing from leodragkit
outside aero (D-04), and io may not import aero (D-03), so each keeps its own copy.
"""

import sys
import warnings


def warn_every_time(message: str, category: type[Warning], caller_depth: int) -> None:
    """Issue ``category`` with ``message``, attributed to the code ``caller_depth`` frames above the caller.

    ``caller_depth=1`` points at whoever called the function that calls this one: the user's line, for a
    reader that warns directly.
    """
    frame = sys._getframe(caller_depth + 1)
    warnings.warn_explicit(message, category, frame.f_code.co_filename, frame.f_lineno)
