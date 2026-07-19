"""Console factory and Rich rendering helpers.

Rich decides on colour by inspecting the stream it is given, but a CLI has extra
requirements a plain ``Console()`` does not cover: a ``--quiet`` flag has to silence
output without every call site checking a boolean, errors belong on stderr so that
``tool convert ... > out.json`` stays parseable, and ANSI escapes must never reach a
pipe or a CI log. Everything here exists so that command modules can render without
thinking about any of it.

The non-TTY detection follows the approach described in
https://www.batch-processing.com/cli-architecture-design-patterns/rich-console-output-progress-bars/detecting-non-tty-output-and-disabling-rich-color/
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from typing import Any, TypeVar

from rich.console import Console
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
)
from rich.table import Table

T = TypeVar("T")


def color_is_disabled() -> bool:
    """Report whether colour must be suppressed regardless of the output stream.

    Honours the ``NO_COLOR`` convention and the ``TERM=dumb`` signal. Rich already
    handles a non-TTY stream, but neither of these is implied by a TTY check: a user can
    be sitting at a colour terminal and still have asked for plain text.
    """
    if os.environ.get("NO_COLOR"):
        return True
    return os.environ.get("TERM", "").lower() == "dumb"


def make_console(
    *, quiet: bool = False, stderr: bool = False, force_terminal: bool | None = None
) -> Console:
    """Build a console configured for CLI use.

    Args:
        quiet: Route all output to a null device. Preferred over guarding each print,
            because a command's rendering code then has exactly one code path.
        stderr: Write to stderr. Use this for diagnostics and progress so that stdout
            carries only the data a caller may want to redirect.
        force_terminal: Override terminal detection. Only tests should need this.

    Returns:
        A ``Console`` that emits no ANSI escapes when the destination is not a terminal
        or when colour has been disabled by the environment.
    """
    if color_is_disabled():
        force_terminal = False
    return Console(
        quiet=quiet,
        stderr=stderr,
        force_terminal=force_terminal,
        no_color=color_is_disabled(),
        soft_wrap=False,
        highlight=False,
    )


def render_table(title: str, columns: Iterable[str], rows: Iterable[Iterable[Any]]) -> Table:
    """Build a Rich table with the styling used across this tool.

    Returned rather than printed so callers can compose it into a panel or a live
    layout, and so tests can inspect the structure without capturing terminal output.
    """
    table = Table(title=title, title_justify="left", header_style="bold", show_lines=False)
    for column in columns:
        table.add_column(column, overflow="fold")
    for row in rows:
        table.add_row(*(str(cell) for cell in row))
    return table


def make_progress(console: Console, *, transient: bool = True) -> Progress:
    """Create the progress bar used for batch work.

    Includes an item count and a time estimate, because the batch command's whole
    purpose is long runs where "how much is left" is the only interesting question.
    Progress renders to the given console, which should be the stderr one so a bar
    never lands in redirected output.

    The bar switches itself off when the console is not a terminal. A progress display
    that cannot repaint just dumps a final frame into the log, which is noise in CI and
    corruption in a piped report.
    """
    return Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        MofNCompleteColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=transient,
        disable=console.quiet or not console.is_terminal,
    )


def track(
    items: Iterable[T],
    *,
    console: Console,
    description: str,
    total: int | None = None,
) -> Iterator[T]:
    """Iterate ``items`` while drawing a progress bar on ``console``.

    A thin wrapper over :func:`make_progress` for the common sequential case; the batch
    command drives the ``Progress`` object directly because it completes work out of
    order.
    """
    if total is None and hasattr(items, "__len__"):
        total = len(items)  # type: ignore[arg-type]
    with make_progress(console) as progress:
        task = progress.add_task(description, total=total)
        for item in items:
            yield item
            progress.advance(task)
