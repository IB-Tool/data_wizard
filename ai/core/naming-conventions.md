# Naming Conventions

## Python Identifiers

| Element | Convention | Example |
|---------|-----------|---------|
| Functions | `snake_case` | `detect_hu_function_field()`, `process_atkis()` |
| Private/internal functions | `_snake_case` (leading underscore) | `_load_shp()`, `_write_gpkg()`, `_check_cancel()` |
| Methods | `snake_case` | `dialog.get_source_dir()` |
| Classes | `PascalCase` | `Data_Wizard`, `Data_WizardDialog`, `_AtkisTask` |
| Module-level constants | `UPPER_SNAKE_CASE` | `HU_FUNCTION_FIELDS`, `FUNCTION_CODE_PATTERN` |
| Local variables | `snake_case` | `target_crs`, `clip_mask`, `veg03_f` |
| Modules | `snake_case` | `processor.py`, `data_wizard.py` |
| Test modules | `test_*.py` | `test_processor.py` |
| Test classes | `PascalCase`, `Test` + subject | `TestDetectHuFunctionField`, `TestWriteGpkg` |
| Test methods | `test_<behavior_under_test>` | `test_returns_ok_when_fkt_field_present` |

## Allowed Abbreviations

Established ATKIS/plugin-domain abbreviations that may be used without further explanation:

| Abbreviation | Meaning |
|-------------|---------|
| `hu` | Hausumringe (building footprints) - also the output file `HU.gpkg` |
| `rn` | Road network (Straßennetz) - output file `RN.gpkg` |
| `aux` | Auxiliary lines (Hilfslinien) - output file `AUX_L.gpkg` |
| `crs` | Coordinate Reference System |
| `geom` | Geometry |
| `id` | Identifier |
| `wkt` | Well-Known Text |
| `wkb` | Well-Known Binary |
| `atkis` | Amtliches Topographisch-Kartographisches Informationssystem (source data model) |
| `ver01_l`, `ver02_l`, `ver03_l`, `veg02_f`, `veg03_f`, `gew01_f`, `gew01_l` | Fixed ATKIS Basis-DLM layer names (from `basis-dlm-aaa_ebenen_inhalt.csv`) - never rename in code, they are file-system contract with `source_dir` |
| `dlg` | Dialog (e.g. `self.dlg`) |
| `iface` | QGIS Interface object |

All other terms must be spelled out.

## Layer/Variable Names in processor.py

- Raw ATKIS layers loaded from disk keep their ATKIS layer name as the
  variable name (`ver01_l`, `veg03_f`, ...) - do not rename them to something
  "friendlier"; the ATKIS name is the reference documentation
- Intermediate `processing.run()` results use a `p_` prefix + short
  description of the step, e.g. `p_veg02_dis` (dissolved), `p_veg02_lines`
  (polygons-to-lines) - see `_process_aux` for the pattern

## File Names

| Type | Convention | Example |
|------|-----------|---------|
| Plugin modules | `snake_case.py` | `processor.py`, `data_wizard_dialog.py` |
| Test modules | `test_*.py` | `test_processor.py` |
| Test infrastructure | `snake_case.py` | `layer_factories.py`, `utilities.py` |
| Configuration | `snake_case.*` | `pytest.ini`, `test_config.ini` |
| Documentation | `kebab-case.md` | `test-strategy.md`, `qgis-api-rules.md` |
| Output GeoPackages | `UPPER_SNAKE_CASE.gpkg` (fixed contract with IB-Tool 3) | `HU.gpkg`, `RN.gpkg`, `AUX_L.gpkg` |

## Parameter Names

- Descriptive, not generic: `hu_function_field` instead of `field`, `study_area_path` instead of `path`
- Boolean parameters as questions/states: `force_singlepart`, `keep_fields`
- `_path`/`_dir` suffix indicates a filesystem string parameter (`source_dir`,
  `hu_path`, `target_dir`) - never a `Path` object, to match the rest of
  `processor.py`'s `os.path`-based style
