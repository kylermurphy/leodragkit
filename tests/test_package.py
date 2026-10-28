"""Tests for the package skeleton: installation, the ``ldk`` command, and the import rules.

The import tests run in a fresh interpreter, so modules imported by other tests cannot hide a
violation of D-04 (aero stays light) or D-05 (no JVM on import).

Run: ``pytest tests/test_package.py``
"""

import shutil
import subprocess
import sys

import leodragkit

# Dependencies that aero must never load (D-04) and that ``import leodragkit`` must not start (D-05).
HEAVY_DEPENDENCIES = {"jpype", "orekit_jpype", "pymsis", "pandas", "requests"}


def modules_loaded_by_import(module_name: str) -> set[str]:
    """Return the names in ``sys.modules`` after importing ``module_name`` in a fresh interpreter."""
    code = f"import sys, {module_name}; print('\\n'.join(sorted(sys.modules)))"
    completed = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    return set(completed.stdout.split())


def top_level_names(module_names: set[str]) -> set[str]:
    """Return the top-level package of each module name (``jpype.imports`` -> ``jpype``)."""
    return {name.split(".")[0] for name in module_names}


def test_package_reports_its_installed_version():
    assert isinstance(leodragkit.__version__, str) and leodragkit.__version__


def test_ldk_help_exits_with_status_zero():
    ldk_path = shutil.which("ldk")
    assert ldk_path is not None, "ldk is not on PATH: run `pip install -e .` in the active environment"
    completed = subprocess.run([ldk_path, "--help"], capture_output=True, text=True)
    assert completed.returncode == 0
    assert "usage: ldk" in completed.stdout


def test_importing_leodragkit_does_not_start_the_jvm():
    loaded = top_level_names(modules_loaded_by_import("leodragkit"))
    assert loaded.isdisjoint(HEAVY_DEPENDENCIES), loaded & HEAVY_DEPENDENCIES


def test_aero_loads_no_heavy_dependency_and_no_other_leodragkit_subpackage():
    loaded = modules_loaded_by_import("leodragkit.aero")
    assert top_level_names(loaded).isdisjoint(HEAVY_DEPENDENCIES), top_level_names(loaded) & HEAVY_DEPENDENCIES
    other_leodragkit_modules = {
        name for name in loaded
        if name.startswith("leodragkit.") and not name.startswith("leodragkit.aero")
    }
    assert other_leodragkit_modules == set(), other_leodragkit_modules
