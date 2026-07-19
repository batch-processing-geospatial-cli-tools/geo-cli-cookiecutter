from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from {{ cookiecutter.module_name }}.cli import app

SQUARE = "POLYGON ((0 0, 0 10, 10 10, 10 0, 0 0))"


def test_describe_reports_area_and_bounds(runner: CliRunner) -> None:
    result = runner.invoke(app, ["geometry", "describe", SQUARE])
    assert result.exit_code == 0
    assert "Polygon" in result.stdout
    assert "100.000000" in result.stdout


def test_describe_reads_from_a_file(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "geometry.wkt"
    path.write_text(SQUARE, encoding="utf-8")
    result = runner.invoke(app, ["geometry", "describe", "--from-file", str(path)])
    assert result.exit_code == 0
    assert "Polygon" in result.stdout


def test_describe_requires_exactly_one_source(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "geometry.wkt"
    path.write_text(SQUARE, encoding="utf-8")

    neither = runner.invoke(app, ["geometry", "describe"])
    assert neither.exit_code == 3

    both = runner.invoke(app, ["geometry", "describe", SQUARE, "--from-file", str(path)])
    assert both.exit_code == 3


def test_describe_rejects_malformed_wkt(runner: CliRunner) -> None:
    result = runner.invoke(app, ["geometry", "describe", "POLYGON (nonsense)"])
    assert result.exit_code == 4


def test_buffer_grows_the_geometry(runner: CliRunner) -> None:
    result = runner.invoke(app, ["geometry", "buffer", "POINT (0 0)", "--distance", "1"])
    assert result.exit_code == 0
    assert result.stdout.strip().startswith("POLYGON")


def test_buffer_reads_from_a_file(runner: CliRunner, tmp_path: Path) -> None:
    path = tmp_path / "geometry.wkt"
    path.write_text(SQUARE, encoding="utf-8")
    result = runner.invoke(app, ["geometry", "buffer", "--from-file", str(path), "-d", "0.5"])
    assert result.exit_code == 0
    assert "POLYGON" in result.stdout


def test_missing_file_is_reported(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["geometry", "describe", "--from-file", str(tmp_path / "absent.wkt")]
    )
    assert result.exit_code != 0
