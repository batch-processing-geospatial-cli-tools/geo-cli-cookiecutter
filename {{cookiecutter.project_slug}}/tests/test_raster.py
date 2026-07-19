from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin
from typer.testing import CliRunner

from {{ cookiecutter.module_name }}.cli import app


@pytest.fixture
def geotiff(tmp_path: Path) -> Path:
    """A tiny two-band GeoTIFF generated on the fly.

    Written here rather than committed as a fixture file: a binary blob in the
    repository is one more thing to keep in step with the code, and this costs
    milliseconds.
    """
    path = tmp_path / "sample.tif"
    data = np.arange(64, dtype="uint8").reshape(8, 8)
    with rasterio.open(
        path,
        "w",
        driver="GTiff",
        height=8,
        width=8,
        count=2,
        dtype="uint8",
        crs="EPSG:3857",
        transform=from_origin(0.0, 80.0, 10.0, 10.0),
        nodata=0,
    ) as dataset:
        dataset.write(data, 1)
        dataset.write(data, 2)
    return path


def test_raster_info_reports_the_header(runner: CliRunner, geotiff: Path) -> None:
    result = runner.invoke(app, ["raster", "info", str(geotiff)])
    assert result.exit_code == 0
    assert "GTiff" in result.stdout
    assert "EPSG:3857" in result.stdout
    assert "8 x 8" in result.stdout


def test_raster_info_rejects_a_non_raster(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "not-a-raster.tif"
    path.write_text("plain text", encoding="utf-8")
    result = runner.invoke(app, ["raster", "info", str(path)])
    assert result.exit_code == 3


def test_raster_group_help(runner: CliRunner) -> None:
    result = runner.invoke(app, ["raster", "--help"])
    assert result.exit_code == 0
    assert "info" in result.stdout
