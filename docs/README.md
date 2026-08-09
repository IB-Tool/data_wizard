# Data Wizard — Documentation

**Data Wizard** (plugin name in QGIS: *IB-Tool-Data-Wizard*) is a companion
QGIS plugin to **IBTool**. It automates the manual ATKIS-to-input-data
workflow described in IBTool's own tutorial: given a folder of raw ATKIS
Basis-DLM data and a separately supplied building-footprint file, it
produces the `HU`, `RN`, and `Aux` GeoPackages IBTool needs — reprojecting,
optionally clipping, and mapping/merging the raw layers automatically.

This document covers **Data Wizard itself** — installation is out of
scope (see [Plugin Installation Paths](#plugin-installation-paths) below
for the short version). For everything about the *target* data format,
the underlying manual workflow, and IBTool's own usage, see
[Relationship to IBTool's Documentation](#relationship-to-ibtools-documentation).

---

## What It Does

Data Wizard automates steps 2–7 of IBTool's data preparation tutorial —
determining the project CRS, optional clipping to a study area, mapping
raw ATKIS layers into `HU`/`RN`/`Aux`, and export as GeoPackage. Only
step 1 (downloading the raw data yourself) and step 8 (final validation
via IBTool's own **Check** button) stay outside the plugin.

1. **Project CRS** is fixed from the CRS of `ver01_l.shp` in the source
   folder. Any other raw layer — including the building-footprint file
   and the optional study-area polygon — that uses a different CRS is
   reprojected automatically before further processing.
2. **Clipping** happens only if a study-area polygon is supplied. Multiple
   polygons in that file are dissolved into a single clip mask first. If
   no study area is given, raw layers are processed at their full extent.
3. **Mapping & merging** follows a fixed rule (see
   [Output Layers](#output-layers) below) — the same rule documented in
   IBTool's `data-preparation.md`, now applied automatically instead of by
   hand in QGIS.
4. **HU function-code field**: if the building file doesn't already carry
   `fkt`, `gfkzshh`, or `funktion`, the plugin scans its columns for one
   matching the ATKIS building object-art code pattern (`31001_xxxx`).
   Exactly one match → copied automatically into a new `funktion` column.
   No match, or more than one → a picker dialog lets you choose the
   correct column (or skip). The original column is never renamed or
   removed, and the source file itself is never modified — only the
   generated `HU.gpkg` gets the extra column.

## Requirements

| Input | Required | What it is |
|---|---|---|
| **Quellordner** (source folder) | yes | A folder containing exactly these seven ATKIS Basis-DLM shapefiles, flat (no subfolders searched): `ver01_l.shp`, `ver02_l.shp`, `ver03_l.shp`, `veg02_f.shp`, `veg03_f.shp`, `gew01_f.shp`, `gew01_l.shp` |
| **Gebäudedatei** (building file) | yes | A separate building-footprint file (`.shp`/`.gpkg`), chosen individually — not expected to sit in the source folder, since it typically comes from a different data source (e.g. ALKIS) |
| **Untersuchungsgebiet** (study area) | no | A polygon file (`.shp`/`.gpkg`) to clip everything to; leave empty to process the full extent of the raw data |
| **Zielordner** (target folder) | yes | Output folder for the three GeoPackages; must already exist |

## Usage

1. Open the plugin from the toolbar/menu (**IB-Tool-Data-Wizard**).
2. Fill in the four fields above (browse buttons for each). Picking the
   building file immediately runs the function-code field check — a
   picker dialog may appear if it can't be resolved automatically.
3. Click **OK**. Processing runs in the background (QGIS Task Manager);
   progress and any warnings appear as log messages ("Data Wizard" in
   **View → Panels → Log Messages**) and in the message bar.
4. On completion, `HU.gpkg`, `RN.gpkg`, and `AUX_L.gpkg` are in the target
   folder. Load them into IBTool along with a `Part` layer and (optionally)
   a filter file, and run IBTool's own **Check** — see
   [IBTool's quickstart.md](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/quickstart.md)
   for that step. Data Wizard does not run IBTool's validation checklist
   itself.

## Output Layers

| Output file | Source layers | Rule |
|---|---|---|
| `HU.gpkg` | Building file (chosen separately) | Copied as-is, all fields kept, no forced singlepart. `funktion` column added if needed (see above). |
| `RN.gpkg` | `ver01_l`, `ver02_l` | Merged, forced singlepart |
| `AUX_L.gpkg` | `ver03_l` (as-is); `veg02_f` (dissolve → lines); `veg03_f` filtered to OBJART 43005/43006 (dissolve → lines); `gew01_f` (lines); `gew01_l` (as-is) | Merged, forced singlepart |

> **Naming note:** the auxiliary output is named `AUX_L.gpkg`, not
> `AUX.gpkg` as in earlier versions of this plugin — `AUX` is a reserved
> Windows device name (like `CON`, `NUL`, `COM1`), and creating a file
> with that name hangs indefinitely on Windows. This has no effect on
> IBTool itself: file names for `HU`/`RN`/`Part`/`Aux` are chosen freely
> in IBTool's own dialog, there is no fixed naming requirement on that
> side (see IBTool's `data-preparation.md` → Export).

## Out of Scope

- **`Part` (partitioning layer)** — produced by a separate, dedicated
  tool; Data Wizard doesn't touch it.
- **Filter file** — a separately maintained, largely static file; Data
  Wizard doesn't touch it.
- **Validation** — Data Wizard does not re-implement IBTool's
  `input-data.md` validation checklist. The one exception is a
  non-blocking log warning if HU ends up with no function-code field at
  all. The authoritative check is IBTool's own **Check** button.

## Architecture

| File | Responsibility |
|---|---|
| `data_wizard.py` | Plugin entry point (`Data_Wizard` class); dialog invocation, input validation, background-task dispatch (`_AtkisTask`, a `QgsTask` subclass) |
| `data_wizard_dialog.py` / `data_wizard_dialog_base.ui` | Dialog UI — the four input fields, browse handlers, HU function-field detection/picker |
| `processor.py` | All processing logic — CRS handling, clipping, the HU/RN/Aux mapping rules, GeoPackage writing. Pure functions, no UI code, so it runs safely inside the background `QgsTask` |

There is no automated test suite exercising `processor.py`'s geoprocessing
logic — it depends on a running QGIS environment, which the plugin's own
`test/` folder (unmodified Plugin-Builder boilerplate) doesn't set up for
this. Verification is manual, inside QGIS.

## Relationship to IBTool's Documentation

Data Wizard is a data-preparation front-end **for** IBTool — it doesn't
replace IBTool's own documentation, which remains the authority on the
target data format and on IBTool itself. Both plugins now live in their
own GitHub repositories (both private, under the `IB-Tool` organization),
so the links below point at IBTool's repository on GitHub rather than a
local sibling folder — following them requires being logged into GitHub
with access to that org.

| For... | See |
|---|---|
| The exact target specification Data Wizard's output must satisfy (field requirements, geometry types, minimum feature counts, the full validation checklist) | [`input-data.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/input-data.md) |
| The manual workflow this plugin automates (background/rationale for each step) | [`data-preparation.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/data-preparation.md) |
| Where to download raw ATKIS data per German state | [`data-sources.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/data-sources.md) |
| Running IBTool itself once Data Wizard's outputs are ready | [`quickstart.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/quickstart.md) |
| How IBTool's algorithm actually works | [`how-it-works.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/how-it-works.md) |
| IBTool's own code structure | [`plugin-architecture.md`](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/plugin-architecture.md) |

*(These links point into IBTool's own repository and are not updated from
this side — if IBTool's docs move, get restructured, or the default
branch changes from `master`, update the paths here accordingly. If you
instead run both plugins from local sibling folders, e.g. for offline
development, use relative paths like `../../IB-Tool-3/docs/...` instead.)*

## Plugin Installation Paths

Same as any QGIS plugin — see IBTool's
[`plugin-architecture.md` → Plugin Installation Paths](https://github.com/IB-Tool/IB-Tool-3/blob/master/docs/plugin-architecture.md#plugin-installation-paths)
for the per-OS paths; Data Wizard's own folder name (`data_wizard`) is
already a valid Python identifier, so no renaming is needed for QGIS to
load it (unlike IBTool's `IB-Tool-3` → `ibtool` rename requirement).

## Development History

This plugin's own design specs and implementation plans (written during
its development, following the same process as IBTool's) live in
`docs/superpowers/specs/` and `docs/superpowers/plans/` — specifically
the `2026-08-09-data-preparation-automation*` and
`2026-08-09-hu-function-field-detection*` files. The other files
previously in those folders documented IBTool's own feature history and
have been removed from this repository (see IB-Tool-3's own
`docs/superpowers/` for that history).
