"""Command line for leodragkit: ``ldk <workflow>``.

Each command will be a few lines: parse arguments or a config file, call one function in
``leodragkit.workflows`` and save its result. No commands exist yet; they are added as
each workflow lands (task W1, ``docs/tasks.md``).
"""

import argparse
from collections.abc import Sequence


def build_argument_parser() -> argparse.ArgumentParser:
    """Return the parser for ``ldk``, with one subcommand per workflow (none yet)."""
    return argparse.ArgumentParser(prog="ldk", description="Satellite drag in low Earth orbit.")


def main(argv: Sequence[str] | None = None) -> int:
    """Run ``ldk`` with ``argv`` (default: the process arguments) and return the exit status.

    With no command it prints the help, since there are no commands yet.

    Example::

        $ ldk --help
    """
    parser = build_argument_parser()
    parser.parse_args(argv)
    parser.print_help()
    return 0
