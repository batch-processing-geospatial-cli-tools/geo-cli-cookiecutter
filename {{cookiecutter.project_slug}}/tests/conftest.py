"""Shared fixtures.

Every fixture writes into ``tmp_path``: the suite must never depend on files in the
repository, on the network, or on the developer's working directory.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

POINTS_CSV = """id,name,lon,lat
1,Alpha,-1.234567,51.987654
2,Beta,0.5,52.0
3,Gamma,2.25,48.5
"""

MESSY_CSV = """id,x,y
1,10.0,20.0
2,,20.0
3,not-a-number,20.0
4,11.5,21.5
"""


@pytest.fixture
def runner() -> CliRunner:
    """A Typer CliRunner for exercising the command surface end to end."""
    return CliRunner()


@pytest.fixture
def points_csv(tmp_path: Path) -> Path:
    """A small, entirely valid point file."""
    path = tmp_path / "points.csv"
    path.write_text(POINTS_CSV, encoding="utf-8")
    return path


@pytest.fixture
def messy_csv(tmp_path: Path) -> Path:
    """A point file with a blank and a non-numeric coordinate row."""
    path = tmp_path / "messy.csv"
    path.write_text(MESSY_CSV, encoding="utf-8")
    return path


@pytest.fixture
def input_dir(tmp_path: Path) -> Path:
    """A directory of three valid CSV files plus one that cannot be converted."""
    directory = tmp_path / "inputs"
    directory.mkdir()
    for index in range(3):
        (directory / f"tile_{index}.csv").write_text(POINTS_CSV, encoding="utf-8")
    (directory / "broken.csv").write_text("id,name\n1,no coordinates here\n", encoding="utf-8")
    return directory


@pytest.fixture(autouse=True)
def isolated_environment(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Stop the developer's own environment and config files leaking into a test.

    Without this, a ``{{ cookiecutter.command_name }}.toml`` in the checkout — or an exported
    ``{{ cookiecutter.module_name.upper() }}_*`` variable — would silently change what the tests assert.
    """
    for key in list(os.environ):
        if key.startswith("{{ cookiecutter.module_name.upper() }}_"):
            monkeypatch.delenv(key, raising=False)
    # Rich sizes a non-terminal console from COLUMNS. Pinning it wide keeps table cells
    # on one line so assertions can look for a value without guessing where it wrapped.
    monkeypatch.setenv("COLUMNS", "200")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.chdir(tmp_path)
