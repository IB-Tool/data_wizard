# Test Strategy

This document is the single authoritative reference for **why** the test suite is structured the way it is, **how** to choose the right test tier for a new test, and **where** known coverage gaps exist. Consult it before writing any new test or assessing CI failures.

This plugin follows the same test-strategy structure as its sibling
[IB-Tool 3](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/test-strategy.md),
scaled down to data_wizard's single-module scope (`processor.py`,
`data_wizard.py`, `data_wizard_dialog.py`).

**What this document is not:**
- A tutorial on pytest syntax - see the pytest documentation.
- A list of tactical rules for geometry checks or test structure - see [`ai/core/testing-rules.md`](../ai/core/testing-rules.md).

---

## Test Philosophy

Four principles explain the structural decisions made in this project:

### Geometry bugs produce plausible-looking wrong results

A dissolve that silently fails returns an empty or null geometry - not an exception. A polygon that self-intersects still renders on screen. This is why **geometry validity checks are mandatory** for every test that touches a layer-returning function. Checking only `featureCount > 0` is insufficient.

### `processing.run()` is the unit/integration boundary

The demarcation between unit and integration tests is not "uses QGIS API" but specifically **whether `processing.run()` is called**. `_load_shp`, `_write_gpkg`, `_add_function_field_copy`, and `detect_hu_function_field` use `QgsVectorLayer`/`QgsFeature`/`QgsVectorFileWriter` directly and are unit-tested without a Processing environment. `_reproject_if_needed`, `_clip_if_needed`, `_prepare_clip_mask`, `_process_hu/_rn/_aux`, and `process_atkis` delegate to `native:*` algorithms and require an initialized Processing environment.

### Error paths are first-class citizens

Empty layers, null geometries, mismatched CRS, and non-overlapping study areas are not accidents - they are guaranteed inputs when processing real ATKIS extracts. Every error-handling branch in `processor.py` must be tested explicitly, not just the happy path.

### Tests document expected behavior

Constants and thresholds should be visible in test docstrings or assertions, not buried in source code. A test like `assert status == 'auto'` without explanation is opaque; a test with `"""Returns ('auto', name) when exactly one field matches the pattern."""` is documentation.

---

## Test Taxonomy

Five tiers are used (matching `pytest.ini`). Every test must carry exactly one primary tier marker (`unit` or `integration`) and may additionally carry `edge_case`, or `performance` + `slow` together.

### Unit (`@pytest.mark.unit`)

**Definition:** No call to `processing.run()`. May instantiate `QgsVectorLayer("…memory")`, `QgsFeature`, `QgsGeometry`, or `QgsVectorFileWriter` directly.

**Execution:** Runs anywhere Python + QGIS libraries are installed (`python-qgis.bat -m pytest test/ -m unit`). Does not require Docker.

**Example targets:** `detect_hu_function_field`, `_check_cancel`, `_load_shp`, `_add_function_field_copy`, `_write_gpkg`, `scripts/create_release_zip.py`, dialog getters, plugin validation logic.

### Integration (`@pytest.mark.integration`)

**Definition:** Calls `processing.run()` at least once, directly or indirectly through the function under test.

**Execution:** Requires Docker (`docker run --rm qgis-plugin-test`) or a local QGIS installation with the Processing plugin initialized (`Processing.initialize()` - see `test/utilities.py`).

**Example targets:** `_reproject_if_needed`, `_clip_if_needed`, `_prepare_clip_mask`, `_process_hu`, `_process_rn`, `_process_aux`, `process_atkis`.

### Edge case (`@pytest.mark.edge_case`)

**Definition:** Cross-cutting tag combined with `unit` or `integration`. Marks a test that exercises a boundary or degenerate input.

**Catalog of mandatory edge cases for `processor.py`:**
- HU without a function-code field and no `function_field` override (warning, no abort)
- `veg03_f` with no feature matching `OBJART` 43005/43006 (empty intermediate layer, no crash)
- `task.isCanceled()` becoming true mid-run (defined exception, not a hang or silent partial write)
- Study area without any overlap with the ATKIS extent (empty result, not an error)
- Input layer in a different CRS than `ver01_l` (automatic reprojection)
- CRS mismatch between `_write_gpkg` input layers (`ValueError`, not silently wrong geometry)
- Null/empty geometries in `_write_gpkg` input (skipped, not written as broken features)

### Performance (`@pytest.mark.performance` + `@pytest.mark.slow`)

**Definition:** Exercises time or memory bounds on realistically large datasets. Always carries both markers together.

**Status:** Not currently used. `process_atkis`'s real end-to-end test already runs against the full `Testdaten/` ATKIS/ALKIS extract (11,207 building features, ~2,100 line/polygon ATKIS features combined) and completes in ~2 seconds locally - there is no dataset in this repository large enough to need a dedicated slow tier yet. See Gap Analysis.

---

## Coverage Targets

Per-file floor values, not aspirational goals. Coverage below these thresholds signals a gap that should be addressed before merging new features.

| File | Target | Rationale |
|---|---|---|
| `processor.py` | 85% | Core ATKIS transformation logic; the plugin's entire reason to exist |
| `data_wizard.py` | 70% | Plugin glue + validation; `classFactory`/GUI wiring excluded (see Justified Exclusions) |
| `data_wizard_dialog.py` | 70% | Signal wiring excluded, getters/detection-resolution logic covered |
| `scripts/create_release_zip.py` | 90% | Pure Python, no QGIS dependency, cheap to cover fully |
| **Overall project** | **75%** | |

---

## Test Data and Fixture Strategy

### Shared vs. per-file factories

**`conftest.py`** handles only pytest infrastructure: it adds the plugin's parent directory to `sys.path` so `import data_wizard.processor` resolves the same way locally and in the container (`PYTHONPATH=/plugins`). It does **not** provide pytest fixtures or import QGIS modules - doing so would trigger a circular import error via `qgis.utils._import` before QGIS is initialized.

**`test/layer_factories.py`** is the canonical home for shared layer and geometry factory helpers. Import it **after** calling `get_qgis_app()`:

```python
from .utilities import get_qgis_app
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import (
    make_polygon_layer, make_line_layer, make_point_layer,
    make_square_geom, add_feature_to_layer,
    write_layer_as_shp, write_layer_as_gpkg,
)
```

`write_layer_as_shp`/`write_layer_as_gpkg` exist because `processor._load_shp`, `detect_hu_function_field`, and `_prepare_clip_mask` all take file **paths**, not `QgsVectorLayer` objects - most `processor.py` unit tests build an in-memory layer and then write it to `tmp_path` before calling the function under test.

### Real ATKIS/ALKIS Testdaten

`Testdaten/ATKIS Basis DLM dataset/` (the 7 layers `processor.process_atkis` reads: `ver01_l`, `ver02_l`, `ver03_l`, `veg02_f`, `veg03_f`, `gew01_f`, `gew01_l`) and `Testdaten/ALKIS Gebäude/GebauedeBauwerk.shp` are real, small ATKIS Basis-DLM / ALKIS extracts checked into the repository (untracked by `.gitignore` deliberately - see `.gitignore` "Test Artefakte" section, which only excludes generated `*.gpkg`, not the source `Testdaten/`). `test/test_processor.py`'s `TestProcessAtkis` class runs `process_atkis` end-to-end against this data and is automatically skipped (`requires_atkis_testdaten`) if the directory is absent, so the suite still runs (minus that one class) on a fresh checkout without the data.

### Processing initialization (local runs)

Unlike `QgsApplication.initQgis()`, the `native:*` algorithm provider is **not** auto-registered - it requires the Processing Python plugin's own `Processing.initialize()`. `test/utilities.py`'s `get_qgis_app()` calls this once, immediately after `initQgis()`, so every test file that calls `get_qgis_app()` gets a working `processing.run()` for free. Without this, every `@pytest.mark.integration` test fails with `Algorithm native:... not found`, regardless of whether `QgsApplication` initialized successfully. This is a deliberate deviation from IB-Tool 3's `test/utilities.py`, which does not do this - necessary here because `processor.py`'s pipeline uses `processing.run()` far more heavily than a typical IB-Tool 3 geometry tool.

### Fixture scope rules

| Fixture type | Scope |
|---|---|
| `QgsVectorLayer` instances | `function` - layers are mutable; reuse across tests causes interference |
| `QgsApplication` (QGIS singleton) | `session` (via `test/utilities.py`'s module-global `QGIS_APP`) - expensive to initialize, safe to share |
| `QgsCoordinateReferenceSystem` | module-level constant (`CRS_25833`, `CRS_4326` in `test_processor.py`) - immutable value object |
| File paths (`pathlib.Path`) | `tmp_path` (pytest built-in) - fresh per test, auto-cleaned |

---

## Module-to-Test Mapping

| Production module | Test file | Tests | Dominant tier | Notable gaps |
|---|---|---|---|---|
| `processor.py` | `test_processor.py` | 39 (38 + 1 xfail) | unit + integration | See Gap Analysis (NULL-copy bug) |
| `data_wizard.py` | `test_data_wizard.py` | 30 | unit | Full `run()` happy path (task actually scheduled via `QgsApplication.taskManager()`) not covered - see Justified Exclusions |
| `data_wizard_dialog.py` | `test_data_wizard_dialog.py` | 16 | unit | `_browse_*` file-dialog callbacks not covered (native `QFileDialog` calls - see Justified Exclusions) |
| `scripts/create_release_zip.py` | `test_create_release_zip.py` | 40 | unit | None significant |
| `__init__.py` (`classFactory`) | `test_init.py` | 1 | smoke | `classFactory()` with a live `iface` - see Justified Exclusions |
| — | `test_qgis_environment.py` | 2 | smoke | QGIS init and Processing available |
| — | `test_resources.py` | 1 | smoke | Plugin resources compiled |
| — | `test_translations.py` | 1 | smoke | Translation file present |
| **Total** | | **130** (129 + 1 xfail) | | |

---

## Decision Guide for New Tests

Use this checklist when adding a new test.

### Step 1 - Identify what changed

- New function or class → write a test for its normal behavior + at least one edge case.
- Bug fix → write a regression test that reproduces the original bug, then verifies the fix.
- Edge case discovered during review → add to the existing test class under `@pytest.mark.edge_case`.

### Step 2 - Choose the tier

```text
Does the function under test call processing.run()?
├── No  → @pytest.mark.unit
└── Yes → @pytest.mark.integration
            (also requires Docker / local QGIS with Processing.initialize())

Is this testing a boundary / degenerate input?
└── Yes → additionally add @pytest.mark.edge_case
```

### Step 3 - Choose the test file

Always add to `test_{module_name}.py` where `module_name` is the file under test without extension.

### Step 4 - Mandatory geometry checks

Every test for a function that returns a `QgsVectorLayer` must include:

```python
assert result_layer is not None
for feat in result_layer.getFeatures():
    geom = feat.geometry()
    assert not geom.isNull(),   "Geometry must not be null"
    assert not geom.isEmpty(),  "Geometry must not be empty"
    assert geom.isGeosValid(),  "Geometry must be GEOS-valid"
```

### Step 5 - Write a one-line docstring

Every test method must have a docstring in the imperative mood describing what behavior it verifies:

```python
def test_returns_auto_for_single_matching_field(self):
    """Returns ('auto', name) when exactly one field matches the pattern."""
```

---

## Gap Analysis

### Known bug found while writing tests (Priority 1)

| Gap | Detail | Action |
|---|---|---|
| `_add_function_field_copy` does not preserve `NULL` | `value is None` never matches a QGIS `NULL` attribute (it is a `QVariant` sentinel, not Python `None`), so a `NULL` source value is copied into the target field as the literal string `"NULL"` instead of staying `NULL`. Reproduced in `test_processor.py::TestAddFunctionFieldCopy::test_null_source_values_are_copied_as_null_not_string`, currently marked `xfail(strict=True)` so the suite stays green while documenting the discrepancy. | Fix `processor.py` to compare against `qgis.core.NULL` (e.g. `value in (None, NULL)`), then remove the `xfail` marker - the test will start passing and `strict=True` will catch it if the marker is forgotten. |

### Other gaps (Priority 2)

| Gap | Action |
|---|---|
| No performance/slow-tier test | Not yet warranted - see Test Taxonomy → Performance. Revisit if a much larger `Testdaten/` extract is added or `process_atkis` runtime becomes a concern. |
| `Data_Wizard.run()` happy path (real task scheduled via `QgsApplication.taskManager()`) | Not covered - deliberately, to avoid a real background `QgsTask` executing during the unit-test run (flaky/slow). Covered indirectly: `_AtkisTask.run()`/`.finished()` are tested directly, and every validation branch that would prevent scheduling is tested. |
| `data_wizard_dialog.py` `_browse_*` methods | Not covered - they are three-line wrappers around `QFileDialog.getExistingDirectory`/`getOpenFileName` static calls; the QGIS API rule against relying on native OS file dialogs in headless CI applies (see `ai/core/qgis-api-rules.md`). |

---

## Justified Exclusions

Documented decisions that **are not gaps** - known exclusions with stated reasons.

| Module / function | Reason for exclusion |
|---|---|
| `__init__.py` `classFactory()` beyond the existing smoke test | Requires a live `iface` object provided by the running QGIS application. |
| `data_wizard_dialog.py` `_browse_source`/`_browse_hu`/`_browse_studyarea`/`_browse_target` | Thin wrappers around native `QFileDialog` static methods; no branching logic of their own beyond "if a path was chosen, set the line edit" (indirectly exercised by the getter tests once a value is present). |
| `Data_Wizard.run()`'s `QgsApplication.taskManager().addTask(...)` call itself | Scheduling a real `QgsTask` would run `process_atkis` in a background thread during the test session - the same logic is exhaustively covered by calling `_AtkisTask.run()`/`.finished()` directly and synchronously. |
| Codecov upload | No Codecov project exists for this repository (`CODECOV_TOKEN` not configured). Coverage is measured locally and in Docker via `pytest-cov` and kept as a downloadable CI artifact (`coverage.xml`, `htmlcov/`) instead of being uploaded to an external service. See `docs/contributing.md` → Coverage Reporting. |
| `resources.py`, `ui_*.py` | Generated files (see `.coveragerc`). |

---

## CI/CD

For the full CI/CD pipeline description, Docker environment setup, and local commands, see [docs/contributing.md](contributing.md).

Quick reference for common test runs:

```bash
# Unit tests only (no QGIS Processing required beyond QGIS itself)
pytest test/ -m unit -v

# Full run (requires Docker or local QGIS 3.40 with Processing)
docker run --rm qgis-plugin-test

# Coverage report
pytest test/ --cov --cov-report=html

# Single module
pytest test/test_processor.py -v
```

---

## Related Files

| File | Content |
|------|---------|
| [`docs/contributing.md`](contributing.md) | CI/CD pipeline, Docker environment, code linting |
| [`ai/core/testing-rules.md`](../ai/core/testing-rules.md) | Tactical rules: geometry checks, test structure, framework conventions |
