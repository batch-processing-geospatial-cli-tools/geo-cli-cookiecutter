from __future__ import annotations

from pathlib import Path

import pytest
from cookiecutter.exceptions import FailedHookException

from .conftest import bake


@pytest.mark.parametrize(
    "slug",
    [
        "Bad Slug",
        "trailing-",
        "-leading",
        "double--hyphen",
        "UPPER",
        "under_score",
        "has space",
    ],
)
def test_invalid_project_slug_is_rejected(tmp_path: Path, slug: str) -> None:
    with pytest.raises(FailedHookException):
        bake(tmp_path, project_slug=slug)


@pytest.mark.parametrize("module", ["1leading-digit", "has-hyphen", "Upper", "class", ""])
def test_invalid_module_name_is_rejected(tmp_path: Path, module: str) -> None:
    with pytest.raises(FailedHookException):
        bake(tmp_path, module_name=module)


@pytest.mark.parametrize("command", ["has space", "semi;colon", "UPPER", "--dashes", ""])
def test_invalid_command_name_is_rejected(tmp_path: Path, command: str) -> None:
    with pytest.raises(FailedHookException):
        bake(tmp_path, command_name=command)


@pytest.mark.parametrize("epsg", ["EPSG:4326", "abc", "0", "1023", "32768", "-4326", ""])
def test_invalid_epsg_is_rejected(tmp_path: Path, epsg: str) -> None:
    with pytest.raises(FailedHookException):
        bake(tmp_path, default_epsg=epsg)


@pytest.mark.parametrize("epsg", ["4326", "3857", "27700", "1024", "32767"])
def test_valid_epsg_codes_are_accepted(tmp_path: Path, epsg: str) -> None:
    project = bake(tmp_path / epsg, default_epsg=epsg)
    assert (project / "src" / "geo_tool" / "config.py").is_file()


def test_a_rejected_bake_leaves_no_directory_behind(tmp_path: Path) -> None:
    with pytest.raises(FailedHookException):
        bake(tmp_path, project_slug="Not A Slug")
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize(
    "name",
    ["raster-tools", "a", "a1", "coastal-raster-tools-2"],
)
def test_valid_project_slugs_are_accepted(tmp_path: Path, name: str) -> None:
    project = bake(tmp_path / name, project_slug=name)
    assert project.name == name
