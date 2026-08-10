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

Test coverage is measured with `pytest-cov` and uploaded to [Codecov](https://codecov.io) on every CI run. The `coverage.xml` file is written by the container into the volume-mounted workspace. Container-absolute paths (`/plugins/data_wizard/`) are stripped before upload so Codecov can map lines back to the repository.

> **Note:** unlike IBTool and ibtoolpartion, this repository does not yet have
> a Codecov project set up — `CODECOV_TOKEN` must be added as a repository
> secret before the coverage upload step will succeed.

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
| `@pytest.mark.unit` | No `processing.run()` calls — fast, no QGIS needed |
| `@pytest.mark.integration` | Calls `processing.run()` — requires QGIS |
| `@pytest.mark.edge_case` | Boundary / degenerate inputs |

The existing tests (`test_data_wizard_dialog.py`, `test_qgis_environment.py`,
`test_resources.py`, `test_translations.py`, `test_init.py`) come from the
QGIS Plugin Builder scaffold. They are not yet marked with these tiers —
that's a good first contribution if you're adding tests for `processor.py`'s
ATKIS mapping/reprojection/clipping logic, which is currently untested.

---

## Related Files

| File | Content |
|------|---------|
| [`docs/README.md`](README.md) | Full plugin documentation, including the relationship to IBTool |
| [`docs/CHANGELOG.md`](CHANGELOG.md) | Version history |
| [`ai/core/release-conventions.md`](../ai/core/release-conventions.md) | Release invariants |
| [`ci/qgis_plugin_validate.py`](../ci/qgis_plugin_validate.py) | Plugin structure validator |
