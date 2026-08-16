# Data Wizard

[![CI](https://github.com/IB-Tool/data_wizard/actions/workflows/ci.yml/badge.svg)](https://github.com/IB-Tool/data_wizard/actions/workflows/ci.yml)
[![QGIS Plugin CI](https://github.com/IB-Tool/data_wizard/actions/workflows/qgis-plugin-ci.yml/badge.svg)](https://github.com/IB-Tool/data_wizard/actions/workflows/qgis-plugin-ci.yml)
[![License: GPL-2.0-or-later](https://img.shields.io/badge/License-GPL--2.0--or--later-blue.svg)](LICENSE)

**QGIS plugin name:** IB-Tool-Data-Wizard · **Status:** experimental · **Version:** 0.1

Data Wizard is a companion QGIS plugin to **[IB-Tool 3](https://github.com/IB-Tool/IB-Tool-3)**.
It automates turning raw ATKIS Basis-DLM data into the `HU`/`RN`/`Aux`
GeoPackages IB-Tool 3 needs — a workflow that previously had to be done by
hand in QGIS.

Given a folder of raw ATKIS shapefiles and a separately chosen
building-footprint file, Data Wizard:

- fixes the project CRS from the raw data and reprojects any mismatched
  input automatically,
- optionally clips everything to a study-area polygon,
- maps and merges the raw layers into `HU.gpkg`, `RN.gpkg`, and
  `AUX_L.gpkg` following IB-Tool 3's fixed mapping rules,
- detects (or lets you pick) the building function-code column if it
  isn't already named `fkt`, `gfkzshh`, or `funktion`, and copies it into
  a correctly named column.

**Full documentation:** [`docs/README.md`](docs/README.md) — inputs,
usage, the exact mapping rules, architecture, and cross-references to
IB-Tool 3's own documentation (target data format, the manual workflow this
plugin automates, IB-Tool 3's usage).

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
(grouped with IB-Tool 3 itself).

## Development

CI runs the same two workflows as IB-Tool 3 and ibtoolpartion — a Docker-based
test suite (`ci.yml`) and lint/security/structure validation
(`qgis-plugin-ci.yml`). See [`docs/contributing.md`](docs/contributing.md)
for the full setup, local test commands, and release process.

Note: the geoprocessing logic in `processor.py` (ATKIS mapping, reprojection,
clipping) is not yet covered by dedicated tests — only the scaffolded dialog
and environment tests exist so far. See
[`docs/contributing.md` → Testing](docs/contributing.md#testing).

This plugin's own design specs and implementation plans live in
`docs/superpowers/specs/` and `docs/superpowers/plans/`.

## Author

Oliver Harig — ottmar.hittzfeld@web.de
