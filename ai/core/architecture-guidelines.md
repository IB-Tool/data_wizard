# Architecture Guidelines

Guidelines for architectural decisions in the data_wizard project.

## Module Layout

data_wizard is intentionally a single-module plugin, not a package-of-packages
like IB-Tool-3:

- **`processor.py`** - all ATKIS transformation logic, no QGIS UI or `iface`
  access. Pure function pipeline: load → reproject/clip → transform → write.
- **`data_wizard.py`** - plugin entry point (`Data_Wizard` class), background
  task orchestration (`_AtkisTask`), and input validation. Talks to `iface`
  and `processor.py`, never the reverse.
- **`data_wizard_dialog.py`** - Qt dialog wrapper, thin getters/setters over
  the `.ui` form plus the HU function-field detection/selection flow (which
  itself delegates the actual detection to `processor.detect_hu_function_field`).

Do not introduce a `data_wizard_tools/`-style subpackage unless a second
independent processing pipeline is added - one file per responsibility is
still proportionate to this plugin's scope.

## Parameter Management

- **Avoid over-engineering**: no config classes for `processor.py`'s
  parameters - they are passed directly as function arguments
  (`source_dir`, `hu_path`, `target_dir`, ...)
- **Module-level constants for fixed contracts**: `HU_FUNCTION_FIELDS`,
  `FUNCTION_CODE_PATTERN` are defined once at the top of `processor.py`,
  not duplicated across functions
- **Single Source of Truth**: the seven ATKIS layer names
  (`ver01_l`/`ver02_l`/`ver03_l`/`veg02_f`/`veg03_f`/`gew01_f`/`gew01_l`) only
  ever appear as string literals inside the `_process_*` functions that load
  them - if this list needs to grow, promote it to a module-level tuple
  instead of adding a new inline literal

## Function Design

- **Small, composable steps**: `process_atkis` is an orchestrator that calls
  `_process_hu`/`_process_rn`/`_process_aux`, each of which calls shared
  helpers (`_prepare_layer`, `_load_shp`, `_write_gpkg`) - keep this shape
  when extending the pipeline rather than growing one function further
- **Stateless functions**: no module-level mutable state in `processor.py`;
  every function receives everything it needs as a parameter
- **Optional `log`/`feedback` callback, not a required logger dependency**:
  every `processor.py` function that reports progress takes an optional
  `log=None` parameter and guards calls with `if log:` - do not introduce a
  hard dependency on `QgsMessageLog` inside `processor.py` (that belongs in
  `data_wizard.py`'s `_AtkisTask.run()`, which is the only place adapting
  `feedback` to `QgsMessageLog.logMessage`)
- **Optional `task` parameter for cancellation**: every long-running
  `processor.py` function accepts `task=None` and calls `_check_cancel(task)`
  before each expensive step - preserve this signature shape when adding new
  processing steps

## Code Organization

- **No magic numbers**: constants at module level, named
  (`FUNCTION_CODE_PATTERN`, not an inline regex string)
- **Pragmatic refactoring**: `processor.py` is ~430 LOC across 12 functions -
  this is proportionate to the plugin's scope; do not split it into a
  package until it meaningfully grows beyond the ATKIS Basis-DLM → IBTool
  input pipeline it currently implements

## Testing Implications

Because `processor.py` has no `iface`/UI dependency, it is directly unit- and
integration-testable without mocking QGIS's plugin interface - see
`ai/core/testing-rules.md`. Keep new `processor.py` functions free of `iface`
access so this property is preserved; anything that needs `iface` belongs in
`data_wizard.py`.
