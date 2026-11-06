"""Warnings that Python never hides as repeats.

``warnings.warn`` shows a warning only the first time it comes from a given line, so a spacecraft rebuilt in
a notebook would warn once and then stay silent. ``warn_every_time`` issues the warning through
``warnings.warn_explicit`` with no registry: it has no memory of earlier warnings, but still obeys warning
filters, so ``warnings.simplefilter("error", SomeWarning)`` turns it into an error as usual.
"""

import sys
import warnings


def warn_every_time(message: str, category: type[Warning], caller_depth: int) -> None:
    """Issue ``category`` with ``message``, attributed to the code ``caller_depth`` frames above the caller.

    ``caller_depth=1`` points at whoever called the function that calls this one; use larger values to
    point further out, at the user's own line.
    """
    frame = sys._getframe(caller_depth + 1)
    warnings.warn_explicit(message, category, frame.f_code.co_filename, frame.f_lineno)
