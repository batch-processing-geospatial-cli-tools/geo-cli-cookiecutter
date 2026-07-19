from __future__ import annotations

from pathlib import Path

import pytest

from {{ cookiecutter.module_name }}.errors import InputError
from {{ cookiecutter.module_name }}.pipeline import (
    TaskOutcome,
    destination_for,
    discover_inputs,
    iter_reports,
    resolve_workers,
    run_batch,
)


def test_discovery_is_sorted_and_filtered(input_dir: Path) -> None:
    (input_dir / "notes.txt").write_text("ignore me", encoding="utf-8")
    found = discover_inputs(input_dir)
    assert [path.name for path in found] == [
        "broken.csv",
        "tile_0.csv",
        "tile_1.csv",
        "tile_2.csv",
    ]


def test_discovery_can_recurse(input_dir: Path) -> None:
    nested = input_dir / "deeper"
    nested.mkdir()
    (nested / "tile_9.csv").write_text("x,y\n1,2\n", encoding="utf-8")
    assert len(discover_inputs(input_dir)) == 4
    assert len(discover_inputs(input_dir, recursive=True)) == 5


def test_discovery_rejects_a_missing_directory(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="Input directory not found"):
        discover_inputs(tmp_path / "absent")


def test_destination_preserves_the_stem(tmp_path: Path) -> None:
    assert destination_for(Path("a/b/tile_1.csv"), tmp_path).name == "tile_1.geojson"


def test_worker_count_is_clamped_to_the_machine() -> None:
    assert resolve_workers(0) == 1
    assert resolve_workers(1) == 1
    assert resolve_workers(10_000) >= 1


def test_batch_reports_successes_and_failures(input_dir: Path, tmp_path: Path) -> None:
    report = run_batch(discover_inputs(input_dir), tmp_path / "out", epsg=4326)
    assert len(report.succeeded) == 3
    assert len(report.failed) == 1
    assert report.features == 9
    assert report.exit_code == 4
    assert report.failed[0].source.name == "broken.csv"
    assert not report.stopped_early


def test_batch_of_only_good_files_exits_zero(input_dir: Path, tmp_path: Path) -> None:
    (input_dir / "broken.csv").unlink()
    report = run_batch(discover_inputs(input_dir), tmp_path / "out", epsg=4326)
    assert report.exit_code == 0
    assert {path.name for path in (tmp_path / "out").iterdir()} == {
        "tile_0.geojson",
        "tile_1.geojson",
        "tile_2.geojson",
    }


def test_empty_batch_is_a_failure(tmp_path: Path) -> None:
    report = run_batch([], tmp_path / "out", epsg=4326)
    assert report.outcomes == []
    assert report.exit_code == 1


def test_fail_fast_stops_at_the_first_failure(input_dir: Path, tmp_path: Path) -> None:
    report = run_batch(discover_inputs(input_dir), tmp_path / "out", epsg=4326, fail_fast=True)
    assert report.stopped_early
    assert len(report.outcomes) == 1
    assert not report.outcomes[0].ok


def test_progress_callback_fires_once_per_file(input_dir: Path, tmp_path: Path) -> None:
    seen: list[TaskOutcome] = []
    report = run_batch(
        discover_inputs(input_dir), tmp_path / "out", epsg=4326, on_result=seen.append
    )
    assert len(seen) == len(report.outcomes) == 4


def test_parallel_run_matches_the_sequential_result(input_dir: Path, tmp_path: Path) -> None:
    sources = discover_inputs(input_dir)
    sequential = run_batch(sources, tmp_path / "seq", epsg=4326, workers=1)
    parallel = run_batch(sources, tmp_path / "par", epsg=4326, workers=2)
    assert parallel.features == sequential.features
    assert len(parallel.failed) == len(sequential.failed)


def test_report_rows_describe_each_outcome(input_dir: Path, tmp_path: Path) -> None:
    report = run_batch(discover_inputs(input_dir), tmp_path / "out", epsg=4326)
    rows = {name: status for name, status, _ in iter_reports(report)}
    assert rows["tile_0.csv"] == "ok"
    assert rows["broken.csv"] == "failed"
