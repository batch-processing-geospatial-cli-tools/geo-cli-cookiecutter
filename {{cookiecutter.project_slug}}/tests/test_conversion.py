from __future__ import annotations

import json
from pathlib import Path

import pytest

from {{ cookiecutter.module_name }}.conversion import (
    build_feature_collection,
    convert_file,
    read_points,
)
from {{ cookiecutter.module_name }}.errors import InputError, ProcessingError


def test_reads_lon_lat_aliases(points_csv: Path) -> None:
    rows = list(read_points(points_csv))
    assert [row.ok for row in rows] == [True, True, True]
    assert rows[0].point == pytest.approx((-1.234567, 51.987654))
    assert rows[0].attributes == {"id": "1", "name": "Alpha"}


@pytest.mark.parametrize(
    ("header", "expected"),
    [
        ("x,y", (1.0, 2.0)),
        ("X,Y", (1.0, 2.0)),
        ("easting,northing", (1.0, 2.0)),
        ("longitude,latitude", (1.0, 2.0)),
    ],
)
def test_column_aliases_are_matched_case_insensitively(
    tmp_path: Path, header: str, expected: tuple[float, float]
) -> None:
    source = tmp_path / "aliases.csv"
    source.write_text(f"{header}\n1.0,2.0\n", encoding="utf-8")
    rows = list(read_points(source))
    assert rows[0].point == pytest.approx(expected)


def test_missing_coordinate_column_names_what_was_found(tmp_path: Path) -> None:
    source = tmp_path / "bad.csv"
    source.write_text("id,name\n1,Alpha\n", encoding="utf-8")
    with pytest.raises(InputError, match=r"No x/longitude column.*got id, name"):
        list(read_points(source))


def test_missing_y_column_is_reported_separately(tmp_path: Path) -> None:
    source = tmp_path / "x-only.csv"
    source.write_text("id,lon\n1,1.5\n", encoding="utf-8")
    with pytest.raises(InputError, match="No y/latitude column"):
        list(read_points(source))


def test_missing_file_is_an_input_error(tmp_path: Path) -> None:
    with pytest.raises(InputError, match="not found"):
        list(read_points(tmp_path / "absent.csv"))


def test_empty_file_is_an_input_error(tmp_path: Path) -> None:
    source = tmp_path / "empty.csv"
    source.write_text("", encoding="utf-8")
    with pytest.raises(InputError, match="empty or has no header"):
        list(read_points(source))


def test_bad_rows_are_reported_not_raised(messy_csv: Path) -> None:
    rows = list(read_points(messy_csv))
    assert [row.ok for row in rows] == [True, False, False, True]
    assert rows[1].reason == "missing coordinates"
    assert rows[2].reason is not None and "non-numeric" in rows[2].reason


def test_feature_collection_shape_and_skip_count(messy_csv: Path) -> None:
    collection, skipped = build_feature_collection(messy_csv, epsg=4326)
    assert collection["type"] == "FeatureCollection"
    assert skipped == 2
    assert len(collection["features"]) == 2
    assert collection["features"][0]["geometry"] == {"type": "Point", "coordinates": [10.0, 20.0]}
    assert "crs" not in collection


def test_projected_output_records_a_crs_member(points_csv: Path) -> None:
    collection, _ = build_feature_collection(points_csv, epsg=27700)
    assert collection["crs"]["properties"]["name"] == "urn:ogc:def:crs:EPSG::27700"


def test_precision_is_applied_to_coordinates(points_csv: Path) -> None:
    collection, _ = build_feature_collection(points_csv, epsg=4326, precision=2)
    assert collection["features"][0]["geometry"]["coordinates"] == [-1.23, 51.99]


def test_non_finite_coordinates_are_rejected(tmp_path: Path) -> None:
    source = tmp_path / "inf.csv"
    source.write_text("x,y\ninf,1.0\n", encoding="utf-8")
    with pytest.raises(ProcessingError, match="not a finite number"):
        build_feature_collection(source, epsg=4326)


def test_alternative_delimiter(tmp_path: Path) -> None:
    source = tmp_path / "semi.csv"
    source.write_text("x;y\n3.0;4.0\n", encoding="utf-8")
    collection, _ = build_feature_collection(source, epsg=4326, delimiter=";")
    assert collection["features"][0]["geometry"]["coordinates"] == [3.0, 4.0]


def test_convert_file_writes_valid_json(points_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "out" / "points.geojson"
    result = convert_file(points_csv, destination, epsg=4326)
    assert result.features == 3
    assert result.total == 3
    payload = json.loads(destination.read_text(encoding="utf-8"))
    assert len(payload["features"]) == 3


def test_convert_file_refuses_to_clobber_by_default(points_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "points.geojson"
    destination.write_text("existing", encoding="utf-8")
    with pytest.raises(ProcessingError, match="already exists"):
        convert_file(points_csv, destination, epsg=4326)
    assert destination.read_text(encoding="utf-8") == "existing"


def test_convert_file_overwrites_when_asked(points_csv: Path, tmp_path: Path) -> None:
    destination = tmp_path / "points.geojson"
    destination.write_text("existing", encoding="utf-8")
    convert_file(points_csv, destination, epsg=4326, overwrite=True)
    assert json.loads(destination.read_text(encoding="utf-8"))["type"] == "FeatureCollection"


def test_failed_write_leaves_no_partial_file(points_csv: Path, tmp_path: Path) -> None:
    blocker = tmp_path / "blocked"
    blocker.write_text("not a directory", encoding="utf-8")
    with pytest.raises(ProcessingError, match="Cannot write"):
        convert_file(points_csv, blocker / "out.geojson", epsg=4326)
    assert blocker.read_text(encoding="utf-8") == "not a directory"
