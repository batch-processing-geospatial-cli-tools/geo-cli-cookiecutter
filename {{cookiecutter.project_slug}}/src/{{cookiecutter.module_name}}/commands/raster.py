"""``{{ cookiecutter.command_name }} raster`` — rasterio-backed inspection commands.

rasterio is an optional dependency. It is imported inside the command rather than at
module scope so that ``{{ cookiecutter.command_name }} --help`` and every other
subcommand keep working when only the base install is present; a missing wheel becomes
a one-line message naming the extra to install rather than an ImportError traceback.
That pattern is covered in
https://www.batch-processing.com/cli-architecture-design-patterns/click-vs-typer-for-geospatial-workflows/handling-missing-dependencies-gracefully-in-click-apps/
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from ..console import render_table
from ..errors import InputError, MissingDependencyError

app = typer.Typer(help="Inspect and summarise raster datasets.", no_args_is_help=True)


def _import_rasterio() -> Any:
    """Import rasterio, or raise an error that tells the user how to fix it."""
    try:
        import rasterio
    except ImportError as exc:
        raise MissingDependencyError("rasterio", "raster") from exc
    return rasterio


@app.command("info")
def raster_info(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Argument(help="Raster file to inspect.", exists=True, dir_okay=False, readable=True),
    ],
) -> None:
    """Print the CRS, size, band count and bounds of a raster.

    Only the dataset header is read: opening a 40 GB mosaic to report its shape should
    cost the same as opening a 40 KB one.
    """
    from ..cli import get_context

    context = get_context(ctx)
    rasterio = _import_rasterio()

    try:
        with rasterio.open(path) as dataset:
            rows: list[tuple[str, Any]] = [
                ("driver", dataset.driver),
                ("crs", dataset.crs or "(undefined)"),
                ("size", f"{dataset.width} x {dataset.height}"),
                ("bands", dataset.count),
                ("dtypes", ", ".join(dataset.dtypes)),
                ("nodata", dataset.nodata if dataset.nodata is not None else "(none)"),
                ("bounds", ", ".join(f"{value:.6f}" for value in dataset.bounds)),
                ("resolution", ", ".join(f"{value:g}" for value in dataset.res)),
            ]
    except OSError as exc:
        # rasterio.errors.RasterioIOError derives from OSError, so this catches both a
        # GDAL open failure and an ordinary permissions problem with one message.
        raise InputError(f"Cannot open {path} as a raster: {exc}") from exc

    context.console.print(render_table(str(path), ("property", "value"), rows))
