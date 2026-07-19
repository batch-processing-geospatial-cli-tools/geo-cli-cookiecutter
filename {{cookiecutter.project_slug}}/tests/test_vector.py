from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from {{ cookiecutter.module_name }}.cli import app

FEATURES = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [1.0, 2.0]},
            "properties": {"name": "Alpha", "score": 3},
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [3.0, 4.0]},
            "properties": {"name": "Beta", "score": 5},
        },
    ],
}


@pytest.fixture
def geojson(tmp_path: Path) -> Path:
    """A two-feature GeoJSON file, written as text so no writer dependency is needed."""
    path = tmp_path / "sample.geojson"
    path.write_text(json.dumps(FEATURES), encoding="utf-8")
    return path


def test_vector_info_reports_the_layer(runner: CliRunner, geojson: Path) -> None:
    result = runner.invoke(app, ["vector", "info", str(geojson)])
    assert result.exit_code == 0
    assert "Point" in result.stdout
    assert "name" in result.stdout
    assert "2" in result.stdout


def test_vector_info_rejects_an_unreadable_source(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "broken.geojson"
    path.write_text("this is not geojson", encoding="utf-8")
    result = runner.invoke(app, ["vector", "info", str(path)])
    assert result.exit_code == 3


def test_vector_group_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["vector", "--help"])
    assert result.exit_code == 0
    assert "info" in result.stdout
