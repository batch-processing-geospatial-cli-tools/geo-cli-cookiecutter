# geo-cli-cookiecutter

A Cookiecutter template that scaffolds a production-ready geospatial Python CLI in one
command — Typer subcommands, Rich output, layered Pydantic configuration, a real test
suite and a CI matrix, all wired together and working before you write a line of your own
code.

## The problem it solves

Every geospatial command-line tool starts the same way. You need subcommands that share
global options, a config file that environment variables and flags can override, output
that is readable in a terminal and parseable in a pipe, error handling that produces
useful exit codes, progress reporting for batch runs, and a test suite that exercises the
CLI rather than just the library underneath it. None of that is hard. All of it takes a
day or two, every time, and it is usually done slightly differently each time.

This template produces that layer, already assembled and already tested. Generated
projects come with a working `convert`/`batch` implementation as a worked example, so the
tests exercise real code paths rather than stubs, and optional rasterio, pyogrio and
shapely subcommands you can switch on or off at generation time.

## Quickstart

```bash
uvx cookiecutter https://github.com/batch-processing-geospatial-cli-tools/geo-cli-cookiecutter.git
```

Or from a clone, which is also how you run the template's own tests:

```bash
git clone https://github.com/batch-processing-geospatial-cli-tools/geo-cli-cookiecutter.git
cd geo-cli-cookiecutter
uv sync --extra dev
uv run cookiecutter . --output-dir ~/projects
```

Then work with what it produced:

```bash
cd ~/projects/<your-slug>
uv sync --all-extras
uv run <your-command> --help
uv run pytest
```

## Template variables

| Variable | Default | Notes |
| --- | --- | --- |
| `project_name` | `Geo Tool` | Human-readable name |
| `project_slug` | derived | Directory, distribution and repository name |
| `module_name` | derived | Importable package under `src/` |
| `command_name` | derived | The installed console script |
| `project_description` | — | One line, used in `--help` and the README |
| `author_name`, `author_email` | — | Package metadata and license copyright |
| `github_owner` | — | Used for the clone URL in the generated README |
| `version` | `0.1.0` | Initial version |
| `copyright_year` | `2026` | License copyright line |
| `default_epsg` | `4326` | Baked in as the default target CRS |
| `use_rasterio` | `no` | Adds a `raster info` subcommand, dependency and test |
| `use_pyogrio` | `no` | Adds a `vector info` subcommand, dependency and test |
| `use_shapely` | `no` | Adds `geometry describe`/`buffer`, dependency and test |
| `open_source_license` | `MIT` | MIT, Apache-2.0, BSD-3-Clause or Proprietary |
| `init_git_repo` | `yes` | Runs `git init` and stages the generated files |

Unselected extras are not commented out or left as dead imports — the post-generation
hook deletes their modules and tests, and the conditionals in `pyproject.toml` and
`cli.py` mean the dependency and the wiring disappear with them.

## What a generated project contains

```
<slug>/
  pyproject.toml            hatchling, console script, ruff/mypy/pytest config
  README.md                 usage, design notes, configuration reference
  <command>.toml.example    annotated starting config
  .github/workflows/ci.yml  ruff, ruff format, mypy, pytest on 3.11/3.12/3.13
  src/<module>/
    cli.py                  Typer app, global-option callback, error boundary
    config.py               layered TOML + env + flags, validated with Pydantic
    console.py              console factory, table renderer, progress helper
    conversion.py           CSV to GeoJSON, the worked example
    pipeline.py             batch discovery, process pool, per-file outcomes
    errors.py               error types carrying their own exit codes
    commands/               one module per subcommand
  tests/                    CliRunner tests plus unit tests, ~90 assertions
```

The design decisions behind those files are documented in the generated project's own
README, which is worth reading once before you start changing things.

## How the template is built

**Hooks do the validation and the pruning.** `hooks/pre_gen_project.py` rejects an
invalid slug, module name, command name or EPSG code before anything is written —
cookiecutter deletes a partially generated tree when a pre-gen hook exits non-zero, so a
bad answer never leaves a half-baked directory behind.
`hooks/post_gen_project.py` deletes the files for unselected extras, keeps the one
license you chose, optionally runs `git init`, and prints the next commands to run.

**The template tree is not linted, the output is.** `{{cookiecutter.project_slug}}/`
contains Jinja source that is not valid Python, so ruff and mypy are configured to skip
it. Skipping it would be an easy way to ship a broken template, so the test suite closes
the gap from the other side: it bakes projects and asserts on what comes out.

## Testing

```bash
uv sync --extra dev
uv run pytest -m "not slow"   # fast: bakes many permutations, inspects the output
uv run pytest                 # everything, including the end-to-end install
```

The fast tests bake with defaults and with a range of `extra_context` permutations, then
check that the file tree is exactly what is expected, that unselected extras leave no
trace, that no `{{cookiecutter.*}}` placeholder survives in any file or path, that every
generated `.py` byte-compiles, and that the generated `pyproject.toml` parses with
`tomllib` and declares the right entry point. Another group drives the pre-generation
hook with invalid slugs, module names, command names and EPSG codes and asserts the bake
fails.

The `slow` test is the one that matters most. It bakes a project with every extra
enabled, creates a virtualenv with `uv venv`, installs the project into it with
`uv pip install -e ".[dev]"`, and then runs the generated project's own quality gates
inside that environment: `pytest`, `ruff check`, `ruff format --check`, `mypy`, and the
installed console script. If the template ever emits code that does not lint, type-check,
import or run, that test fails. It is pinned to a single permutation so CI stays quick.

## Further reading

The patterns baked into the generated project are explained in more depth here:

- [Structuring a Multi-Command GDAL CLI with Typer Sub-Apps](https://www.batch-processing.com/cli-architecture-design-patterns/cli-subcommand-organization/structuring-a-multi-command-gdal-cli-with-typer-sub-apps/) — the subcommand layout the template generates.
- [Layering TOML and Env Config for Raster Pipelines](https://www.batch-processing.com/cli-architecture-design-patterns/configuration-file-management/layering-toml-and-env-config-for-raster-pipelines/) — the configuration precedence order in `config.py`.
- [Handling Missing Dependencies Gracefully in Click Apps](https://www.batch-processing.com/cli-architecture-design-patterns/click-vs-typer-for-geospatial-workflows/handling-missing-dependencies-gracefully-in-click-apps/) — why the optional GIS extras are imported lazily.
- [Packaging & CI/CD for a Python Geospatial CLI](https://www.batch-processing.com/cli-architecture-design-patterns/packaging-and-cicd/) — background on the packaging and workflow the template emits.

## License

MIT. See [LICENSE](LICENSE).
