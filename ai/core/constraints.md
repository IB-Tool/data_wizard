# Constraints

Binding rules for all code changes in the data_wizard project.

For release-specific constraints (metadata.txt, LICENSE, ZIP packaging, CI),
see [release-conventions.md](release-conventions.md).

## Language

> **Deviation from IB-Tool 3:** IB-Tool 3's own `ai/core/constraints.md`
> mandates English for all code comments/docstrings, with German reserved for
> UI strings and end-user log output. `processor.py` in this repository does
> not follow that split - its docstrings, comments, and `log()` messages are
> German throughout, while identifiers are English. This is the actual,
> current convention here, not an oversight to silently "correct" by copying
> IB-Tool 3's rule - see the Testplan-data_wizard-ibtoolpartion.md
> "Nebenbefund #4" note, which flags the inconsistency across the three
> plugins as a separate decision to make deliberately, not as part of adding
> tests/docs. The table below documents what this repository actually does.

| Content Type | Language | Examples |
|---|---|---|
| Code identifiers (function/class/variable names) | **English** | `process_atkis`, `_reproject_if_needed`, `target_crs` |
| `processor.py` docstrings, comments, `log()` messages | **German** (established convention - do not silently rewrite to English) | `"""Reprojiziert layer nach target_crs..."""` |
| `data_wizard.py`, `data_wizard_dialog.py` | **English** (already English throughout) | |
| Test files (`test/`) | **English** (docstrings, comments, assertions) | matches this repo's tests and IB-Tool 3's convention |
| Developer documentation (`ai/`, `docs/`) | **English** | All markdown files for AI/developer context |
| Commit messages, CHANGELOG (technical) | **English** | |
| UI strings (via `QCoreApplication.translate()`) | **English** source string, translated via `i18n/*.ts` (German provided) | Dialog labels, message bar text |

When modifying existing code, match the language already used in the
function/file you are editing. Do not mix German and English within the same
docstring or the same log-message call.

## Interface Access

- **No direct access to `iface`** outside the main class (`data_wizard.py`)
  and dialog (`data_wizard_dialog.py`)
- `processor.py` never receives `iface` as a parameter - it communicates
  progress via the optional `feedback`/`log` callback and results via return
  values / files written to `target_dir`

## Variables and State

- **No global variables** in `processor.py` - all state is passed as
  parameters
- `processor.py` functions must be **stateless** and must not modify their
  input layers (`_write_gpkg` reads from `input_layers` but never edits them;
  `_add_function_field_copy` is the one documented exception - it edits the
  layer it receives in place via `startEditing()`/`commitChanges()`, which is
  why callers `materialize()` a fresh copy first)

## Documentation

- **Every new function** gets a docstring (German for `processor.py`, English
  elsewhere - see Language above)
- **Every new class** gets a docstring describing its purpose
- Parameters with non-obvious meaning are explained in the docstring
  (`processor.process_atkis`'s parameter list is the reference example)

## Paths and Configuration

- **No hardcoded paths** - all paths via parameters (`source_dir`, `hu_path`,
  `target_dir`, `study_area_path`)
- Temporary files via `QgsProcessing.TEMPORARY_OUTPUT`

## Numeric Values

- **No magic numbers** without a named constant - e.g. `FUNCTION_CODE_PATTERN`,
  `HU_FUNCTION_FIELDS` at module level in `processor.py`, not inlined into
  the functions that use them

## Error Handling

- `_check_cancel(task)` before every expensive step (layer prep,
  `processing.run()`, the GeoPackage write loop) in a cancellable pipeline
- Raise specific exceptions (`FileNotFoundError`, `ValueError`, `IOError`) with
  a message that includes the offending path/value - never a bare `Exception`
  except for the deliberate cancellation signal (`"Verarbeitung abgebrochen."`)
- Do not catch and discard exceptions silently - `_AtkisTask.run()` is the one
  place that catches broadly (`except Exception as e`), because it is a
  `QgsTask` boundary that must return `False` instead of crashing the
  background thread; it stores the exception on `self.exception` and logs it

## Strings

- All user-visible strings in `data_wizard.py`/`data_wizard_dialog.py` must be
  translatable via `self.tr(...)` / `QCoreApplication.translate(...)`
- `processor.py`'s `log()` messages are not translated (developer/log-file
  audience, not the plugin's translated UI)
