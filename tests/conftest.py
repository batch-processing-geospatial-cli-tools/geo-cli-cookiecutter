"""Helpers for baking the template in a temporary directory.

Everything goes through the cookiecutter Python API rather than the ``cookiecutter``
command line: the API raises real exceptions the tests can assert on, and it never
touches the user's ``~/.cookiecutterrc`` or replay directory.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from cookiecutter.main import cookiecutter

TEMPLATE_ROOT = Path(__file__).resolve().parent.parent

# Files that are legitimately binary or generated; excluded from text scans.
SKIP_SUFFIXES = frozenset({".png", ".ico", ".gz", ".whl"})


def bake(output_dir: Path, **context: Any) -> Path:
    """Generate a project from the template and return its directory.

    Args:
        output_dir: Directory to generate into, normally the test's ``tmp_path``.
        **context: Overrides merged into ``cookiecutter.json`` defaults.

    Returns:
        The generated project directory.
    """
    context.setdefault("init_git_repo", "no")
    result = cookiecutter(
        str(TEMPLATE_ROOT),
        no_input=True,
        extra_context=context,
        output_dir=str(output_dir),
    )
    return Path(result)


def iter_files(root: Path) -> Iterator[Path]:
    """Yield every file in the generated tree, skipping VCS and cache directories."""
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        parts = set(path.relative_to(root).parts)
        if parts & {".git", "__pycache__", ".ruff_cache", ".mypy_cache"}:
            continue
        yield path


def read_text_files(root: Path) -> Iterator[tuple[Path, str]]:
    """Yield ``(path, contents)`` for every readable text file in the tree."""
    for path in iter_files(root):
        if path.suffix in SKIP_SUFFIXES:
            continue
        try:
            yield path, path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # pragma: no cover - no binary fixtures ship today
            continue


@pytest.fixture
def clean_cwd(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run a test from an empty directory so nothing leaks in from the checkout."""
    monkeypatch.chdir(tmp_path)
    for key in list(os.environ):
        if key.startswith("GEO_TOOL_"):
            monkeypatch.delenv(key, raising=False)
    return tmp_path
