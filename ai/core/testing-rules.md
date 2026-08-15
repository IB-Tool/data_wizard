# Testing Rules

> For the full test strategy - tier definitions, coverage targets, module mapping, and gap backlog - see [`docs/test-strategy.md`](../../docs/test-strategy.md). This file contains the tactical rules (geometry checks, framework, structure) that apply to every test.

## Before Every Code Change

1. **Understand existing logic**: Read the relevant code before making changes
2. **Run tests**: Existing tests must pass before and after the change
3. **No regression**: No existing functionality may break due to changes

## Test Framework

- **pytest** as the test framework
- Tests reside in `test/` following the pattern `test_*.py`
- `conftest.py` configures the test environment (`sys.path` only - no QGIS imports, see below)
- `test/utilities.py`'s `get_qgis_app()` creates the QGIS singleton **and** calls `Processing.initialize()` - call it once per test module before importing anything from `data_wizard`
- Docker environment for consistent QGIS test execution in CI

## Test Execution

```bash
# Docker (recommended - consistent environment)
docker build -t qgis-plugin-test .
docker run --rm qgis-plugin-test

# Local (requires QGIS 3.40 installation)
python-qgis.bat -m pytest test/ -v      # Windows, QGIS-bundled interpreter
pytest test/ -v                          # if QGIS python env is already active

# Single test
pytest test/test_processor.py -v

# Unit tests only (no Docker, no Processing needed beyond QGIS itself)
pytest test/ -m unit -v
```

## conftest.py Rule

`conftest.py` must **never** import `qgis.*`. It only manipulates `sys.path` (adding the plugin's parent directory so `import data_wizard.processor` resolves). Importing QGIS in `conftest.py` triggers a circular import via `qgis.utils._import` before QGIS itself is initialized. QGIS setup happens per-test-module via `test/utilities.py`'s `get_qgis_app()`, called **before** any `data_wizard.*` or `.layer_factories` import:

```python
from .utilities import get_qgis_app
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
from .layer_factories import make_polygon_layer, add_feature_to_layer
from data_wizard.processor import detect_hu_function_field
```

## Testing Geometry Operations

Include the following checks for every geometry operation:

### Validity Check

```python
result_geom = result_feature.geometry()
assert not result_geom.isNull(), "Geometry must not be null"
assert not result_geom.isEmpty(), "Geometry must not be empty"
assert result_geom.isGeosValid(), "Geometry must be valid"
```

### Multipart Check

```python
if expect_singlepart:
    assert not result_geom.isMultipart(), "Expected singlepart geometry"
```

Note: `_write_gpkg`'s `geometry_type` parameter determines the writer's declared
WKB type independently of `force_singlepart`. When testing `force_singlepart=True`
against `_write_gpkg` directly, pass the **singlepart** target type (e.g.
`QgsWkbTypes.Polygon`, not `QgsWkbTypes.MultiPolygon`) - matching how
`_process_rn`/`_process_aux` actually call it with `QgsWkbTypes.LineString`.

### Feature Count

```python
assert result_layer.featureCount() > 0, "Result must contain features"
```

## QGIS Attribute NULL vs. Python None

A `NULL` QGIS feature attribute (`feat[idx]` for an unset field) is a `QVariant`
sentinel (`qgis.core.NULL`), **not** Python `None` - `value is None` is `False`
for it, `value == NULL` is `True`. Any test (or production code) that checks
`value is None` to detect a missing attribute is checking the wrong thing; see
the documented `_add_function_field_copy` bug in
[`docs/test-strategy.md`](../../docs/test-strategy.md#gap-analysis).

## Error Messages

- **Never silently swallow errors**: Every expected exception must be tested
- Test that error messages are meaningful (`pytest.raises(ValueError, match="...")`)
- Test edge cases: empty layers, null geometries, wrong CRS, non-overlapping study areas

## Test Structure

```python
class TestFunctionName:
    """Tests for module.function_name."""

    @pytest.mark.unit
    def test_normal_case(self):
        """Standard case with valid inputs."""
        result = function_name(valid_input)
        assert result is not None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_empty_input(self):
        """Behavior with empty input layer."""
        # Expect defined behavior, not a crash

    @pytest.mark.unit
    def test_invalid_geometry(self):
        """Behavior with invalid geometry."""
        # Expect a raised, meaningful exception
```

## Known Bugs Found by Tests

When a test reveals a real bug in production code rather than a test-authoring
mistake, do **not** write the test to assert the buggy behavior as correct.
Instead:

1. Write the test asserting the *intended* behavior (from the docstring/contract).
2. Mark it `@pytest.mark.xfail(reason="...", strict=True)` with a reason that
   explains the bug and points to the fix.
3. Document the bug in `docs/test-strategy.md` → Gap Analysis.
4. `strict=True` ensures the marker itself starts failing the suite (as an
   "unexpectedly passing" XPASS) once someone fixes the bug and forgets to
   remove the marker - it cannot silently rot into a stale exclusion.

## Coverage

- New features must be covered by tests
- Coverage reports via `pytest --cov --cov-report=html` (needs `pytest-cov`,
  see `requirements-test.txt`)
- CI pipeline checks tests automatically on every push (Docker) and keeps
  `coverage.xml`/`htmlcov/` as a downloadable artifact - see
  `docs/test-strategy.md` → Justified Exclusions for why there is no Codecov upload
