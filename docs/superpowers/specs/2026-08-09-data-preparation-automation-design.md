# Data Preparation Automation — Design Spec

**Date:** 2026-08-09

## Context

`docs/data-preparation.md` (in the sibling `ibtool` project) documents the
manual workflow for turning downloaded ATKIS Basis-DLM raw data into the
HU (Building Footprints), RN (Road Network), and Aux (Auxiliary Layer)
inputs required by IBTool. That document explicitly names this
`data_wizard` plugin as "a future dedicated tool that automates these
steps."

The current state of `data_wizard` is a partial, undocumented
implementation of that automation: `processor.py` produces `RN.gpkg` and
`AUX.gpkg` from a hardcoded set of ATKIS shapefile names, but:

- Does not produce `HU.gpkg` at all.
- Performs no clipping to a study area.
- Performs no CRS check/reprojection.
- Does not enforce singlepart geometry on RN (only on Aux), even though
  `input-data.md` requires it for both line layers.
- The dialog only exposes a source folder and a target folder.

Goal: rework the plugin so that, given raw data the user has already
downloaded into a folder, the plugin produces all three of HU/RN/Aux as
GeoPackages, performing the CRS, clipping, mapping/merging, and
singlepart steps automatically — i.e. automate tutorial steps 2–7 of
`data-preparation.md` (step 1, obtaining raw data, and step 8, final
validation via IBTool's own Check button, stay outside the plugin's
scope).

## Decisions (from user clarification)

- **Clipping is conditional, not mandatory**: if the user supplies a
  study-area polygon file, the plugin clips every raw layer to it before
  mapping/merging. If no study-area file is supplied, raw layers are
  processed at their full extent as found in the source folder.
- **CRS handling**: the plugin auto-reprojects. The CRS of `ver01_l` (the
  first raw layer loaded) is fixed as the project CRS; any other raw
  layer (including the study-area polygon and the HU building file) that
  uses a different CRS is reprojected to match before further processing.
- **Aux composition**: keep the existing `processor.py` rule as
  authoritative, not the more loosely worded tutorial text — from
  `veg03_f`, only OBJART 43005 (`AX_Moor`) and 43006 (`AX_Sumpf`) are
  kept (not 43003 `AX_Gehoelz`, 43004 `AX_Heide`, or 43007
  `AX_UnlandVegetationsloseFlaeche`); `gew01_l` (waterway centerlines) is
  added to Aux directly, in addition to `gew01_f` (converted from
  polygons to lines).
- **HU source**: a separate file the user selects explicitly (its own
  file picker in the dialog) — not one of the ATKIS Basis-DLM shapefiles
  in the source folder. Typically ALKIS building/Hausumringe data, kept
  in its own folder outside the ATKIS raw-data folder.
- **No self-validation**: the plugin does not re-implement
  `input-data.md`'s validation checklist. The IBTool Check button remains
  the single source of truth for pass/fail validation. The one exception
  is a non-blocking log warning if none of `fkt`/`gfkzshh`/`funktion` is
  found on the HU source (informational only, mirrors the "this only
  needs to be checked" language in `data-preparation.md` step 6 without
  turning it into a hard validation layer).
- **Raw file discovery**: fixed ATKIS filenames (`ver01_l.shp`,
  `ver02_l.shp`, `ver03_l.shp`, `veg02_f.shp`, `veg03_f.shp`,
  `gew01_f.shp`, `gew01_l.shp`) are looked up directly in the source
  folder — no recursive subfolder search.
- **Output naming**: fixed names `HU.gpkg`, `RN.gpkg`, `AUX.gpkg` in the
  target folder — no user-configurable naming.

## Inputs (dialog)

| Field | Required | Type | Notes |
|---|---|---|---|
| Quellordner (source folder) | yes | folder picker | must contain the 7 fixed ATKIS shapefile names |
| Gebäudedatei (HU building file) | yes | file picker (`*.shp *.gpkg`) | any location, any of `fkt`/`gfkzshh`/`funktion` for the function-code field |
| Untersuchungsgebiet (study area) | no | file picker (`*.shp *.gpkg`) | polygon(s); if set, everything is clipped to it |
| Zielordner (target folder) | yes | folder picker | receives `HU.gpkg`, `RN.gpkg`, `AUX.gpkg` |

## Processing Pipeline (`processor.py`)

```
1. Load ver01_l → fix its CRS as project_crs
2. If study_area_path given:
     load study area layer
     reproject to project_crs if needed
     dissolve to a single clip mask (if >1 feature)
3. For each of the 7 raw ATKIS layers + the HU building file:
     load
     reproject to project_crs if its CRS differs
     clip to the mask from step 2, if a mask exists
4. HU:
     write prepared building layer → HU.gpkg
     (all fields preserved, no forced singlepart — polygon geometry,
      input-data.md does not restrict multipart for HU)
     if none of fkt/gfkzshh/funktion present as a field → log warning only
5. RN:
     merge ver01_l + ver02_l
     write → RN.gpkg (LineString, singlepart forced, no fields kept)
6. Aux:
     ver03_l as-is
     veg02_f → dissolve → polygonstolines
     veg03_f → filter OBJART IN (43005, 43006) → dissolve → polygonstolines
     gew01_f → polygonstolines
     gew01_l as-is
     merge all of the above
     write → AUX.gpkg (LineString, singlepart forced, no fields kept)
```

### Code structure changes

- Generalize the existing `_write_singlepart_gpkg` into a single
  `_write_gpkg(input_layers, output_path, geometry_type, force_singlepart,
  keep_fields, log, task)` used by all three of HU/RN/Aux — avoids having
  a second near-duplicate writer for HU's polygon+fields-preserved case.
- Add `_reproject_if_needed(layer, target_crs)` and
  `_clip_if_needed(layer, clip_mask)` helpers, applied uniformly to every
  raw input (including the HU building file and the study-area polygon
  itself) before layer-specific processing.
- `process_atkis()` gains two parameters:
  `process_atkis(source_dir, hu_path, target_dir, study_area_path=None,
  feedback=None, task=None)`.

## Error Handling

Unchanged pattern from the current code:
- Missing raw file → `FileNotFoundError` naming the expected path.
- Invalid/unloadable layer → `ValueError` naming the path.
- Cancellation checked at each processing step via `task.isCanceled()`.
- New: HU function-code field absent → non-blocking log warning, `Qgis.Warning`-level message via the existing `feedback`/log callback, processing continues.

## UI Changes

`data_wizard_dialog_base.ui`: add two rows —
"Gebäudedatei:" (file picker) and "Untersuchungsgebiet (optional):" (file
picker, may stay empty). `data_wizard_dialog.py` gains
`get_hu_file()` / `get_study_area_file()` and matching browse handlers.
`data_wizard.py`'s `run()` validates the three required fields (source
folder, HU file, target folder), passes the (optional) study-area path
through to `_AtkisTask`/`process_atkis`, and the success message lists
all three output files (`HU.gpkg`, `RN.gpkg`, `AUX.gpkg`).

## Testing

No project-specific automated test currently exercises `processor.py`'s
geoprocessing logic (`test/` is unmodified Plugin-Builder boilerplate
requiring a running QGIS environment). Verification for this change is
manual: run the plugin inside QGIS against a sample ATKIS dataset (with
and without a study-area file, with and without a CRS mismatch) and
confirm `HU.gpkg`/`RN.gpkg`/`AUX.gpkg` are produced and satisfy
`input-data.md`'s checklist when run through IBTool's own Check button.

## Out of Scope

- Re-implementing `input-data.md`'s validation checklist inside this
  plugin.
- Recursive/nested source-folder discovery.
- User-configurable output file names.
- Automatic download / WFS integration (raw data is always a
  user-provided local folder).
