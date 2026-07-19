"""``{{ cookiecutter.command_name }} info`` — show the resolved configuration and where each value came from.

This is the command users reach for when the tool "ignored" their config file. Showing
the provenance of each setting alongside its value answers that in one step, which is
why :func:`load_settings` bothers to track it.
"""

from __future__ import annotations

import platform
import sys
from typing import Annotated

import typer

from .. import __version__
from ..config import ENV_PREFIX, Settings
from ..console import render_table


def info(
    ctx: typer.Context,
    show_environment: Annotated[
        bool,
        typer.Option("--environment/--no-environment", help="Include interpreter details."),
    ] = False,
) -> None:
    """Print the effective configuration, one row per setting."""
    from ..cli import get_context

    context = get_context(ctx)
    loaded = context.loaded
    settings = loaded.settings

    rows = [
        (name, getattr(settings, name), loaded.source_of(name)) for name in Settings.model_fields
    ]
    context.console.print(render_table("Configuration", ("setting", "value", "source"), rows))

    origin = str(loaded.config_path) if loaded.config_path else "none found"
    context.console.print(f"config file: {origin}")
    context.console.print(f"env prefix:  {ENV_PREFIX}*")

    if show_environment:
        environment_rows = [
            ("{{ cookiecutter.command_name }}", __version__),
            ("python", platform.python_version()),
            ("platform", platform.platform()),
            ("executable", sys.executable),
        ]
        context.console.print(render_table("Environment", ("component", "value"), environment_rows))
