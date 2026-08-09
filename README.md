# Data Wizard

**QGIS plugin name:** IB-Tool-Data-Wizard · **Status:** experimental · **Version:** 0.1

Data Wizard is a companion QGIS plugin to **[IBTool](https://github.com/IB-Tool/IB-Tool-3)**.
It automates turning raw ATKIS Basis-DLM data into the `HU`/`RN`/`Aux`
GeoPackages IBTool needs — a workflow that previously had to be done by
hand in QGIS.

Given a folder of raw ATKIS shapefiles and a separately chosen
building-footprint file, Data Wizard:

- fixes the project CRS from the raw data and reprojects any mismatched
  input automatically,
- optionally clips everything to a study-area polygon,
- maps and merges the raw layers into `HU.gpkg`, `RN.gpkg`, and
  `AUX_L.gpkg` following IBTool's fixed mapping rules,
- detects (or lets you pick) the building function-code column if it
  isn't already named `fkt`, `gfkzshh`, or `funktion`, and copies it into
  a correctly named column.

**Full documentation:** [`docs/README.md`](docs/README.md) — inputs,
usage, the exact mapping rules, architecture, and cross-references to
IBTool's own documentation (target data format, the manual workflow this
plugin automates, IBTool's usage).

## Installation

Copy (or clone) this repository into your QGIS plugins folder as
`data_wizard`, then enable it in QGIS's **Plugins → Manage and Install
Plugins**:

| OS | Path |
|---|---|
| Windows | `%APPDATA%\QGIS\QGIS3\profiles\default\python\plugins` |
| Linux | `~/.local/share/QGIS/QGIS3/profiles/default/python/plugins` |
| macOS | `~/Library/Application Support/QGIS/QGIS3/profiles/default/python/plugins` |

The plugin then appears under **Erweiterungen → IB-Tool → Data Wizard**
(grouped with IBTool itself).

## Development

No CI/automated test suite is set up (the geoprocessing logic in
`processor.py` depends on a running QGIS environment). Verification is
manual, inside QGIS — see [`docs/README.md` → Architecture](docs/README.md#architecture).

This plugin's own design specs and implementation plans live in
`docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Author

Oliver Harig — ottmar.hittzfeld@web.de
