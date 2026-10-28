# Code tour

A reading guide to leodragkit, module by module, in the order to read them. Each entry says what the module does, where it sits in the workflows, and what to read first. Updated in the same step as the code (CLAUDE.md, "Documentation").

## Start here

1. `README.md`: what the package does and how it is used.
2. `CLAUDE.md`: the layout and the import order of the subpackages.
3. `docs/decisions.md`: why things are the way they are.

## Modules

Only the skeleton exists so far (task T-00):

- `leodragkit/__init__.py`: the package version. It imports no subpackage, so `import leodragkit` stays light.
- `leodragkit/cli.py`: the `ldk` command. It has no commands yet; one is added with each workflow.
- `leodragkit/<subpackage>/__init__.py`: one docstring each, saying what the subpackage will hold and what it may import.
- `tests/test_package.py`: the installation, the `ldk` command, and the import rules D-04 and D-05.
