"""Batch execution: discover inputs, convert them, and report what happened.

Two decisions here are worth explaining because they are the ones that make batch runs
survivable.

First, failures are values, not exceptions. A worker returns a :class:`TaskOutcome`
either way, so one corrupt file out of fifty thousand does not tear down the pool, and
the caller gets a complete report at the end instead of a traceback at file 12,000.
``fail_fast`` opts back into stopping early when that is what you want.

Second, parallelism is process-based and off by default. The work here is I/O plus JSON
encoding, but real geospatial payloads drop into native GDAL code that holds the GIL,
so processes are the honest default shape; see
https://www.batch-processing.com/spatial-batch-processing-async-workflows/multiprocessing-geospatial-tasks/
"""

from __future__ import annotations

import os
from collections.abc import Callable, Iterable, Iterator, Sequence
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path

from .conversion import convert_file
from .errors import InputError, ToolError

DEFAULT_PATTERN = "*.csv"


@dataclass(frozen=True)
class TaskOutcome:
    """The result of processing one input file, successful or not."""

    source: Path
    destination: Path
    features: int = 0
    skipped: int = 0
    error: str | None = None

    @property
    def ok(self) -> bool:
        """Whether the file was converted."""
        return self.error is None


@dataclass(frozen=True)
class BatchReport:
    """Aggregate result of a batch run."""

    outcomes: Sequence[TaskOutcome]
    stopped_early: bool = False

    @property
    def succeeded(self) -> list[TaskOutcome]:
        """Outcomes that produced a file."""
        return [outcome for outcome in self.outcomes if outcome.ok]

    @property
    def failed(self) -> list[TaskOutcome]:
        """Outcomes that raised."""
        return [outcome for outcome in self.outcomes if not outcome.ok]

    @property
    def features(self) -> int:
        """Total features written across the run."""
        return sum(outcome.features for outcome in self.succeeded)

    @property
    def exit_code(self) -> int:
        """``0`` only when every discovered file converted.

        A batch that half-worked must not look like success to a scheduler, so any
        failure — or a run that found nothing to do — is a non-zero status.
        """
        if not self.outcomes:
            return 1
        return 0 if not self.failed else 4


def discover_inputs(
    source_dir: Path, *, pattern: str = DEFAULT_PATTERN, recursive: bool = False
) -> list[Path]:
    """List the files a batch run will process, in a stable order.

    Sorting matters more than it looks: filesystem order is arbitrary, and a run whose
    input order changes between invocations cannot be resumed from a checkpoint or
    compared against a previous log.

    Raises:
        InputError: ``source_dir`` is not a directory.
    """
    if not source_dir.is_dir():
        raise InputError(f"Input directory not found: {source_dir}")
    globber = source_dir.rglob if recursive else source_dir.glob
    return sorted(path for path in globber(pattern) if path.is_file())


def destination_for(source: Path, output_dir: Path, *, suffix: str = ".geojson") -> Path:
    """Map an input path to its output path, preserving the stem."""
    return output_dir / (source.stem + suffix)


def _run_one(
    source: Path,
    destination: Path,
    epsg: int,
    precision: int,
    overwrite: bool,
) -> TaskOutcome:
    """Convert one file, turning any expected failure into an outcome.

    Defined at module level and taking only picklable arguments because
    ``ProcessPoolExecutor`` has to import and call it in a fresh interpreter.
    """
    try:
        result = convert_file(
            source,
            destination,
            epsg=epsg,
            precision=precision,
            overwrite=overwrite,
        )
    except ToolError as exc:
        return TaskOutcome(source=source, destination=destination, error=str(exc))
    except OSError as exc:
        # A worker must never die on an I/O hiccup; the pool would lose queued work.
        return TaskOutcome(source=source, destination=destination, error=f"I/O error: {exc}")
    return TaskOutcome(
        source=source,
        destination=destination,
        features=result.features,
        skipped=result.skipped,
    )


def resolve_workers(requested: int) -> int:
    """Clamp the worker count to something the machine can actually run.

    Oversubscribing processes on a GDAL workload is actively harmful: each worker
    carries its own native memory arena, so more workers than cores buys contention and
    a higher peak RSS, not throughput.
    """
    available = os.cpu_count() or 1
    return max(1, min(requested, available))


def run_batch(
    sources: Iterable[Path],
    output_dir: Path,
    *,
    epsg: int,
    precision: int = 6,
    overwrite: bool = False,
    workers: int = 1,
    fail_fast: bool = False,
    on_result: Callable[[TaskOutcome], None] | None = None,
) -> BatchReport:
    """Convert every path in ``sources`` into ``output_dir``.

    Args:
        sources: Input files, already discovered and ordered.
        output_dir: Directory the GeoJSON files are written into; created if absent.
        epsg: Target CRS recorded in the output.
        precision: Decimal places kept in coordinates.
        overwrite: Replace existing output files instead of failing on them.
        workers: Requested parallelism; clamped to the CPU count.
        fail_fast: Stop as soon as one file fails.
        on_result: Called once per completed file, on the calling thread. This is the
            hook the CLI uses to advance a progress bar; keeping it a callback rather
            than baking Rich in here means the pipeline stays importable from a script.

    Returns:
        A report covering every file that was attempted. With ``fail_fast`` the report
        is short and ``stopped_early`` is set — the files never started are simply
        absent, rather than reported as failures they did not experience.
    """
    tasks = list(sources)
    if not tasks:
        return BatchReport(outcomes=[])

    output_dir.mkdir(parents=True, exist_ok=True)
    effective_workers = resolve_workers(workers)

    if effective_workers == 1:
        return _run_sequential(
            tasks,
            output_dir,
            epsg=epsg,
            precision=precision,
            overwrite=overwrite,
            fail_fast=fail_fast,
            on_result=on_result,
        )
    return _run_parallel(
        tasks,
        output_dir,
        epsg=epsg,
        precision=precision,
        overwrite=overwrite,
        workers=effective_workers,
        fail_fast=fail_fast,
        on_result=on_result,
    )


def _run_sequential(
    tasks: Sequence[Path],
    output_dir: Path,
    *,
    epsg: int,
    precision: int,
    overwrite: bool,
    fail_fast: bool,
    on_result: Callable[[TaskOutcome], None] | None,
) -> BatchReport:
    """Single-process path, also used whenever the machine has one usable core."""
    outcomes: list[TaskOutcome] = []
    for source in tasks:
        outcome = _run_one(source, destination_for(source, output_dir), epsg, precision, overwrite)
        outcomes.append(outcome)
        if on_result is not None:
            on_result(outcome)
        if fail_fast and not outcome.ok:
            return BatchReport(outcomes=outcomes, stopped_early=True)
    return BatchReport(outcomes=outcomes)


def _run_parallel(
    tasks: Sequence[Path],
    output_dir: Path,
    *,
    epsg: int,
    precision: int,
    overwrite: bool,
    workers: int,
    fail_fast: bool,
    on_result: Callable[[TaskOutcome], None] | None,
) -> BatchReport:
    """Process-pool path.

    Work is submitted all at once and consumed as it completes, so a single slow file
    does not stall the workers behind it. Inputs are assumed to be many and small
    relative to memory; a pipeline handling millions of paths would want a bounded
    submission window instead.
    """
    outcomes: list[TaskOutcome] = []
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(
                _run_one, source, destination_for(source, output_dir), epsg, precision, overwrite
            ): source
            for source in tasks
        }
        pending = set(futures)
        while pending:
            done, pending = wait(pending, return_when=FIRST_COMPLETED)
            for future in done:
                outcome = future.result()
                outcomes.append(outcome)
                if on_result is not None:
                    on_result(outcome)
                if fail_fast and not outcome.ok:
                    for remaining in pending:
                        remaining.cancel()
                    return BatchReport(outcomes=outcomes, stopped_early=True)
    return BatchReport(outcomes=outcomes)


def iter_reports(report: BatchReport) -> Iterator[tuple[str, str, str]]:
    """Yield ``(file, status, detail)`` rows suitable for a Rich table."""
    for outcome in report.outcomes:
        if outcome.ok:
            detail = f"{outcome.features} features"
            if outcome.skipped:
                detail += f", {outcome.skipped} rows skipped"
            yield outcome.source.name, "ok", detail
        else:
            yield outcome.source.name, "failed", outcome.error or "unknown error"
