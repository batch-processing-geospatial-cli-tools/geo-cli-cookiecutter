from __future__ import annotations

from pathlib import Path

import pytest

from {{ cookiecutter.module_name }}.config import (
    ENV_PREFIX,
    Settings,
    discover_config_file,
    load_settings,
    read_config_file,
    read_environment,
)
from {{ cookiecutter.module_name }}.errors import ConfigError


def write_config(path: Path, body: str) -> Path:
    path.write_text(body, encoding="utf-8")
    return path


def test_defaults_apply_when_nothing_is_configured(tmp_path: Path) -> None:
    loaded = load_settings(cwd=tmp_path, environ={})
    assert loaded.settings.target_epsg == {{ cookiecutter.default_epsg }}
    assert loaded.settings.workers == 1
    assert loaded.config_path is None
    assert loaded.source_of("target_epsg") == "default"


def test_toml_file_overrides_defaults(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = 3857\nworkers = 4\n")
    loaded = load_settings(config, environ={})
    assert loaded.settings.target_epsg == 3857
    assert loaded.settings.workers == 4
    assert loaded.source_of("workers").startswith("file:")


def test_environment_overrides_file(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = 3857\n")
    loaded = load_settings(config, environ={f"{ENV_PREFIX}TARGET_EPSG": "27700"})
    assert loaded.settings.target_epsg == 27700
    assert loaded.source_of("target_epsg") == "env"


def test_cli_overrides_environment(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = 3857\n")
    loaded = load_settings(
        config,
        {"target_epsg": 2154},
        environ={f"{ENV_PREFIX}TARGET_EPSG": "27700"},
    )
    assert loaded.settings.target_epsg == 2154
    assert loaded.source_of("target_epsg") == "cli"


def test_none_overrides_do_not_outrank_the_file(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = 3857\n")
    loaded = load_settings(config, {"target_epsg": None, "workers": None}, environ={})
    assert loaded.settings.target_epsg == 3857
    assert loaded.settings.workers == 1


def test_named_section_is_preferred_in_a_dedicated_file(tmp_path: Path) -> None:
    config = write_config(
        tmp_path / "config.toml",
        "unrelated = true\n\n[{{ cookiecutter.module_name }}]\nprecision = 2\n",
    )
    assert read_config_file(config) == {"precision": 2}


def test_pyproject_table_is_discovered(tmp_path: Path) -> None:
    write_config(
        tmp_path / "pyproject.toml",
        "[project]\nname = 'x'\n\n[tool.{{ cookiecutter.module_name }}]\nprecision = 3\n",
    )
    discovered = discover_config_file(cwd=tmp_path)
    assert discovered is not None and discovered.name == "pyproject.toml"
    assert load_settings(cwd=tmp_path, environ={}).settings.precision == 3


def test_pyproject_without_our_table_is_ignored(tmp_path: Path) -> None:
    write_config(tmp_path / "pyproject.toml", "[project]\nname = 'x'\n")
    assert discover_config_file(cwd=tmp_path) is None


def test_default_named_file_beats_pyproject(tmp_path: Path) -> None:
    write_config(tmp_path / "pyproject.toml", "[tool.{{ cookiecutter.module_name }}]\nprecision = 3\n")
    write_config(tmp_path / "{{ cookiecutter.command_name }}.toml", "precision = 5\n")
    assert load_settings(cwd=tmp_path, environ={}).settings.precision == 5


def test_env_var_can_select_the_config_file(tmp_path: Path) -> None:
    config = write_config(tmp_path / "elsewhere.toml", "workers = 7\n")
    loaded = load_settings(cwd=tmp_path, environ={f"{ENV_PREFIX}CONFIG": str(config)})
    assert loaded.settings.workers == 7


def test_env_config_pointing_at_a_missing_file_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="missing file"):
        load_settings(cwd=tmp_path, environ={f"{ENV_PREFIX}CONFIG": str(tmp_path / "nope.toml")})


def test_explicit_missing_config_is_an_error(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_settings(tmp_path / "absent.toml", environ={})


def test_malformed_toml_is_reported_with_the_path(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = = 4326\n")
    with pytest.raises(ConfigError, match="not valid TOML"):
        load_settings(config, environ={})


def test_unknown_key_is_rejected(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "worker = 4\n")
    with pytest.raises(ConfigError, match="worker"):
        load_settings(config, environ={})


def test_out_of_range_epsg_is_rejected(tmp_path: Path) -> None:
    config = write_config(tmp_path / "config.toml", "target_epsg = 99\n")
    with pytest.raises(ConfigError, match="EPSG"):
        load_settings(config, environ={})


def test_invalid_worker_count_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="workers"):
        load_settings(overrides={"workers": 0}, cwd=tmp_path, environ={})


def test_every_validation_problem_is_reported_at_once(tmp_path: Path) -> None:
    config = write_config(
        tmp_path / "config.toml", "target_epsg = 1\nworkers = 0\nprecision = 99\n"
    )
    with pytest.raises(ConfigError) as excinfo:
        load_settings(config, environ={})
    message = str(excinfo.value)
    assert "target_epsg" in message
    assert "workers" in message
    assert "precision" in message


def test_environment_reader_ignores_foreign_and_unknown_variables() -> None:
    values = read_environment(
        {
            f"{ENV_PREFIX}WORKERS": "3",
            f"{ENV_PREFIX}CONFIG": "/somewhere.toml",
            f"{ENV_PREFIX}NOT_A_SETTING": "x",
            "PATH": "/usr/bin",
        }
    )
    assert values == {"workers": "3"}


@pytest.mark.parametrize("raw", ["true", "1", "yes", "on"])
def test_boolean_settings_accept_the_usual_env_spellings(raw: str) -> None:
    loaded = load_settings(environ={f"{ENV_PREFIX}OVERWRITE": raw})
    assert loaded.settings.overwrite is True


def test_crs_property_uses_authority_form() -> None:
    assert Settings(target_epsg=3857).crs == "EPSG:3857"


def test_settings_are_immutable() -> None:
    settings = Settings()
    with pytest.raises(Exception, match=r"frozen|Instance is frozen"):
        settings.workers = 4
