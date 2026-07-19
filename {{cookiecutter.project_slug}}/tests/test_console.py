from __future__ import annotations

import io

import pytest
from rich.console import Console

from {{ cookiecutter.module_name }}.console import (
    color_is_disabled,
    make_console,
    make_progress,
    render_table,
    track,
)


def render(console: Console, renderable: object) -> str:
    console.print(renderable)
    stream = console.file
    assert isinstance(stream, io.StringIO)
    return stream.getvalue()


def test_no_color_environment_disables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    assert color_is_disabled() is True
    assert make_console(force_terminal=True).no_color is True


def test_dumb_terminal_disables_color(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "dumb")
    assert color_is_disabled() is True


def test_color_is_allowed_on_a_normal_terminal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("TERM", "xterm-256color")
    assert color_is_disabled() is False


def test_non_tty_output_carries_no_escape_sequences() -> None:
    console = make_console()
    console.file = io.StringIO()
    text = render(console, "[bold red]danger[/bold red]")
    assert "danger" in text
    assert "\x1b[" not in text


def test_quiet_console_writes_nothing() -> None:
    console = make_console(quiet=True)
    console.file = io.StringIO()
    assert render(console, "should not appear") == ""


def test_error_console_targets_stderr() -> None:
    assert make_console(stderr=True).stderr is True


def test_table_renders_every_row() -> None:
    console = make_console()
    console.file = io.StringIO()
    table = render_table("Results", ("file", "status"), [("a.csv", "ok"), ("b.csv", "failed")])
    text = render(console, table)
    assert "Results" in text
    assert "a.csv" in text
    assert "failed" in text


def test_table_stringifies_non_text_cells() -> None:
    console = make_console()
    console.file = io.StringIO()
    text = render(console, render_table("Counts", ("n",), [(42,), (None,)]))
    assert "42" in text
    assert "None" in text


def test_progress_is_disabled_when_output_is_not_a_terminal() -> None:
    assert make_progress(make_console()).disable is True


def test_progress_is_disabled_for_a_quiet_console() -> None:
    assert make_progress(make_console(quiet=True, force_terminal=True)).disable is True


def test_track_yields_every_item() -> None:
    items = ["a", "b", "c"]
    assert list(track(items, console=make_console(quiet=True), description="working")) == items


def test_track_accepts_a_generator_with_an_explicit_total() -> None:
    source = (index for index in range(4))
    result = list(track(source, console=make_console(quiet=True), description="working", total=4))
    assert result == [0, 1, 2, 3]
