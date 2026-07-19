from __future__ import annotations

import compileall
import tomllib
from pathlib import Path

import pytest

from .conftest import bake, iter_files, read_text_files

EXPECTED_TREE = {
    "README.md",
    "LICENSE",
    "pyproject.toml",
    ".gitignore",
    ".github/workflows/ci.yml",
    "geo-tool.toml.example",
    "src/geo_tool/__init__.py",
    "src/geo_tool/cli.py",
    "src/geo_tool/config.py",
    "src/geo_tool/console.py",
    "src/geo_tool/conversion.py",
    "src/geo_tool/errors.py",
    "src/geo_tool/pipeline.py",
    "src/geo_tool/commands/__init__.py",
    "src/geo_tool/commands/info.py",
    "src/geo_tool/commands/convert.py",
    "src/geo_tool/commands/batch.py",
    "tests/conftest.py",
    "tests/test_cli.py",
    "tests/test_config.py",
    "tests/test_console.py",
    "tests/test_conversion.py",
    "tests/test_pipeline.py",
}


def relative_paths(project: Path) -> set[str]:
    return {path.relative_to(project).as_posix() for path in iter_files(project)}


def test_default_bake_produces_the_expected_tree(tmp_path: Path) -> None:
    project = bake(tmp_path)
    assert project.name == "geo-tool"
    assert relative_paths(project) == EXPECTED_TREE


def test_default_bake_omits_every_optional_extra(tmp_path: Path) -> None:
    project = bake(tmp_path)
    for name in ("raster.py", "vector.py", "geometry.py"):
        assert not (project / "src" / "geo_tool" / "commands" / name).exists()
    for name in ("test_raster.py", "test_vector.py", "test_geometry.py"):
        assert not (project / "tests" / name).exists()


def test_no_template_placeholder_survives_anywhere(tmp_path: Path) -> None:
    project = bake(tmp_path, project_name="Terrain Ops", command_name="terra")
    for path, contents in read_text_files(project):
        assert "cookiecutter" not in contents.lower(), f"unrendered variable in {path}"
        assert "{%" not in contents, f"unrendered Jinja tag in {path}"
    for path in iter_files(project):
        assert "{{" not in str(path), f"unrendered variable in the path {path}"


def test_generated_python_byte_compiles(tmp_path: Path) -> None:
    project = bake(tmp_path, use_rasterio="yes", use_pyogrio="yes", use_shapely="yes")
    assert compileall.compile_dir(str(project), quiet=1, force=True), (
        "generated project contains Python that does not compile"
    )


def test_generated_pyproject_parses_and_declares_the_entry_point(tmp_path: Path) -> None:
    project = bake(tmp_path, project_name="Terrain Ops", command_name="terra")
    with (project / "pyproject.toml").open("rb") as handle:
        document = tomllib.load(handle)
    assert document["project"]["name"] == "terrain-ops"
    assert document["project"]["scripts"] == {"terra": "terrain_ops.cli:main"}
    assert document["project"]["requires-python"] == ">=3.11"
    assert document["build-system"]["build-backend"] == "hatchling.build"
    assert document["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == ["src/terrain_ops"]


def test_slug_and_module_are_derived_from_the_project_name(tmp_path: Path) -> None:
    project = bake(tmp_path, project_name="Coastal Raster Tools")
    assert project.name == "coastal-raster-tools"
    assert (project / "src" / "coastal_raster_tools" / "cli.py").is_file()


def test_command_name_reaches_the_console_script_and_the_docs(tmp_path: Path) -> None:
    project = bake(tmp_path, project_name="Terrain Ops", command_name="terra")
    assert (project / "terra.toml.example").is_file()
    assert "terra convert" in (project / "README.md").read_text(encoding="utf-8")
    assert 'name="terra"' in (project / "src" / "terrain_ops" / "cli.py").read_text(
        encoding="utf-8"
    )


def test_default_epsg_reaches_the_settings_model(tmp_path: Path) -> None:
    project = bake(tmp_path, default_epsg="27700")
    config = (project / "src" / "geo_tool" / "config.py").read_text(encoding="utf-8")
    assert "DEFAULT_EPSG = 27700" in config


def test_git_init_is_opt_in(tmp_path: Path) -> None:
    assert not (bake(tmp_path / "off", init_git_repo="no") / ".git").exists()
    assert (bake(tmp_path / "on", init_git_repo="yes") / ".git").is_dir()


@pytest.mark.parametrize(
    ("license_name", "marker"),
    [
        ("MIT", "MIT License"),
        ("Apache-2.0", "Apache License"),
        ("BSD-3-Clause", "BSD 3-Clause License"),
        ("Proprietary", "All rights reserved"),
    ],
)
def test_license_choice_selects_one_license_file(
    tmp_path: Path, license_name: str, marker: str
) -> None:
    project = bake(tmp_path, open_source_license=license_name)
    license_text = (project / "LICENSE").read_text(encoding="utf-8")
    assert marker in license_text
    assert not list(project.glob("LICENSE_*"))
    with (project / "pyproject.toml").open("rb") as handle:
        assert tomllib.load(handle)["project"]["license"]["text"] == license_name
