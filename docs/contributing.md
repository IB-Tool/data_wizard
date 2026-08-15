# Contributing & Development

This document covers the development setup, CI/CD pipeline, test structure, and code quality tooling for Data Wizard.

This plugin is a companion to **[IBTool](https://github.com/IB-Tool/IB-Tool-3)**
(the main plugin) and follows the same development conventions as IBTool and
[ibtoolpartion](https://github.com/IB-Tool/ibtoolpartion). For the canonical
description of the CI/test/release approach shared by all three IB-Tool
plugins, see
[IBTool's own `docs/contributing.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/contributing.md).
This document only covers what differs here.

---

## Continuous Integration with GitHub Actions

The project uses two GitHub Actions workflows:

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| **CI** | `.github/workflows/ci.yml` | push to `master`/`main`, PRs | Docker-based tests + Codecov coverage |
| **QGIS Plugin CI** | `.github/workflows/qgis-plugin-ci.yml` | push to `master`/`main`, PRs | Lint, security scan, plugin structure validation |

---

## Workflow 1 — CI (Docker-based tests)

Runs the full test suite inside a Docker container with a real QGIS environment.

Steps:
1. Checks out the repository
2. Builds the Docker image from `Dockerfile` at the repo root
3. Runs the test suite inside the container with coverage reporting
4. Strips container-absolute paths from `coverage.xml`
5. Uploads the coverage report to Codecov

The image is a slimmed-down variant of IBTool's own `Dockerfile` — this
plugin has no runtime dependencies beyond QGIS's own processing algorithms
(`processing`, `qgis.core`), so `numpy`/`scipy`/`networkx` are not installed.

### Coverage Reporting

Test coverage is measured with `pytest-cov` (`.coveragerc` at the repo root: `source = data_wizard, scripts`). The `coverage.xml`/`htmlcov/` files are written by the container into the volume-mounted workspace, with container-absolute paths (`/plugins/data_wizard/`) stripped for portability.

> **No Codecov upload.** Unlike IBTool and ibtoolpartion, this repository does
> not have a Codecov project set up (`CODECOV_TOKEN` was never configured,
> and the previous Codecov upload step in `ci.yml` could only ever fail with
> `fail_ci_if_error: true`). This is a deliberate, documented exclusion — see
> [`docs/test-strategy.md`](test-strategy.md#justified-exclusions) — not an
> oversight to fix later. Coverage is produced on every CI run and kept as a
> downloadable **CI artifact** (`coverage-report`, containing `coverage.xml`
> and `htmlcov/`) instead.

### Local Development with Docker

```bash
# Build the Docker image
docker build -t qgis-plugin-test .
# Run tests
docker run --rm -v $(pwd):/plugins/data_wizard qgis-plugin-test
# Interactive shell inside the container
docker run --rm -it qgis-plugin-test /bin/bash
```

---

## Workflow 2 — QGIS Plugin CI (linting & validation)

Runs static analysis without Docker — suitable for quick feedback on every push.

Steps:
1. **Plugin validator** (`ci/qgis_plugin_validate.py --auto`): checks folder name, required files (`metadata.txt`, `__init__.py`, `LICENSE`), and all required metadata keys.
2. **Flake8**: PEP 8 style checks.
3. **Bandit**: Security scan (medium severity and above).
4. **detect-secrets**: Scans for accidentally committed credentials.

Run locally:

```bash
pip install flake8 bandit detect-secrets
python ci/qgis_plugin_validate.py --auto
flake8 .
bandit -r . -ll
detect-secrets scan --force-use-all-plugins
```

---

## Pre-commit Hook (local, automatic)

`scripts/git-hooks/pre-commit` runs the QGIS Plugin CI checks above (validator,
flake8, bandit, detect-secrets) plus `pytest test/ -m unit` — everything that
does **not** need Docker — automatically before every `git commit`. It
deliberately skips the full Docker-based Workflow 1 (integration tests +
coverage), which stays a manual/CI-only step (see above) because a full
`docker build && docker run` takes minutes, not seconds.

**One-time setup per clone** (the hook lives in a tracked, versioned directory
— `.git/hooks/` itself is never committed by git):

```bash
git config core.hooksPath scripts/git-hooks
```

This applies regardless of which IDE or Git client is used to commit
(IntelliJ/PyCharm, VS Code, CLI, …) — they all invoke the same `git` binary,
which reads `core.hooksPath` and runs the hook the same way.

If your local QGIS install is not at the default
`C:\Program Files\QGIS 3.40.0`, point the hook at it once:

```bash
git config data-wizard.qgisPrefix "D:/QGIS 3.40"
```

To skip the hook for a single commit (use sparingly — fix the underlying
issue instead of routinely bypassing this):

```bash
git commit --no-verify
```

---

## Release Process

Releases are built with `scripts/create_release_zip.py`, mirroring IBTool's
and ibtoolpartion's release process:

```bash
python ci/qgis_plugin_validate.py --auto
python scripts/create_release_zip.py
python ci/qgis_plugin_validate.py --zip dist/*.zip
```

This produces `dist/data_wizard.<version>.zip`. Bump `version` in
`metadata.txt` and add a corresponding entry to
[`docs/CHANGELOG.md`](CHANGELOG.md) before tagging a release. There is no
automated GitHub release workflow — the ZIP is built and uploaded to GitHub
Releases manually. See
[`ai/core/release-conventions.md`](../ai/core/release-conventions.md) for
the full invariants (required metadata keys, LICENSE file, folder naming).

---

## Code Quality Standards

| Tool | Purpose | Config |
|------|---------|--------|
| `flake8` | Style (PEP 8) | `.flake8` |
| `bandit` | Security | `.bandit` |
| `pylint` | Comprehensive linting | `pylintrc` |
| `pytest` | Unit & integration tests | `pytest.ini` |
| `detect-secrets` | Credential scanning | — |

---

## Testing

Tests live in `test/`. Run them with:

```bash
# All tests (requires QGIS environment)
pytest test/ -v

# Unit tests only (no QGIS required)
pytest test/ -v -m unit
```

### Test tiers

| Marker | When to use |
|--------|-------------|
| `@pytest.mark.unit` | No `processing.run()` calls — fast, no QGIS Processing needed |
| `@pytest.mark.integration` | Calls `processing.run()` — requires QGIS with Processing initialized |
| `@pytest.mark.edge_case` | Boundary / degenerate inputs |
| `@pytest.mark.performance` + `@pytest.mark.slow` | Time/memory bounds on large datasets (not currently used — see `docs/test-strategy.md`) |

See [`docs/test-strategy.md`](test-strategy.md) for the full tier taxonomy,
coverage targets, module-to-test mapping, and gap backlog — it is the
authoritative reference; consult it before writing a new test.

`processor.py`'s ATKIS mapping/reprojection/clipping logic is covered by
`test/test_processor.py` (unit + integration + edge-case tiers). The
end-to-end `process_atkis` tests run against real ATKIS/ALKIS data in
`Testdaten/` (not tracked in `.gitignore`'s "Test Artefakte" section on
purpose) and are automatically skipped if that data is absent from the
checkout.

### Running tests locally on Windows

The QGIS-bundled Python interpreter sets up `sys.path`/env vars that a bare
system Python does not:

```bash
"C:\Program Files\QGIS 3.40.0\bin\python-qgis.bat" -m pytest test/ -v
```

---

## Related Files

| File | Content |
|------|---------|
| [`docs/README.md`](README.md) | Full plugin documentation, including the relationship to IBTool |
| [`docs/CHANGELOG.md`](CHANGELOG.md) | Version history |
| [`docs/test-strategy.md`](test-strategy.md) | Test philosophy, tier taxonomy, coverage targets, module-to-test mapping, gap backlog |
| [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) | Tactical test rules: geometry checks, QGIS NULL handling, test structure |
| [`ai/core/qgis-api-rules.md`](../ai/core/qgis-api-rules.md) | QGIS API compatibility and Processing initialization rules |
| [`ai/core/release-conventions.md`](../ai/core/release-conventions.md) | Release invariants |
| [`ci/qgis_plugin_validate.py`](../ci/qgis_plugin_validate.py) | Plugin structure validator |
