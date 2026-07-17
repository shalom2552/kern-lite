"""
Tests for tests/Makefile: the run/run-host/run-py target split.

Host C++ suites and the Python pytest suite used to be interleaved under a
single `run` recipe. They are now split into `run-host` (host C++ binaries
only) and `run-py` (pytest only), with `run` depending on both -- so either
suite can be invoked independently while `make -C tests run` still runs
everything, matching the CI workflow.

file: tests/gs/test_makefile.py
author: Smallejoo
date: 2026-07-17
"""
from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

MAKEFILE_PATH = Path(__file__).resolve().parent.parent / "Makefile"


@pytest.fixture(scope="module")
def makefile_text() -> str:
    return MAKEFILE_PATH.read_text()


def _target_block(text: str, name: str) -> tuple[str, str]:
    """Return (prerequisites, recipe) for a `name:` target in a Makefile.

    The recipe is the block of tab-indented lines immediately following the
    target line, stopping at the first non-indented / blank line.
    """
    match = re.search(rf"(?m)^{re.escape(name)}:(.*)\n((?:\t.*\n?)*)", text)
    assert match is not None, f"target {name!r} not found in Makefile"
    prereqs = match.group(1).strip()
    recipe = match.group(2)
    return prereqs, recipe


def test_makefile_exists():
    assert MAKEFILE_PATH.is_file()


def test_run_host_target_depends_on_all(makefile_text):
    prereqs, _recipe = _target_block(makefile_text, "run-host")
    assert prereqs == "all"


def test_run_host_recipe_iterates_over_host_binaries_only(makefile_text):
    _prereqs, recipe = _target_block(makefile_text, "run-host")
    assert "$(TRG)" in recipe
    assert "./$$exe" in recipe
    # run-host must not shell out to pytest.
    assert "$(PYTEST)" not in recipe
    assert "pytest" not in recipe


def test_run_py_target_depends_on_venv(makefile_text):
    prereqs, _recipe = _target_block(makefile_text, "run-py")
    assert prereqs == "$(VENV)"


def test_run_py_recipe_invokes_pytest_with_expected_env(makefile_text):
    _prereqs, recipe = _target_block(makefile_text, "run-py")
    assert "PYTHONPATH=$(PYTHONPATH)" in recipe
    assert "$(PYTEST) gs/ -v" in recipe
    # run-py must not build or execute the host C++ binaries.
    assert "$(TRG)" not in recipe
    assert "./$$exe" not in recipe


def test_run_target_depends_on_run_host_and_run_py(makefile_text):
    prereqs, recipe = _target_block(makefile_text, "run")
    assert prereqs == "run-host run-py"
    # `run` is a pure aggregate target: no recipe of its own.
    assert recipe.strip() == ""


def test_phony_declares_all_run_targets(makefile_text):
    phony_match = re.search(r"(?m)^\.PHONY:\s*(.*)$", makefile_text)
    assert phony_match is not None
    phony_targets = phony_match.group(1).split()
    for target in ("all", "run", "run-host", "run-py", "clean"):
        assert target in phony_targets


def test_run_host_and_run_py_are_distinct_targets(makefile_text):
    # Regression guard: the split must produce two independently
    # invokable targets, not a single target aliased twice.
    assert makefile_text.count("run-host:") == 1
    assert makefile_text.count("run-py:") == 1
    assert re.search(r"(?m)^run:\s*run-host run-py\s*$", makefile_text)


@pytest.mark.skipif(shutil.which("make") is None, reason="make not available")
class TestMakeDryRun:
    """Exercise the real Makefile via `make -n` (dry run, no execution)."""

    def _dry_run(self, target: str) -> str:
        result = subprocess.run(
            ["make", "-C", str(MAKEFILE_PATH.parent), "-n", target],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout

    def test_run_host_dry_run_skips_pytest(self):
        output = self._dry_run("run-host")
        assert "pytest" not in output

    def test_run_py_dry_run_invokes_pytest(self):
        output = self._dry_run("run-py")
        assert "pytest" in output

    def test_run_dry_run_covers_both_suites(self):
        output = self._dry_run("run")
        assert "pytest" in output
        assert "./$exe" in output or "for exe in" in output