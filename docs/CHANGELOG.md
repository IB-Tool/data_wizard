# Changelog

All notable changes to Data Wizard will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## Unreleased

### Added
- `Dockerfile`, `ci/qgis_plugin_validate.py`, `scripts/create_release_zip.py` — Docker-based test execution and release ZIP building, mirroring IBTool's and ibtoolpartion's setup.
- `.github/workflows/ci.yml` (Docker-based tests + Codecov coverage) and `qgis-plugin-ci.yml` (flake8, bandit, detect-secrets, structure validation).
- `pytest.ini`, `requirements-test.txt`, `.flake8`, `.bandit` — test and lint configuration.
- `docs/contributing.md` — development setup, CI/CD pipeline, test structure, and release process, matching the other two IB-Tool plugins.
- `ai/core/release-conventions.md` — release invariants shared with IBTool and ibtoolpartion.

### Fixed
- `metadata.txt`: replaced placeholder `tracker`/`repository`/`homepage` URLs (`http://bugs`, `http://repo`, `http://homepage`) with the actual repository URLs; removed a stray unescaped line that was silently parsed as a bogus `category of the plugin` key; added a `changelog` entry (previously commented out).

---

## 0.1 — 2026-03-01

### Added
- Initial project structure: plugin entry point, dialog, ATKIS-to-HU/RN/Aux processor, i18n, test scaffold.
- `docs/README.md`: full documentation with cross-references to IBTool's own documentation.
