"""``{{ cookiecutter.command_name }} batch`` — convert a directory of files, with progress and a summary.

The progress bar is drawn on the stderr console so that ``... batch --json > run.json``
still produces parseable output. Progress reporting for long geospatial runs is
discussed in
https://www.batch-processing.com/spatial-batch-processing-async-workflows/progress-tracking-in-batch-jobs/
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated, Any

import typer

from ..console import make_progress, render_table
from ..pipeline import (
    DEFAULT_PATTERN,
    BatchReport,
    TaskOutcome,
    discover_inputs,
    iter_reports,
    resolve_workers,
    run_batch,
)


def _as_json(report: BatchReport, output_dir: Path) -> str:
    """Serialise a run for a downstream job or a CI artefact."""
    payload: dict[str, Any] = {
        "output_dir": str(output_dir),
        "attempted": len(report.outcomes),
        "succeeded": len(report.succeeded),
        "failed": len(report.failed),
        "features": report.features,
        "stopped_early": report.stopped_early,
        "results": [
            {
                "source": str(outcome.source),
                "destination": str(outcome.destination),
                "features": outcome.features,
                "skipped": outcome.skipped,
                "error": outcome.error,
            }
            for outcome in report.outcomes
        ],
    }
    return json.dumps(payload, indent=2)


def batch(
    ctx: typer.Context,
    source_dir: Annotated[
        Path,
        typer.Argument(
            help="Directory of input files.", exists=True, file_okay=False, readable=True
        ),
    ],
    pattern: Annotated[
        str, typer.Option("--pattern", "-p", help="Glob matched against the input directory.")
    ] = DEFAULT_PATTERN,
    recursive: Annotated[
        bool, typer.Option("--recursive/--no-recursive", "-r", help="Descend into subdirectories.")
    ] = False,
    workers: Annotated[
        int | None,
        typer.Option("--workers", "-w", help="Parallel worker processes.", show_default=False),
    ] = None,
    fail_fast: Annotated[
        bool | None,
        typer.Option("--fail-fast/--keep-going", help="Stop at the first failure."),
    ] = None,
    as_json: Annotated[
        bool, typer.Option("--json", help="Emit a machine-readable report on stdout.")
    ] = False,
) -> None:
    """Convert every matching file in a directory and summarise the run.

    Exits non-zero if any file failed, or if the pattern matched nothing at all — an
    empty run that reports success is how silent pipeline breakages start.
    """
    from ..cli import get_context

    context = get_context(ctx)
    settings = context.settings

    sources = discover_inputs(source_dir, pattern=pattern, recursive=recursive)
    if not sources:
        context.err_console.print(
            f"[bold red]error:[/bold red] no files matching {pattern!r} in {source_dir}"
        )
        raise typer.Exit(code=1)

    effective_workers = resolve_workers(settings.workers if workers is None else workers)
    if context.verbose:
        context.err_console.print(
            f"{len(sources)} file(s), {effective_workers} worker(s), target {settings.crs}"
        )

    progress = make_progress(context.err_console)
    with progress:
        task = progress.add_task("converting", total=len(sources))

        def advance(_outcome: TaskOutcome) -> None:
            progress.advance(task)

        report = run_batch(
            sources,
            settings.output_dir,
            epsg=settings.target_epsg,
            precision=settings.precision,
            overwrite=settings.overwrite,
            workers=effective_workers,
            fail_fast=settings.fail_fast if fail_fast is None else fail_fast,
            on_result=advance,
        )

    if as_json:
        context.console.print_json(_as_json(report, settings.output_dir))
    else:
        if context.verbose or report.failed:
            context.console.print(
                render_table("Results", ("file", "status", "detail"), iter_reports(report))
            )
        summary = (
            f"{len(report.succeeded)}/{len(report.outcomes)} file(s) converted, "
            f"{report.features} features"
        )
        if report.stopped_early:
            summary += " (stopped early)"
        context.console.print(summary)

    for outcome in report.failed:
        context.err_console.print(f"[red]failed[/red] {outcome.source}: {outcome.error}")

    if report.exit_code:
        raise typer.Exit(code=report.exit_code)
