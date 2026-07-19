"""Typer application: global options, subcommand wiring, and the error boundary.

Global options live on a callback rather than being repeated on each command, so
``--verbose`` works the same everywhere and the resolved settings are built exactly
once per invocation and handed down through a context object. The pattern is described
in
https://www.batch-processing.com/cli-architecture-design-patterns/cli-subcommand-organization/sharing-global-options-across-geospatial-subcommands/

This module is also the only place that decides exit statuses. :class:`ToolErrorGroup`
catches :class:`~{{ cookiecutter.module_name }}.errors.ToolError`, prints one clear
line to stderr and converts it into a Click exit with the code the error carries.
Putting the boundary in the group rather than in ``main()`` means the same behaviour
applies under ``CliRunner``, so tests assert on real exit codes. Command bodies just
raise, and stay usable as ordinary functions.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Annotated, Any

import typer
from rich.console import Console
from typer.core import TyperGroup

from . import __version__
from .commands import batch as batch_command
from .commands import convert as convert_command
{%- if cookiecutter.use_shapely == 'yes' %}
from .commands import geometry as geometry_command
{%- endif %}
from .commands import info as info_command
{%- if cookiecutter.use_rasterio == 'yes' %}
from .commands import raster as raster_command
{%- endif %}
{%- if cookiecutter.use_pyogrio == 'yes' %}
from .commands import vector as vector_command
{%- endif %}
from .config import LoadedSettings, Settings, load_settings
from .console import make_console
from .errors import ToolError


@dataclass
class AppContext:
    """Everything a command needs, resolved once by the root callback.

    Passed on ``typer.Context.obj``. Two consoles rather than one: data goes to stdout
    so it can be redirected, diagnostics and progress go to stderr so redirection stays
    clean.
    """

    loaded: LoadedSettings
    console: Console
    err_console: Console
    verbose: bool = False
    quiet: bool = False

    @property
    def settings(self) -> Settings:
        """The validated settings for this run."""
        return self.loaded.settings


class ToolErrorGroup(TyperGroup):
    """Command group that turns a :class:`ToolError` into a clean exit.

    Click already has an exception type for this (``ClickException``), but making the
    library layer depend on Click just to report an error would be the wrong direction
    of dependency. Translating at the boundary keeps ``errors.py`` free of CLI concerns
    while still producing ``error: ...`` on stderr and a meaningful status code.

    The exit is a plain ``SystemExit`` rather than ``click.exceptions.Exit`` on purpose:
    recent Typer releases vendor their own copy of Click, so an ``Exit`` built from the
    top-level ``click`` package is a different class from the one Typer's own runner
    catches, and it would escape as an unhandled exception with a useless status of 1.
    ``SystemExit`` means the same thing to Python, Click, Typer and ``CliRunner`` alike.
    """

    def invoke(self, ctx: Any) -> Any:
        """Run the selected command, reporting expected failures instead of raising.

        ``ctx`` is deliberately untyped: whether it is ``click.Context`` or Typer's
        vendored equivalent depends on the installed Typer version.
        """
        try:
            return super().invoke(ctx)
        except ToolError as exc:
            make_console(stderr=True).print(f"[bold red]error:[/bold red] {exc}")
            raise SystemExit(exc.exit_code) from exc


app = typer.Typer(
    cls=ToolErrorGroup,
    name="{{ cookiecutter.command_name }}",
    help="{{ cookiecutter.project_description }}",
    no_args_is_help=True,
    add_completion=True,
    rich_markup_mode="rich",
    context_settings={"help_option_names": ["-h", "--help"]},
)

app.command(name="info")(info_command.info)
app.command(name="convert")(convert_command.convert)
app.command(name="batch")(batch_command.batch)
{%- if cookiecutter.use_rasterio == 'yes' %}
app.add_typer(raster_command.app, name="raster")
{%- endif %}
{%- if cookiecutter.use_pyogrio == 'yes' %}
app.add_typer(vector_command.app, name="vector")
{%- endif %}
{%- if cookiecutter.use_shapely == 'yes' %}
app.add_typer(geometry_command.app, name="geometry")
{%- endif %}


def _version_callback(value: bool) -> None:
    """Print the version and exit, before any other option is processed."""
    if value:
        typer.echo(f"{{ cookiecutter.command_name }} {__version__}")
        raise typer.Exit()


@app.callback()
def main_callback(
    ctx: typer.Context,
    config: Annotated[
        Path | None,
        typer.Option(
            "--config",
            "-c",
            help="TOML configuration file. Overrides discovery.",
            envvar="{{ cookiecutter.module_name.upper() }}_CONFIG",
            dir_okay=False,
        ),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Show detailed diagnostics on stderr.")
    ] = False,
    quiet: Annotated[
        bool, typer.Option("--quiet", "-q", help="Suppress all non-error output.")
    ] = False,
    epsg: Annotated[
        int | None, typer.Option("--epsg", help="Target CRS as an EPSG code.", show_default=False)
    ] = None,
    output_dir: Annotated[
        Path | None,
        typer.Option("--output-dir", "-o", help="Directory for generated files.", file_okay=False),
    ] = None,
    _version: Annotated[
        bool,
        typer.Option(
            "--version",
            help="Show the version and exit.",
            callback=_version_callback,
            is_eager=True,
        ),
    ] = False,
) -> None:
    """Resolve configuration and build the context every subcommand shares."""
    if verbose and quiet:
        raise typer.BadParameter("--verbose and --quiet cannot be combined")

    overrides: dict[str, Any] = {"target_epsg": epsg, "output_dir": output_dir}
    if verbose:
        overrides["log_level"] = "debug"
    elif quiet:
        overrides["log_level"] = "error"

    loaded = load_settings(config, overrides)
    ctx.obj = AppContext(
        loaded=loaded,
        console=make_console(quiet=quiet),
        err_console=make_console(quiet=quiet, stderr=True),
        verbose=verbose,
        quiet=quiet,
    )


def get_context(ctx: typer.Context) -> AppContext:
    """Fetch the shared context, building a default one if the callback was bypassed.

    Typer's ``CliRunner`` can invoke a command function directly in a test; falling back
    to defaults keeps that path working rather than raising an ``AttributeError`` that
    tells the reader nothing.
    """
    if isinstance(ctx.obj, AppContext):
        return ctx.obj
    context = AppContext(
        loaded=load_settings(),
        console=make_console(),
        err_console=make_console(stderr=True),
    )
    ctx.obj = context
    return context


def main() -> int:
    """Console-script entry point.

    Only two things are left for this layer: report a Ctrl-C as the conventional 130
    rather than a traceback, and let anything genuinely unexpected keep its traceback —
    a crash we did not anticipate is a bug report, and hiding it helps nobody.
    """
    try:
        app()
    except KeyboardInterrupt:
        make_console(stderr=True).print("[yellow]interrupted[/yellow]")
        return 130
    return 0


if __name__ == "__main__":  # pragma: no cover - exercised via the console script
    raise SystemExit(main())
