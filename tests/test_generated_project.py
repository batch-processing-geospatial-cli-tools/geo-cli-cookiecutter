"""End-to-end check: bake a project, install it for real, and run its own quality gates.

Everything else in this suite inspects text. This test is the only one that proves the
template produces software that works — that the package imports, the console script is
registered, the generated tests pass, and the generated ruff and mypy configuration is
satisfied by the generated code. It is marked ``slow`` and pinned to one permutation
(all extras on, which exercises every file the template can emit) so CI stays quick.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from .conftest import bake

pytestmark = pytest.mark.slow

UV = shutil.which("uv")


def run(command: list[str], cwd: Path, env: dict[str, str] | None = None) -> str:
    """Run a command, failing the test with its full output if it exits non-zero."""
    process = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        capture_output=True,
        text=True,
        timeout=1800,
        check=False,
    )
    if process.returncode != 0:
        pytest.fail(
            f"{' '.join(command)} exited {process.returncode}\n"
            f"--- stdout ---\n{process.stdout}\n--- stderr ---\n{process.stderr}"
        )
    return process.stdout


@pytest.fixture(scope="module")
def installed_project(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Bake a fully featured project into an isolated venv and return its directory.

    Module-scoped: creating the environment is the expensive part, and every assertion
    below wants the same one.
    """
    if UV is None:  # pragma: no cover - uv is a documented prerequisite
        pytest.skip("uv is not installed")

    project = bake(
        tmp_path_factory.mktemp("baked"),
        project_name="Terrain Ops",
        command_name="terra",
        use_rasterio="yes",
        use_pyogrio="yes",
        use_shapely="yes",
    )

    # Strip the variables that would otherwise redirect uv somewhere else: CI sets
    # UV_PYTHON to steer the matrix, and this test needs its own environment.
    env = dict(os.environ)
    for name in ("UV_PYTHON", "VIRTUAL_ENV", "PYTHONPATH", "UV_PROJECT_ENVIRONMENT"):
        env.pop(name, None)

    venv = project / ".venv"
    interpreter = f"{sys.version_info.major}.{sys.version_info.minor}"
    run([UV, "venv", "--python", interpreter, str(venv)], project, env)
    run(
        [UV, "pip", "install", "--python", str(venv / "bin" / "python"), "-e", ".[dev]"],
        project,
        env,
    )
    return project


def binary(project: Path, name: str) -> str:
    """Absolute path to an executable inside the generated project's venv."""
    path = project / ".venv" / "bin" / name
    assert path.is_file(), f"{name} was not installed into the generated venv"
    return str(path)


def test_console_script_is_installed_and_reports_help(installed_project: Path) -> None:
    output = run([binary(installed_project, "terra"), "--help"], installed_project)
    assert "convert" in output
    assert "batch" in output
    assert "raster" in output


def test_generated_suite_passes(installed_project: Path) -> None:
    output = run(
        [binary(installed_project, "python"), "-m", "pytest", "-q", "--no-header"],
        installed_project,
    )
    assert "failed" not in output.splitlines()[-1]


def test_generated_code_is_lint_clean(installed_project: Path) -> None:
    run([binary(installed_project, "ruff"), "check", "."], installed_project)
    run([binary(installed_project, "ruff"), "format", "--check", "."], installed_project)


def test_generated_code_type_checks(installed_project: Path) -> None:
    run([binary(installed_project, "mypy")], installed_project)


def test_the_tool_actually_converts_a_file(installed_project: Path, tmp_path: Path) -> None:
    source = tmp_path / "sites.csv"
    source.write_text("id,lon,lat\n1,1.5,52.5\n2,2.5,53.5\n", encoding="utf-8")
    destination = tmp_path / "sites.geojson"
    run(
        [binary(installed_project, "terra"), "convert", str(source), "--out", str(destination)],
        installed_project,
    )
    assert '"FeatureCollection"' in destination.read_text(encoding="utf-8")
