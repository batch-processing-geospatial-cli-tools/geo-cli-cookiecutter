# {{ cookiecutter.project_name }}

{{ cookiecutter.project_description }}

## What it does

`{{ cookiecutter.command_name }}` reads delimited point files and writes GeoJSON, one file at a
time or a whole directory at once. It is a working starting point rather than a demo: the
configuration layering, error handling, exit codes, progress reporting and test suite are
the parts you would otherwise spend a week assembling, and they are already here.

## Install

```bash
git clone https://github.com/{{ cookiecutter.github_owner }}/{{ cookiecutter.project_slug }}.git
cd {{ cookiecutter.project_slug }}
uv sync                      # or: python -m venv .venv && .venv/bin/pip install -e ".[dev]"
uv run {{ cookiecutter.command_name }} --help
```
{%- if cookiecutter.use_rasterio == 'yes' or cookiecutter.use_pyogrio == 'yes' or cookiecutter.use_shapely == 'yes' %}

Optional subcommands need their own extras:

```bash
{% if cookiecutter.use_rasterio == 'yes' %}uv sync --extra raster       # rasterio, for `{{ cookiecutter.command_name }} raster`
{% endif %}{% if cookiecutter.use_pyogrio == 'yes' %}uv sync --extra vector       # pyogrio, for `{{ cookiecutter.command_name }} vector`
{% endif %}{% if cookiecutter.use_shapely == 'yes' %}uv sync --extra geometry     # shapely, for `{{ cookiecutter.command_name }} geometry`
{% endif %}```

Without the extra, those commands exit with a message naming the package to install; the
rest of the tool keeps working.
{%- endif %}

## Usage

Convert a single file:

```console
$ {{ cookiecutter.command_name }} convert sites.csv --out sites.geojson
wrote sites.geojson (1284 features, 3 rows skipped, EPSG:{{ cookiecutter.default_epsg }})
```

Convert a directory, in parallel, and get a machine-readable report:

```console
$ {{ cookiecutter.command_name }} --output-dir build batch data/ --pattern '*.csv' --workers 8 --json
{
  "output_dir": "build",
  "attempted": 412,
  "succeeded": 411,
  "failed": 1,
  "features": 903118,
  "stopped_early": false,
  "results": [...]
}
```

Check what the tool thinks its configuration is, and where each value came from:

```console
$ {{ cookiecutter.command_name }} --epsg 27700 info
  Configuration
 setting      value            source
 target_epsg  27700            cli
 output_dir   output           default
 workers      4                file:/srv/jobs/{{ cookiecutter.command_name }}.toml
 overwrite    False            default
 precision    6                default
 fail_fast    False            default
 log_level    info             default

config file: /srv/jobs/{{ cookiecutter.command_name }}.toml
env prefix:  {{ cookiecutter.module_name.upper() }}_*
```
{%- if cookiecutter.use_rasterio == 'yes' %}

Inspect a raster header without reading any pixels:

```console
$ {{ cookiecutter.command_name }} raster info dem.tif
```
{%- endif %}
{%- if cookiecutter.use_pyogrio == 'yes' %}

Inspect a vector layer's metadata:

```console
$ {{ cookiecutter.command_name }} vector info parcels.gpkg --layer parcels
```
{%- endif %}
{%- if cookiecutter.use_shapely == 'yes' %}

Describe or buffer a geometry given as WKT:

```console
$ {{ cookiecutter.command_name }} geometry buffer "POINT (0 0)" --distance 250
```
{%- endif %}

## How it works

**Global options live on one callback.** `--config`, `--verbose`, `--quiet`, `--epsg` and
`--output-dir` are declared once on the root callback in `cli.py`, which resolves settings
and stores an `AppContext` on the Typer context. Subcommands read it rather than each
re-declaring and re-parsing the same flags.

**Configuration is layered, and the layers are documented.** In increasing priority:
defaults on the `Settings` model, then a TOML file, then `{{ cookiecutter.module_name.upper() }}_*`
environment variables, then command-line flags. Every layer is flattened into one
dictionary before Pydantic validates it, so a value is checked in exactly one place
whatever supplied it — and `{{ cookiecutter.command_name }} info` prints which layer won for each
setting, which is the answer to nearly every "why is it using that CRS" question.

**Unknown configuration keys are an error.** `extra="forbid"` on the settings model means a
typo like `worker = 8` fails loudly at startup instead of producing a run that looks
configured and is not.

**Errors are values in the pipeline and exceptions at the edges.** Library code raises
`ToolError` subclasses carrying their own exit code (`2` configuration, `3` input,
`4` processing, `5` missing optional dependency). A custom Typer group catches them at the
CLI boundary, prints one line on stderr and exits with that code. Batch workers go further
and return failures as `TaskOutcome` values, so one corrupt file out of fifty thousand does
not tear down the process pool.

**stdout carries data, stderr carries everything else.** There are two consoles. Progress
bars, diagnostics and error lines go to stderr, so `... batch --json > report.json` is
always valid JSON. The progress bar disables itself when the output is not a terminal
rather than dumping a final frame into a CI log, and colour is dropped for `NO_COLOR`,
`TERM=dumb`, or any non-TTY destination.

**Parallelism is process-based and clamped.** Batch work runs in a `ProcessPoolExecutor`
because real geospatial payloads drop into native GDAL code that holds the GIL. The worker
count is clamped to the CPU count: oversubscribing GDAL processes buys memory pressure, not
throughput.

## Configuration reference

| Setting | Type | Default | Meaning |
| --- | --- | --- | --- |
| `target_epsg` | int | `{{ cookiecutter.default_epsg }}` | Target CRS, as a bare EPSG code |
| `output_dir` | path | `output` | Where generated files are written |
| `workers` | int (1–64) | `1` | Parallel worker processes for `batch` |
| `overwrite` | bool | `false` | Replace existing output files |
| `precision` | int (0–15) | `6` | Decimal places kept in coordinates |
| `fail_fast` | bool | `false` | Abort a batch at the first failure |
| `log_level` | enum | `info` | `debug`, `info`, `warning` or `error` |

Sources, lowest priority first:

1. the defaults above;
2. `--config FILE`, else `${{ cookiecutter.module_name.upper() }}_CONFIG`, else `./{{ cookiecutter.command_name }}.toml`,
   else `[tool.{{ cookiecutter.module_name }}]` in `./pyproject.toml`;
3. environment variables, e.g. `{{ cookiecutter.module_name.upper() }}_WORKERS=8`;
4. command-line flags.

See `{{ cookiecutter.command_name }}.toml.example` for a starting file.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | Success |
| `1` | Usage error, or a batch that matched no files |
| `2` | Configuration is missing or invalid |
| `3` | An input path is missing or unreadable |
| `4` | One or more files failed to process |
| `5` | An optional dependency is not installed |
| `130` | Interrupted |

## Development

```bash
uv sync --all-extras
uv run pytest --cov --cov-report=term-missing
uv run ruff check .
uv run ruff format --check .
uv run mypy
```

Tests generate their fixtures in `tmp_path` and never touch the network, so the suite runs
anywhere Python does.

## Further reading

Background on the patterns this project is built from:

- [Sharing Global Options Across Geospatial Subcommands](https://www.batch-processing.com/cli-architecture-design-patterns/cli-subcommand-organization/sharing-global-options-across-geospatial-subcommands/) — the root-callback approach used in `cli.py`.
- [Layering TOML and Env Config for Raster Pipelines](https://www.batch-processing.com/cli-architecture-design-patterns/configuration-file-management/layering-toml-and-env-config-for-raster-pipelines/) — the precedence order implemented in `config.py`.
- [Validating CLI Config with Pydantic](https://www.batch-processing.com/cli-architecture-design-patterns/configuration-file-management/validating-cli-config-with-pydantic-for-gis-workflows/) — why the settings model forbids unknown keys.
- [Detecting Non-TTY Output and Disabling Rich Color](https://www.batch-processing.com/cli-architecture-design-patterns/rich-console-output-progress-bars/detecting-non-tty-output-and-disabling-rich-color/) — the console factory in `console.py`.
- [Testing Click Commands with CliRunner](https://www.batch-processing.com/cli-architecture-design-patterns/click-vs-typer-for-geospatial-workflows/testing-click-commands-with-clirunner-for-gis-tools/) — how the CLI tests are structured.

## License

{{ cookiecutter.open_source_license }}. See [LICENSE](LICENSE).
