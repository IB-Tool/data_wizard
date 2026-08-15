---
description: Use this skill when the user asks to write, create, or add tests for a module, function, or class in data_wizard - for example "schreib Tests für processor", "write tests for detect_hu_function_field", "add test coverage for X", "fehlende Tests ergänzen". Invoke automatically whenever a testing task is identified for this QGIS plugin project.
---

# /write-tests — Write Tests for a data_wizard Module

Write pytest tests for the module: **$ARGUMENTS**

Follow these steps in order. Do not skip any step.

---

## Step 1 — Read the target module

Search for `$ARGUMENTS` in these locations (in order):
- `$ARGUMENTS.py` (root level - `processor.py`, `data_wizard.py`, `data_wizard_dialog.py`)
- `scripts/$ARGUMENTS.py`

Read the file completely. Identify:
- All public functions/classes and their parameters and types
- Return values and their types
- Error conditions and how they are handled (which exceptions, with what message)
- Any calls to `processing.run()` — these determine the tier (see Step 3)
- Any `log`/`feedback` and `task` (cancellation) parameters — every
  processor.py function that has these needs at least one test for the
  cancel-mid-run path and the log-callback-invoked path

## Step 2 — Check for existing tests

Search `test/` for an existing test file for `$ARGUMENTS`:
- `test/test_$ARGUMENTS.py` (snake_case variant)
- Any file matching `test_*$ARGUMENTS*`

If a test file **exists**: extend it, do not replace it. Match its existing
class/fixture structure.
If no test file exists: create `test/test_<snake_case_name>.py`.

## Step 3 — Consult project rules (mandatory)

Read **all** of these files before writing any code:

1. `docs/test-strategy.md` — tier definitions, coverage targets, module mapping, gap backlog (authoritative source)
2. `ai/core/testing-rules.md` — tactical rules: geometry checks, QGIS NULL handling, test structure
3. `ai/core/qgis-api-rules.md` — QGIS API compatibility rules, Processing initialization
4. `ai/core/constraints.md` — language and naming rules

Also read:
- `test/utilities.py` — QGIS app initialisation + Processing.initialize()
- `test/conftest.py` — sys.path setup (no fixtures, no QGIS imports)
- `test/layer_factories.py` — shared layer/geometry factory helpers

## Step 4 — Write the test file

### Tier decision

```
Does the function under test call processing.run()?
├── No  → @pytest.mark.unit
└── Yes → @pytest.mark.integration  (requires Docker / local QGIS with Processing.initialize())

Is this a boundary or degenerate input?
└── Yes → additionally add @pytest.mark.edge_case
```

### Required structure

```python
import pytest
from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsField, QgsGeometry,
    QgsCoordinateReferenceSystem, QgsPointXY, QgsWkbTypes, NULL,
)
from qgis.PyQt.QtCore import QVariant

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from .layer_factories import (
    make_polygon_layer, make_line_layer, make_point_layer,
    make_square_geom, add_feature_to_layer,
    write_layer_as_shp, write_layer_as_gpkg,
)

from data_wizard.<module_name> import <function_or_class>


class Test<Subject>:
    """Tests for <module_name>.<function_or_class>."""

    @pytest.mark.unit
    def test_normal_case(self):
        """<Imperative description of what this test verifies.>"""
        ...
```

`QgsField(name, type, len=...)` — always pass `type` as `QVariant.String` (or
the correct `QVariant` constant) explicitly, and `len` as a **keyword**
argument. `QgsField(name, 10)` silently creates a field with an invalid type
enum, which OGR then drops on write — a common, hard-to-spot mistake.

### Required geometry assertions (mandatory after every geometry-returning operation)

```python
assert result_layer is not None
for feat in result_layer.getFeatures():
    geom = feat.geometry()
    assert not geom.isNull(),   "Geometry must not be null"
    assert not geom.isEmpty(),  "Geometry must not be empty"
    assert geom.isGeosValid(),  "Geometry must be GEOS-valid"
```

### QGIS NULL vs. Python None

When testing attribute values that may be unset, remember `NULL` (imported
from `qgis.core`) is the correct sentinel to compare against — `value is None`
never matches a QGIS `NULL` attribute. See `ai/core/testing-rules.md`.

### Mandatory test cases (minimum, per function)

1. **Normal case** — valid input; check return value, feature count, geometry validity
2. **At least one error path** — invalid input that should raise a specific,
   documented exception (`FileNotFoundError`/`ValueError`/`IOError`) — assert
   the exception type and, where the message is meaningful, match on it
3. At least one **domain-specific edge case** (`@pytest.mark.edge_case`) — see
   the catalog in `docs/test-strategy.md` → Test Taxonomy → Edge case
4. If the function takes `task=None` — a cancel-mid-run test
   (`task.isCanceled()` becomes `True` after the first check)

### If a test reveals a bug in the production code

Do not write the test to assert the buggy behavior. Write it to assert the
*intended* behavior, mark it `@pytest.mark.xfail(reason="...", strict=True)`
explaining the bug, and add it to `docs/test-strategy.md` → Gap Analysis. See
`ai/core/testing-rules.md` → "Known Bugs Found by Tests".

### Docstring rule (mandatory)

Every test method must have a one-line docstring in the imperative mood:

```python
def test_writes_valid_hu_gpkg(self):
    """Writes HU.gpkg with valid MultiPolygon geometries and preserved fields."""
```

## Step 5 — Run the tests

```bash
python-qgis.bat -m pytest test/test_<module_name>.py -v --tb=short   # Windows
pytest test/test_<module_name>.py -v --tb=short                       # QGIS env already active
```

Fix failures before proceeding — do not report a test file as done with
failing tests, and do not weaken an assertion just to make it pass without
understanding why it failed first (see "If a test reveals a bug" above).

## Step 6 — Output

Report:
1. Path of the created/modified test file
2. List of test methods written and what each covers
3. Which tier markers were applied and why
4. Any assumptions made about expected behavior
5. Any bugs found and marked `xfail`, with a pointer to the Gap Analysis entry
