from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import pytest
from typer.testing import CliRunner

from {{ cookiecutter.module_name }} import __version__
from {{ cookiecutter.module_name }}.cli import app


def output(result: Any) -> str:
    """Everything the run printed, whichever stream it used.

    Click 8.2 split ``stdout`` and ``stderr`` on ``Result``; older versions merge them
    and raise on ``.stderr``. Tests assert on content, not on stream plumbing, so they
    look at both.
    """
    text: str = result.stdout
    with contextlib.suppress(ValueError, AttributeError):
        text += result.stderr
    return text


def test_help_lists_every_command(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    for command in ("info", "convert", "batch"):
        assert command in result.stdout


def test_version_flag(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.stdout


def test_no_arguments_shows_help_and_exits_non_zero(runner: CliRunner) -> None:
    result = runner.invoke(app, [])
    assert result.exit_code != 0
    assert "Usage" in output(result)


def test_info_shows_defaults(runner: CliRunner) -> None:
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "target_epsg" in result.stdout
    assert "default" in result.stdout


def test_info_reports_the_source_of_an_overridden_value(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text("workers = 3\n", encoding="utf-8")
    result = runner.invoke(app, ["--config", str(config), "info"])
    assert result.exit_code == 0
    assert "settings.toml" in result.stdout


def test_cli_flag_beats_the_config_file(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text("target_epsg = 3857\n", encoding="utf-8")
    result = runner.invoke(app, ["--config", str(config), "--epsg", "27700", "info"])
    assert result.exit_code == 0
    assert "27700" in result.stdout


def test_info_environment_section_is_opt_in(runner: CliRunner) -> None:
    assert "executable" not in runner.invoke(app, ["info"]).stdout
    assert "executable" in runner.invoke(app, ["info", "--environment"]).stdout


def test_verbose_and_quiet_together_are_rejected(runner: CliRunner) -> None:
    result = runner.invoke(app, ["--verbose", "--quiet", "info"])
    assert result.exit_code != 0
    assert "cannot be combined" in output(result)


def test_quiet_suppresses_output(runner: CliRunner, points_csv: Path, tmp_path: Path) -> None:
    result = runner.invoke(
        app, ["--quiet", "convert", str(points_csv), "--out", str(tmp_path / "q.geojson")]
    )
    assert result.exit_code == 0
    assert result.stdout.strip() == ""
    assert (tmp_path / "q.geojson").is_file()


def test_missing_config_file_exits_with_the_config_code(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["--config", str(tmp_path / "absent.toml"), "info"])
    assert result.exit_code == 2


def test_invalid_config_exits_with_the_config_code(runner: CliRunner, tmp_path: Path) -> None:
    config = tmp_path / "settings.toml"
    config.write_text("target_epsg = 12\n", encoding="utf-8")
    result = runner.invoke(app, ["--config", str(config), "info"])
    assert result.exit_code == 2
    assert "EPSG" in output(result)


def test_convert_writes_geojson(runner: CliRunner, points_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "points.geojson"
    result = runner.invoke(app, ["convert", str(points_csv), "--out", str(destination)])
    assert result.exit_code == 0
    assert "3 features" in result.stdout
    assert json.loads(destination.read_text(encoding="utf-8"))["type"] == "FeatureCollection"


def test_convert_defaults_to_the_configured_output_dir(
    runner: CliRunner, points_csv: Path, tmp_path: Path
) -> None:
    out_dir = tmp_path / "generated"
    result = runner.invoke(app, ["--output-dir", str(out_dir), "convert", str(points_csv)])
    assert result.exit_code == 0
    assert (out_dir / "points.geojson").is_file()


def test_convert_reports_a_missing_input(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["convert", str(tmp_path / "absent.csv")])
    assert result.exit_code != 0


def test_convert_rejects_a_multi_character_delimiter(runner: CliRunner, points_csv: Path) -> None:
    result = runner.invoke(app, ["convert", str(points_csv), "--delimiter", "||"])
    assert result.exit_code != 0
    assert "single character" in output(result)


def test_convert_refuses_to_clobber(runner: CliRunner, points_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "points.geojson"
    destination.write_text("existing", encoding="utf-8")
    result = runner.invoke(app, ["convert", str(points_csv), "--out", str(destination)])
    assert result.exit_code == 4
    assert "already exists" in output(result)

    forced = runner.invoke(
        app, ["convert", str(points_csv), "--out", str(destination), "--overwrite"]
    )
    assert forced.exit_code == 0


def test_batch_converts_a_directory(runner: CliRunner, input_dir: Path, tmp_path: Path) -> None:
    result = runner.invoke(app, ["--output-dir", str(tmp_path / "out"), "batch", str(input_dir)])
    assert result.exit_code == 4  # one input in the fixture cannot be converted
    assert "3/4" in output(result)
    assert (tmp_path / "out" / "tile_0.geojson").is_file()


def test_batch_exits_zero_when_everything_converts(
    runner: CliRunner, input_dir: Path, tmp_path: Path
) -> None:
    (input_dir / "broken.csv").unlink()
    result = runner.invoke(app, ["--output-dir", str(tmp_path / "out"), "batch", str(input_dir)])
    assert result.exit_code == 0
    assert "3/3" in output(result)


def test_batch_json_report_is_parseable(runner: CliRunner, input_dir: Path, tmp_path: Path) -> None:
    (input_dir / "broken.csv").unlink()
    result = runner.invoke(
        app, ["--output-dir", str(tmp_path / "out"), "batch", str(input_dir), "--json"]
    )
    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["succeeded"] == 3
    assert payload["features"] == 9


def test_batch_with_no_matches_exits_non_zero(
    runner: CliRunner, input_dir: Path, tmp_path: Path
) -> None:
    result = runner.invoke(app, ["batch", str(input_dir), "--pattern", "*.shp"])
    assert result.exit_code == 1
    assert "no files matching" in output(result)


def test_batch_rejects_a_missing_directory(runner: CliRunner, tmp_path: Path) -> None:
    result = runner.invoke(app, ["batch", str(tmp_path / "absent")])
    assert result.exit_code != 0


@pytest.mark.parametrize("flag", ["--fail-fast", "--keep-going"])
def test_batch_accepts_both_failure_policies(
    runner: CliRunner, input_dir: Path, tmp_path: Path, flag: str
) -> None:
    result = runner.invoke(
        app, ["--output-dir", str(tmp_path / "out"), "batch", str(input_dir), flag]
    )
    assert result.exit_code == 4


def test_environment_variables_are_honoured(
    runner: CliRunner, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("{{ cookiecutter.module_name.upper() }}_TARGET_EPSG", "2154")
    result = runner.invoke(app, ["info"])
    assert result.exit_code == 0
    assert "2154" in result.stdout
