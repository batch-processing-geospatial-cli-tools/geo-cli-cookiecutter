"""``{{ cookiecutter.command_name }} vector`` — pyogrio-backed vector commands.

pyogrio is optional and imported lazily, for the same reason as the raster extra: the
base install must stay usable without a GDAL stack. pyogrio is preferred over Fiona
here because it reads whole layers through GDAL's columnar API rather than
feature-by-feature in Python, which is what makes chunked reads of large files
practical — see
https://www.batch-processing.com/spatial-batch-processing-async-workflows/chunked-vector-data-reading/pyogrio-vs-fiona-for-large-vector-datasets/
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Any

import typer

from ..console import render_table
from ..errors import InputError, MissingDependencyError

app = typer.Typer(help="Inspect vector datasets.", no_args_is_help=True)


def _import_pyogrio() -> Any:
    """Import pyogrio, or raise an error that names the extra to install."""
    try:
        import pyogrio
        import pyogrio.errors
    except ImportError as exc:
        raise MissingDependencyError("pyogrio", "vector") from exc
    return pyogrio


@app.command("info")
def vector_info(
    ctx: typer.Context,
    path: Annotated[
        Path,
        typer.Argument(help="Vector file to inspect.", exists=True, readable=True),
    ],
    layer: Annotated[
        str | None,
        typer.Option(
            "--layer", "-l", help="Layer name, for multi-layer sources.", show_default=False
        ),
    ] = None,
) -> None:
    """Report the layer's geometry type, CRS, feature count and field names.

    Uses ``read_info``, which reads metadata only — no geometries are loaded, so this
    is safe to run against a multi-gigabyte GeoPackage.
    """
    from ..cli import get_context

    context = get_context(ctx)
    pyogrio = _import_pyogrio()

    try:
        info = pyogrio.read_info(path, layer=layer)
    except pyogrio.errors.DataSourceError as exc:
        raise InputError(f"Cannot read {path} as a vector dataset: {exc}") from exc
    except (OSError, ValueError) as exc:
        # A missing layer name comes back as a plain ValueError rather than a GDAL error.
        raise InputError(f"Cannot read {path}: {exc}") from exc

    fields = info.get("fields")
    rows: list[tuple[str, Any]] = [
        ("driver", info.get("driver", "(unknown)")),
        ("geometry", info.get("geometry_type", "(none)")),
        ("crs", info.get("crs") or "(undefined)"),
        ("features", info.get("features", 0)),
        ("fields", ", ".join(str(name) for name in fields) if fields is not None else "(none)"),
    ]
    context.console.print(render_table(str(path), ("property", "value"), rows))
