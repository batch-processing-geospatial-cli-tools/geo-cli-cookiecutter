"""``{{ cookiecutter.command_name }} geometry`` — shapely-backed geometry operations.

shapely is optional and imported lazily so the base install stays free of a GEOS
dependency. Operations take and return WKT so the command composes with anything that
can write a text file.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from ..console import render_table
from ..errors import InputError, MissingDependencyError, ProcessingError

app = typer.Typer(help="Operate on WKT geometries.", no_args_is_help=True)


def _import_shapely() -> Any:
    """Import shapely, or raise an error that names the extra to install."""
    try:
        import shapely
    except ImportError as exc:
        raise MissingDependencyError("shapely", "geometry") from exc
    return shapely


def _read_wkt(value: str | None, path: Path | None) -> str:
    """Take the geometry from an argument or a file, insisting on exactly one source."""
    if (value is None) == (path is None):
        raise InputError("Give either a WKT argument or --from-file, not both or neither")
    if path is not None:
        try:
            return path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise InputError(f"Cannot read {path}: {exc}") from exc
    return (value or "").strip()


@app.command("describe")
def describe(
    ctx: typer.Context,
    wkt: Annotated[str | None, typer.Argument(help="Geometry in WKT.", show_default=False)] = None,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file", help="Read the WKT from a file.", dir_okay=False, show_default=False
        ),
    ] = None,
) -> None:
    """Report a geometry's type, validity, area, length and bounds."""
    from ..cli import get_context

    context = get_context(ctx)
    shapely = _import_shapely()
    source = _read_wkt(wkt, from_file)

    try:
        geometry = shapely.from_wkt(source)
    except Exception as exc:  # shapely raises GEOSException, not in our dependency surface
        raise ProcessingError(f"Not valid WKT: {exc}") from exc

    rows = [
        ("type", geometry.geom_type),
        ("valid", shapely.is_valid(geometry)),
        ("empty", geometry.is_empty),
        ("area", f"{geometry.area:.6f}"),
        ("length", f"{geometry.length:.6f}"),
        ("bounds", ", ".join(f"{value:.6f}" for value in geometry.bounds) or "(empty)"),
    ]
    context.console.print(render_table("Geometry", ("property", "value"), rows))


@app.command("buffer")
def buffer(
    ctx: typer.Context,
    wkt: Annotated[str | None, typer.Argument(help="Geometry in WKT.", show_default=False)] = None,
    distance: Annotated[float, typer.Option("--distance", "-d", help="Buffer distance.")] = 1.0,
    from_file: Annotated[
        Path | None,
        typer.Option(
            "--from-file", help="Read the WKT from a file.", dir_okay=False, show_default=False
        ),
    ] = None,
) -> None:
    """Buffer a geometry and print the result as WKT.

    The distance is in the units of the geometry's own CRS, which this command cannot
    know — buffering degrees by 1.0 is almost never what anyone means, so check your
    input is projected before trusting the output.
    """
    from ..cli import get_context

    context = get_context(ctx)
    shapely = _import_shapely()
    source = _read_wkt(wkt, from_file)

    try:
        geometry = shapely.from_wkt(source)
        result = shapely.buffer(geometry, distance)
    except Exception as exc:
        raise ProcessingError(f"Cannot buffer geometry: {exc}") from exc

    context.console.print(shapely.to_wkt(result, rounding_precision=context.settings.precision))
