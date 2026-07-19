"""Dependency-free CSV-to-GeoJSON conversion — the worked example this template ships.

The point of having real logic here rather than a stub is that the generated project's
tests, batch runner and error handling all have something honest to exercise from the
first commit. It reads a delimited file of point coordinates and writes a GeoJSON
``FeatureCollection``, using only the standard library, so a freshly generated project
runs on any machine with Python and no GDAL at all.

Everything is a plain function taking and returning ordinary values: the batch command
runs these in a process pool, and that only works if nothing here holds a console, a
file handle or any other unpicklable state.
"""

from __future__ import annotations

import csv
import json
import math
from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .errors import InputError, ProcessingError

# Column names accepted for each axis, in order of preference. Real-world exports are
# inconsistent enough that guessing from a small allow-list saves more time than it costs.
X_ALIASES: tuple[str, ...] = ("x", "lon", "long", "longitude", "easting")
Y_ALIASES: tuple[str, ...] = ("y", "lat", "latitude", "northing")


@dataclass(frozen=True)
class ConversionResult:
    """What a single file conversion produced.

    Carries counts rather than the features themselves: a batch run may convert
    thousands of files, and holding every geometry in memory to report a total is the
    quickest way to turn a working pipeline into an out-of-memory crash.
    """

    source: Path
    destination: Path
    features: int
    skipped: int

    @property
    def total(self) -> int:
        """Rows read, whether or not they yielded a feature."""
        return self.features + self.skipped


def _resolve_column(header: Sequence[str], aliases: Sequence[str], axis: str) -> str:
    """Pick the column holding one axis, matching case-insensitively.

    Raises:
        InputError: No candidate column is present. The message lists what was actually
            in the header, which is the information needed to fix the file.
    """
    lookup = {name.strip().lower(): name for name in header}
    for alias in aliases:
        if alias in lookup:
            return lookup[alias]
    raise InputError(
        f"No {axis} column found: expected one of {', '.join(aliases)}, "
        f"got {', '.join(header) if header else '(empty header)'}"
    )


def _round_coordinate(value: float, precision: int) -> float:
    """Round to ``precision`` decimals, keeping the result JSON-serialisable.

    Guards against NaN and infinity, which ``json.dump`` will happily emit as bare
    ``NaN`` — valid JavaScript, invalid JSON, and rejected by most GeoJSON readers.
    """
    if not math.isfinite(value):
        raise ProcessingError(f"Coordinate {value} is not a finite number")
    return round(value, precision)


@dataclass(frozen=True)
class ParsedRow:
    """One data row of the source file, parsed or rejected.

    A rejected row keeps its line number and reason instead of vanishing, so a caller
    can log exactly which records were dropped — a batch job that reports "412 skipped"
    with no way to find them is not much of a report.
    """

    line: int
    attributes: dict[str, str]
    point: tuple[float, float] | None = None
    reason: str | None = None

    @property
    def ok(self) -> bool:
        """Whether this row yielded usable coordinates."""
        return self.point is not None


def read_points(source: Path, *, delimiter: str = ",") -> Iterator[ParsedRow]:
    """Yield one :class:`ParsedRow` per data row of ``source``.

    Rows whose coordinates are blank or non-numeric are reported as rejected rather
    than raised on: a single malformed row in a 10-million-row export should not lose
    the other 9,999,999. Callers decide whether the skip count is acceptable.

    Raises:
        InputError: The file is missing, unreadable, empty, or lacks coordinate columns.
    """
    if not source.is_file():
        raise InputError(f"Input file not found: {source}")

    try:
        handle = source.open("r", encoding="utf-8-sig", newline="")
    except OSError as exc:
        raise InputError(f"Cannot read {source}: {exc}") from exc

    with handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        header = reader.fieldnames or []
        if not header:
            raise InputError(f"{source} is empty or has no header row")
        x_column = _resolve_column(header, X_ALIASES, "x/longitude")
        y_column = _resolve_column(header, Y_ALIASES, "y/latitude")

        for line_number, row in enumerate(reader, start=2):
            attributes = {
                key: value
                for key, value in row.items()
                if key not in (x_column, y_column) and key is not None and value is not None
            }
            raw_x, raw_y = row.get(x_column), row.get(y_column)
            if raw_x is None or raw_y is None or not raw_x.strip() or not raw_y.strip():
                yield ParsedRow(
                    line=line_number, attributes=attributes, reason="missing coordinates"
                )
                continue
            try:
                point = (float(raw_x), float(raw_y))
            except ValueError:
                yield ParsedRow(
                    line=line_number,
                    attributes=attributes,
                    reason=f"non-numeric coordinates ({raw_x!r}, {raw_y!r})",
                )
                continue
            yield ParsedRow(line=line_number, attributes=attributes, point=point)


def build_feature_collection(
    source: Path,
    *,
    epsg: int,
    precision: int = 6,
    delimiter: str = ",",
) -> tuple[dict[str, Any], int]:
    """Build a GeoJSON ``FeatureCollection`` from a delimited point file.

    Returns:
        The collection and the number of rows skipped as unparseable.

    Note:
        A non-4326 ``epsg`` is recorded in a ``crs`` member. RFC 7946 removed ``crs``
        and mandates WGS 84, but tools that write projected GeoJSON do still emit it,
        and dropping the information silently is worse than emitting a legacy member.
    """
    features: list[dict[str, Any]] = []
    skipped = 0

    for row in read_points(source, delimiter=delimiter):
        if row.point is None:
            skipped += 1
            continue
        x, y = row.point
        try:
            coordinates = [_round_coordinate(x, precision), _round_coordinate(y, precision)]
        except ProcessingError as exc:
            raise ProcessingError(f"{source}:{row.line}: {exc}") from exc
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": coordinates},
                "properties": row.attributes,
            }
        )

    collection: dict[str, Any] = {"type": "FeatureCollection", "features": features}
    if epsg != 4326:
        collection["crs"] = {
            "type": "name",
            "properties": {"name": f"urn:ogc:def:crs:EPSG::{epsg}"},
        }
    return collection, skipped


def convert_file(
    source: Path,
    destination: Path,
    *,
    epsg: int,
    precision: int = 6,
    overwrite: bool = False,
    delimiter: str = ",",
) -> ConversionResult:
    """Convert one delimited point file to GeoJSON on disk.

    The write goes to a temporary sibling and is then renamed, so an interrupted run
    leaves either the previous file or nothing — never a half-written GeoJSON that a
    downstream job will happily try to parse.

    Raises:
        InputError: The source is unusable.
        ProcessingError: The destination exists without ``overwrite``, or writing failed.
    """
    if destination.exists() and not overwrite:
        raise ProcessingError(f"{destination} already exists; pass --overwrite to replace it")

    collection, skipped = build_feature_collection(
        source, epsg=epsg, precision=precision, delimiter=delimiter
    )

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        temporary = destination.with_name(destination.name + ".partial")
        with temporary.open("w", encoding="utf-8") as handle:
            json.dump(collection, handle, allow_nan=False)
            handle.write("\n")
        temporary.replace(destination)
    except OSError as exc:
        raise ProcessingError(f"Cannot write {destination}: {exc}") from exc

    return ConversionResult(
        source=source,
        destination=destination,
        features=len(collection["features"]),
        skipped=skipped,
    )
