"""Prune unselected extras, optionally initialise git, and print next steps.

Cookiecutter renders every file in the template unconditionally; the only supported way
to make a file optional is to delete it afterwards. Doing the pruning here (rather than
wrapping whole modules in Jinja conditionals) keeps the template files valid, readable
Python that an editor and ruff can still understand.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_DIR = Path.cwd()
MODULE_NAME = "{{ cookiecutter.module_name }}"
COMMAND_NAME = "{{ cookiecutter.command_name }}"
PROJECT_SLUG = "{{ cookiecutter.project_slug }}"
# Annotated as plain ``str`` on purpose: without it a type checker reading this file
# before rendering infers a literal type and flags every comparison as impossible.
INIT_GIT_REPO: str = "{{ cookiecutter.init_git_repo }}"
CHOSEN_LICENSE: str = "{{ cookiecutter.open_source_license }}"

# Each entry is (was it selected, files it owns). A list rather than a dict keyed on the
# answer, because several extras share the answer "no" and would collide as dict keys.
EXTRAS: list[tuple[str, tuple[str, ...]]] = [
    (
        "{{ cookiecutter.use_rasterio }}",
        (f"src/{MODULE_NAME}/commands/raster.py", "tests/test_raster.py"),
    ),
    (
        "{{ cookiecutter.use_pyogrio }}",
        (f"src/{MODULE_NAME}/commands/vector.py", "tests/test_vector.py"),
    ),
    (
        "{{ cookiecutter.use_shapely }}",
        (f"src/{MODULE_NAME}/commands/geometry.py", "tests/test_geometry.py"),
    ),
]

LICENSE_FILES = {
    "MIT": "LICENSE_MIT",
    "Apache-2.0": "LICENSE_APACHE",
    "BSD-3-Clause": "LICENSE_BSD",
    "Proprietary": "LICENSE_PROPRIETARY",
}


def remove(relative_path: str) -> None:
    """Delete a generated path, tolerating an already-absent file."""
    target = PROJECT_DIR / relative_path
    if target.is_dir():
        shutil.rmtree(target)
    elif target.exists():
        target.unlink()


def prune_extras() -> list[str]:
    """Delete the modules and tests for every extra the user did not select."""
    removed: list[str] = []
    for selected, paths in EXTRAS:
        if selected == "yes":
            continue
        for path in paths:
            remove(path)
            removed.append(path)
    return removed


def select_license() -> None:
    """Keep only the chosen license text, renamed to ``LICENSE``."""
    keep = LICENSE_FILES.get(CHOSEN_LICENSE)
    for name in LICENSE_FILES.values():
        if name == keep:
            (PROJECT_DIR / name).rename(PROJECT_DIR / "LICENSE")
        else:
            remove(name)


def init_git() -> None:
    """Create an initial repository so the first ``git diff`` is meaningful."""
    if INIT_GIT_REPO != "yes":
        return
    try:
        subprocess.run(["git", "init", "--quiet"], cwd=PROJECT_DIR, check=True)
        subprocess.run(["git", "add", "--all"], cwd=PROJECT_DIR, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"  note: could not initialise a git repository ({exc})", file=sys.stderr)


def main() -> None:
    """Run every post-generation step and tell the user what to do next."""
    removed = prune_extras()
    select_license()
    init_git()

    print(f"\nCreated {PROJECT_SLUG}/")
    if removed:
        print(f"Pruned {len(removed)} file(s) for unselected extras.")
    print(
        "\nNext steps:\n"
        f"  cd {PROJECT_SLUG}\n"
        "  uv sync\n"
        f"  uv run {COMMAND_NAME} --help\n"
        "  uv run pytest\n"
    )


main()
