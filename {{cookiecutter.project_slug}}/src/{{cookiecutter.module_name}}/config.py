"""Layered configuration: defaults, TOML file, environment variables, CLI flags.

The precedence order is fixed and, in increasing priority:

1. the defaults declared on :class:`Settings`;
2. a TOML file — the one named with ``--config``, else ``${{ cookiecutter.module_name.upper() }}_CONFIG``, else
   ``./{{ cookiecutter.command_name }}.toml``, else ``[tool.{{ cookiecutter.module_name }}]`` in ``./pyproject.toml``;
3. environment variables prefixed ``{{ cookiecutter.module_name.upper() }}_``;
4. options passed on the command line.

Each layer is resolved into a plain dictionary before validation, so a value is
validated exactly once, in one place, whatever layer it came from — a string ``"3857"``
from the environment and an integer ``3857`` from TOML both end up as the same
``int``. :func:`load_settings` also records which layer won for each field so
``{{ cookiecutter.command_name }} info`` can explain a surprising value instead of leaving the user to guess.

The rationale for this layering is discussed in
https://www.batch-processing.com/cli-architecture-design-patterns/configuration-file-management/layering-toml-and-env-config-for-raster-pipelines/
"""

from __future__ import annotations

import os
import tomllib
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from .errors import ConfigError

ENV_PREFIX = "{{ cookiecutter.module_name.upper() }}_"
"""Prefix for every environment variable this tool reads."""

DEFAULT_CONFIG_FILENAME = "{{ cookiecutter.command_name }}.toml"
"""File looked for in the working directory when no config is named explicitly."""

PYPROJECT_TABLE = ("tool", "{{ cookiecutter.module_name }}")
"""Fallback table read out of ``pyproject.toml``."""

DEFAULT_EPSG = {{ cookiecutter.default_epsg }}
"""Target CRS used when nothing overrides it."""

# The EPSG registry's code range. Checked here rather than by importing pyproj, so that
# configuration stays validatable without a GIS stack installed.
EPSG_MIN = 1024
EPSG_MAX = 32767

LogLevel = Literal["debug", "info", "warning", "error"]


class Settings(BaseModel):
    """Validated runtime settings for {{ cookiecutter.project_name }}.

    ``extra="forbid"`` is deliberate: a typo in a config file (``worker = 8``) is far
    more likely than a genuinely unknown key, and silently ignoring it produces a run
    that looks configured but is not.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    target_epsg: int = Field(default=DEFAULT_EPSG, description="Target CRS as an EPSG code.")
    output_dir: Path = Field(default=Path("output"), description="Directory for generated files.")
    workers: int = Field(default=1, ge=1, le=64, description="Parallel workers for batch runs.")
    overwrite: bool = Field(default=False, description="Replace existing output files.")
    precision: int = Field(
        default=6, ge=0, le=15, description="Decimal places kept in coordinates."
    )
    fail_fast: bool = Field(default=False, description="Abort a batch on the first failure.")
    log_level: LogLevel = Field(default="info", description="Verbosity of diagnostic output.")

    @field_validator("target_epsg")
    @classmethod
    def _check_epsg(cls, value: int) -> int:
        """Reject codes outside the EPSG range before they reach a GIS library.

        A bad code otherwise surfaces hundreds of files into a batch run as an opaque
        PROJ error, which is the worst possible moment to find out.
        """
        if not EPSG_MIN <= value <= EPSG_MAX:
            raise ValueError(f"{value} is not in the EPSG code range {EPSG_MIN}-{EPSG_MAX}")
        return value

    @property
    def crs(self) -> str:
        """The target CRS in the ``EPSG:xxxx`` authority form most libraries accept."""
        return f"EPSG:{self.target_epsg}"


@dataclass(frozen=True)
class LoadedSettings:
    """Validated settings plus where each value came from."""

    settings: Settings
    sources: Mapping[str, str] = field(default_factory=dict)
    config_path: Path | None = None

    def source_of(self, name: str) -> str:
        """Name the layer that supplied ``name``; ``"default"`` when nothing overrode it."""
        return self.sources.get(name, "default")


def discover_config_file(
    explicit: Path | None = None,
    *,
    cwd: Path | None = None,
    environ: Mapping[str, str] | None = None,
) -> Path | None:
    """Find the TOML file to read, following the documented search order.

    Args:
        explicit: A path given with ``--config``. Missing files are an error here,
            because the user clearly meant that file.
        cwd: Directory to search; defaults to the process working directory.
        environ: Environment to consult; defaults to ``os.environ``.

    Returns:
        The file to read, or ``None`` when no configuration file exists.

    Raises:
        ConfigError: ``explicit`` was given but does not exist.
    """
    if explicit is not None:
        if not explicit.is_file():
            raise ConfigError(f"Config file not found: {explicit}")
        return explicit

    env = os.environ if environ is None else environ
    from_env = env.get(f"{ENV_PREFIX}CONFIG")
    if from_env:
        candidate = Path(from_env)
        if not candidate.is_file():
            raise ConfigError(f"{ENV_PREFIX}CONFIG points at a missing file: {candidate}")
        return candidate

    base = cwd or Path.cwd()
    local = base / DEFAULT_CONFIG_FILENAME
    if local.is_file():
        return local
    pyproject = base / "pyproject.toml"
    if pyproject.is_file() and _read_pyproject_table(pyproject) is not None:
        return pyproject
    return None


def _read_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file, converting the parse failure into a ``ConfigError``."""
    try:
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path} is not valid TOML: {exc}") from exc
    except OSError as exc:
        raise ConfigError(f"Cannot read {path}: {exc}") from exc


def _read_pyproject_table(path: Path) -> dict[str, Any] | None:
    """Return ``[tool.{{ cookiecutter.module_name }}]`` from a pyproject file, or ``None``."""
    document: Any = _read_toml(path)
    for key in PYPROJECT_TABLE:
        if not isinstance(document, dict) or key not in document:
            return None
        document = document[key]
    return document if isinstance(document, dict) else None


def read_config_file(path: Path) -> dict[str, Any]:
    """Read the settings table out of a config file.

    A dedicated config file may put settings at the top level or under a
    ``[{{ cookiecutter.module_name }}]`` table; ``pyproject.toml`` must use
    ``[tool.{{ cookiecutter.module_name }}]``. Supporting all three costs a few lines and
    removes a whole class of "why is my config ignored" reports.
    """
    if path.name == "pyproject.toml":
        table = _read_pyproject_table(path)
        if table is None:
            raise ConfigError(f"{path} has no [tool.{{ cookiecutter.module_name }}] table")
        return table

    document = _read_toml(path)
    section = document.get("{{ cookiecutter.module_name }}")
    if isinstance(section, dict):
        return section
    return document


def read_environment(environ: Mapping[str, str] | None = None) -> dict[str, Any]:
    """Collect ``{{ cookiecutter.module_name.upper() }}_*`` variables that name a real setting.

    ``{{ cookiecutter.module_name.upper() }}_CONFIG`` is excluded: it selects the file rather than being a
    setting, and would otherwise trip the ``extra="forbid"`` check.
    """
    env = os.environ if environ is None else environ
    values: dict[str, Any] = {}
    for key, raw in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        name = key[len(ENV_PREFIX) :].lower()
        if name == "config" or name not in Settings.model_fields:
            continue
        values[name] = raw
    return values


def load_settings(
    config_file: Path | None = None,
    overrides: Mapping[str, Any] | None = None,
    *,
    environ: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> LoadedSettings:
    """Merge every configuration layer and validate the result.

    Args:
        config_file: Explicit ``--config`` path, if the user gave one.
        overrides: CLI values. Keys whose value is ``None`` are dropped, so an unset
            option never outranks a config file.
        environ: Environment to read; defaults to ``os.environ``. Injectable for tests.
        cwd: Directory used for config discovery; defaults to the working directory.

    Returns:
        The validated settings together with the provenance of each field.

    Raises:
        ConfigError: A file is missing or malformed, or the merged values fail
            validation. The message lists every invalid field at once rather than
            stopping at the first, so a user fixes one round of mistakes, not five.
    """
    path = discover_config_file(config_file, cwd=cwd, environ=environ)

    merged: dict[str, Any] = {}
    sources: dict[str, str] = {}

    def apply(layer: Mapping[str, Any], label: str) -> None:
        for key, value in layer.items():
            merged[key] = value
            sources[key] = label

    if path is not None:
        apply(read_config_file(path), f"file:{path}")
    apply(read_environment(environ), "env")
    if overrides:
        apply({k: v for k, v in overrides.items() if v is not None}, "cli")

    try:
        settings = Settings(**merged)
    except ValidationError as exc:
        problems: list[str] = []
        for error in exc.errors():
            location = ".".join(str(part) for part in error["loc"]) or "config"
            problems.append(f"{location}: {error['msg']}")
        details = "; ".join(problems)
        origin = f" (from {path})" if path is not None else ""
        raise ConfigError(f"Invalid configuration{origin}: {details}") from exc

    return LoadedSettings(settings=settings, sources=sources, config_path=path)
