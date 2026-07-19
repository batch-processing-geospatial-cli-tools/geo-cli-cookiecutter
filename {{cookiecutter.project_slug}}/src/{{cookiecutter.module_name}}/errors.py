"""Error types and the exit codes they map to.

Every failure path in this tool raises one of these instead of calling ``sys.exit``
deep inside library code. The CLI layer is the only place that decides how an error is
presented and what the process exit status becomes, which keeps the same functions
usable from a script or a test without a ``SystemExit`` escaping.
"""

from __future__ import annotations


class ToolError(Exception):
    """Base class for every error this tool raises deliberately.

    ``exit_code`` is the process status the CLI uses. Codes are kept distinct so shell
    callers and CI jobs can branch on the failure kind without parsing stderr.
    """

    exit_code = 1


class ConfigError(ToolError):
    """Configuration was missing, malformed, or failed validation."""

    exit_code = 2


class InputError(ToolError):
    """An input path was missing, unreadable, or not in the expected format."""

    exit_code = 3


class ProcessingError(ToolError):
    """A record or file could not be processed."""

    exit_code = 4


class MissingDependencyError(ToolError):
    """An optional dependency needed by this subcommand is not installed.

    Optional GIS stacks are heavy, so the tool imports them lazily inside the command
    that needs them and turns the ``ImportError`` into this, with an actionable message
    naming the extra to install.
    """

    exit_code = 5

    def __init__(self, package: str, extra: str) -> None:
        """Build the message from the missing package and the extra that provides it."""
        super().__init__(
            f"This command needs the '{package}' package, which is not installed. "
            f'Install it with: pip install "{{ cookiecutter.project_slug }}[{extra}]"'
        )
        self.package = package
        self.extra = extra
