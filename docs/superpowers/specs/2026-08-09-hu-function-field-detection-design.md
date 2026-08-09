# HU Function-Field Detection & Copy — Design Spec

**Date:** 2026-08-09

## Context

`input-data.md` requires the HU (building footprints) layer to carry the
ATKIS function code in one of three field names: `fkt`, `gfkzshh`, or
`funktion`. The current `data_wizard` implementation (see
`docs/superpowers/specs/2026-08-09-data-preparation-automation-design.md`)
only *checks* for these names on the user-selected building file and logs a
non-blocking warning if none is found — it never attempts to locate or fix
a misnamed field.

In practice the user's building source files sometimes carry the function
code under a different column name. Goal: when none of the three expected
names is present, have the plugin locate the column that actually holds
the function codes and add a copy of it under the expected name
(`funktion`), so IBTool's own field lookup (`fkt`/`gfkzshh`/`funktion`)
succeeds without the user having to rename anything by hand in QGIS first.

## Decisions (from user clarification)

- **Detection strategy**: content-based heuristic first (scan sampled
  field values for the ATKIS function-code pattern, e.g. `31001_1000`),
  falling back to a manual dropdown picker only when the heuristic result
  is ambiguous (no match, or more than one column matches). The pattern is
  checked against the specific, known ATKIS object-art code for buildings
  (`31001`, i.e. `AX_Gebaeude` — confirmed via
  `basis-dlm-aaa_ebenen_inhalt.csv` in the project root), not a generic
  "5 digits" shape, to avoid false positives from unrelated coded fields.
- **Trigger timing**: detection runs immediately when the user picks the
  building file via the file-picker button in the dialog (`_browse_hu`),
  not deferred to when processing starts.
- **Target field name**: always `funktion` — no user choice of target
  name.
- **Scope of trigger**: only the file-picker path runs detection; manually
  typing/editing the path in the line edit does not re-trigger it (matches
  the existing pattern where `source_dir`/`target_dir` are only validated,
  not schema-inspected, regardless of how they were entered). To prevent a
  detected field from a previous file selection being silently misapplied
  to a different, manually-typed path, any manual edit of the line edit
  invalidates the previously detected field.
- **Original column is preserved**: the plugin adds a *copy* under the
  correct name; it does not rename or remove the original column.

## Detection Algorithm

`detect_hu_function_field(hu_path, sample_size=50)` (new, in `processor.py`):

1. Load `hu_path` as a `QgsVectorLayer`. Invalid layer → `ValueError`
   (same convention as the rest of the module).
2. If any field name matches `fkt`/`gfkzshh`/`funktion` case-insensitively
   → return `('ok', None)` — nothing to do, matches current behavior.
3. Otherwise, scan up to `sample_size` features once (single pass, not
   once per field), collecting each field's non-null/non-empty values as
   strings.
4. A field *qualifies* as a candidate if it has at least one sampled value
   and **all** of its sampled values match `^31001_\d{4}` — the fixed
   ATKIS object-art code for buildings (`31001` = `AX_Gebaeude`, per
   `basis-dlm-aaa_ebenen_inhalt.csv`) followed by the 4-digit function
   sub-code, e.g. `31001_1000`; matching against the leading characters,
   consistent with `input-data.md`'s "only the first 10 characters are
   used for filter matching". This is deliberately narrower than a
   generic "5 digits_4 digits" shape, since `31001` is the one object-art
   code that can actually appear in a building layer's function-code
   field.
5. Exactly one qualifying field → `('auto', field_name)`.
6. Zero or more than one qualifying field → `('ambiguous', all_field_names)`
   — caller (the dialog) must resolve this with the user.

## Dialog Behavior (`data_wizard_dialog.py`)

- `_browse_hu`, after `self.lineEdit_hu.setText(path)`, calls
  `_resolve_hu_function_field(path)`.
- `_resolve_hu_function_field`:
  - Calls `detect_hu_function_field`. A `ValueError` (unreadable file) is
    shown as a `QMessageBox.warning` and the resolved field is cleared —
    processing time will hit the same "layer ungültig" error anyway if
    the path is truly bad, but the dialog surfaces it right away too.
  - `'ok'` → clears the stored field (nothing to copy).
  - `'auto'` → stores the detected field name.
  - `'ambiguous'` → shows `QInputDialog.getItem` with a
    "— kein Funktionscode-Feld / überspringen —" first entry (default
    selection) followed by all field names; stores the user's pick, or
    clears it if the user picks the skip entry or cancels the dialog.
- `self.lineEdit_hu.textChanged` is connected to a handler that clears the
  stored field whenever the text changes for any reason (including the
  `setText()` call inside `_browse_hu` itself — `_resolve_hu_function_field`
  runs *after* `setText()`, so the browse path still ends with the correct
  value stored; a manual edit that isn't followed by a fresh detection
  call is left with no stored field, falling back to the existing
  warning-only behavior).
- New getter: `get_hu_function_field()` → the stored field name or `None`.

## Processing (`processor.py`)

- New helper `_add_function_field_copy(layer, source_field_name,
  target_field_name, log=None)`:
  - Opens an edit session (`layer.startEditing()` — raises `ValueError` if
    it returns `False`).
  - Adds `target_field_name` as a new `QVariant.String` field (length 254)
    via `layer.dataProvider().addAttributes([...])` + `layer.updateFields()`.
  - Copies every feature's value from the source field index into the new
    field index via `layer.changeAttributeValue(...)` (`None` stays
    `None`; everything else is copied via `str(value)`).
  - Commits (`layer.commitChanges()` — raises `ValueError` if it returns
    `False`).
  - Returns the layer (same object, now with the extra field).
- `_process_hu` gains a `function_field=None` parameter:
  - The existing "no expected field present" check now also asks "and no
    `function_field` was resolved" before logging the warning — if a
    `function_field` was resolved, no warning is logged, since the plugin
    is about to fix it.
  - After `_prepare_layer` (reproject/clip), if the expected field is
    still absent and `function_field` is set, calls
    `_add_function_field_copy(layer, function_field, "funktion", log)`
    before handing the layer to `_write_gpkg` (which already picks up
    whatever fields the layer currently has via `keep_fields=True` — no
    change needed there).
- `process_atkis` gains a `hu_function_field=None` parameter, forwarded
  straight through to `_process_hu`.

## Wiring (`data_wizard.py`)

- `_AtkisTask.__init__` gains a `hu_function_field` parameter/attribute;
  `run()` passes it to `process_atkis(..., hu_function_field=self.hu_function_field)`.
- `Data_Wizard.run()` reads `hu_function_field = self.dlg.get_hu_function_field()`
  and passes it into the `_AtkisTask(...)` constructor alongside the
  existing four arguments.

## Error Handling

- Unreadable building file during dialog-time detection → `QMessageBox.warning`
  in the dialog (new — detection runs synchronously on the main thread, so a
  direct message box is safe here, unlike the background-task path).
- Edit-session failures in `_add_function_field_copy` → `ValueError`,
  caught the same way every other `processor.py` exception already is by
  `_AtkisTask.run()`'s broad `except Exception`.
- If detection was skipped or came back ambiguous-and-unresolved, behavior
  is unchanged from today: non-blocking log warning, HU.gpkg is still
  produced without a function-code field.

## Testing

Same constraint as the rest of `data_wizard`: no QGIS runtime available in
this environment. Verification is a syntax check (`py_compile`) plus a
manual QGIS pass: pick a building file whose function-code column is
named something other than `fkt`/`gfkzshh`/`funktion` and confirm (a) a
correctly-named column is auto-detected when unambiguous, (b) the dropdown
appears and works when it isn't, (c) `HU.gpkg` ends up with a `funktion`
column holding the same values as the original column, and (d) the
original column is still present, unmodified, alongside it.

## Out of Scope

- Renaming/removing the original column.
- Re-running detection when the HU path is edited by hand rather than via
  the file picker.
- Letting the user choose the target field name (always `funktion`).
- Any change to RN/AUX processing.
