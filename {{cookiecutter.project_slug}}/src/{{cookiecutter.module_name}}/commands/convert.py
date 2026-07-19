"""``{{ cookiecutter.command_name }} convert`` — turn one delimited point file into GeoJSON."""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from ..conversion import convert_file
from ..pipeline import destination_for


def convert(
    ctx: typer.Context,
    source: Annotated[
        Path,
        typer.Argument(
            help="CSV file with x/longitude and y/latitude columns.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ],
    destination: Annotated[
        Path | None,
        typer.Option(
            "--out",
            help="Output path. Defaults to <output-dir>/<name>.geojson.",
            dir_okay=False,
            show_default=False,
        ),
    ] = None,
    delimiter: Annotated[
        str, typer.Option("--delimiter", "-d", help="Field delimiter in the source file.")
    ] = ",",
    overwrite: Annotated[
        bool | None,
        typer.Option("--overwrite/--no-overwrite", help="Replace an existing output file."),
    ] = None,
) -> None:
    """Convert a delimited point file into a GeoJSON FeatureCollection.

    Coordinates are written in the configured target CRS's axis order as they appear in
    the source; this command does not reproject. Rows with blank or non-numeric
    coordinates are counted and reported rather than failing the file.
    """
    from ..cli import get_context

    context = get_context(ctx)
    settings = context.settings

    if len(delimiter) != 1:
        raise typer.BadParameter("--delimiter must be a single character", param_hint="--delimiter")

    target = destination or destination_for(source, settings.output_dir)
    result = convert_file(
        source,
        target,
        epsg=settings.target_epsg,
        precision=settings.precision,
        overwrite=settings.overwrite if overwrite is None else overwrite,
        delimiter=delimiter,
    )

    context.console.print(
        f"wrote [bold]{result.destination}[/bold] "
        f"({result.features} features, {result.skipped} rows skipped, {settings.crs})"
    )
    if result.skipped and context.verbose:
        context.err_console.print(
            f"{result.skipped} of {result.total} rows had missing or non-numeric coordinates"
        )
