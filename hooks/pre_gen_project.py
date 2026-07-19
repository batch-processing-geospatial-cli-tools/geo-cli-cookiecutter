"""Validate the answers before a single file is written.

Cookiecutter has no schema layer, so a bad answer normally surfaces much later as a
syntax error in the rendered project or an unimportable package. Failing here keeps the
output directory clean: cookiecutter removes a partially generated tree when a pre-gen
hook exits non-zero, so the user never has to delete a half-baked project by hand.
"""

from __future__ import annotations

import keyword
import re
import sys

# PEP 508 name rules, narrowed: we also forbid a leading/trailing hyphen so the slug is
# usable verbatim as a directory name, a distribution name and a GitHub repository name.
PROJECT_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
# A valid Python identifier that is also a sane top-level package name.
MODULE_NAME_RE = re.compile(r"^[a-z][a-z0-9_]*$")
# Console scripts get typed a lot; allow hyphens and dots but nothing shell-significant.
COMMAND_NAME_RE = re.compile(r"^[a-z0-9]+(?:[-.][a-z0-9]+)*$")

# The EPSG registry uses codes in this range. We deliberately do not import pyproj to
# check the code exists: the template must generate without any GIS stack installed.
EPSG_MIN = 1024
EPSG_MAX = 32767

PYTHON_KEYWORDS = frozenset(keyword.kwlist)

project_slug = "{{ cookiecutter.project_slug }}"
module_name = "{{ cookiecutter.module_name }}"
command_name = "{{ cookiecutter.command_name }}"
default_epsg = "{{ cookiecutter.default_epsg }}"

errors: list[str] = []

if not PROJECT_SLUG_RE.match(project_slug):
    errors.append(
        f"project_slug {project_slug!r} is not valid: use lowercase letters, digits and "
        f"single hyphens, e.g. 'raster-tools'."
    )

if not MODULE_NAME_RE.match(module_name):
    errors.append(
        f"module_name {module_name!r} is not a valid Python package name: use lowercase "
        f"letters, digits and underscores, starting with a letter, e.g. 'raster_tools'."
    )
elif module_name in PYTHON_KEYWORDS:
    errors.append(f"module_name {module_name!r} is a Python keyword and cannot be imported.")

if not COMMAND_NAME_RE.match(command_name):
    errors.append(
        f"command_name {command_name!r} is not valid: use lowercase letters, digits and "
        f"single hyphens or dots, e.g. 'rt' or 'raster-tools'."
    )

try:
    epsg = int(default_epsg)
except ValueError:
    errors.append(
        f"default_epsg {default_epsg!r} is not an integer. Give a bare code such as 4326, "
        f"not 'EPSG:4326'."
    )
else:
    if not EPSG_MIN <= epsg <= EPSG_MAX:
        errors.append(
            f"default_epsg {epsg} is outside the EPSG code range "
            f"{EPSG_MIN}-{EPSG_MAX}; 4326 (WGS 84) is the usual default."
        )

if errors:
    print("Cannot generate the project, the following answers are invalid:", file=sys.stderr)
    for error in errors:
        print(f"  - {error}", file=sys.stderr)
    sys.exit(1)
