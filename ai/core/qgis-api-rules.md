# QGIS API Rules

## Core Classes

### QgsVectorLayer

```python
# Create a temporary layer
layer = QgsVectorLayer("Polygon?crs=EPSG:25833", "name", "memory")

# Load a file-based layer
layer = QgsVectorLayer(path, layer_name, "ogr")

# Feature iteration
for feature in layer.getFeatures():
    geom = feature.geometry()
```

- Always check `layer.isValid()` after creation (see `processor._load_shp`,
  `processor.detect_hu_function_field`)
- Create temporary layers via the `"memory"` provider
- For file-based layers: path as the first parameter, provider `"ogr"` as the third

### QgsFeature

```python
feature = QgsFeature()
feature.setGeometry(geometry)
feature.setAttributes([value1, value2])
```

- Set geometry and attributes separately
- Do not set feature IDs manually - assigned by the layer
- Check `feature.hasGeometry()` / `geom is None` before accessing geometry -
  `processor._write_gpkg` skips features where `geom is None or geom.isNull()
  or geom.isEmpty()`

### QgsGeometry

```python
geom = QgsGeometry.fromWkt(wkt_string)
geom = feature.geometry()

# Multipart -> singlepart
parts = geom.asGeometryCollection() if geom.isMultipart() else [geom]
```

- Always validate the result of geometry operations (`isGeosValid()`)
- `isNull()` and `isEmpty()` are different states - check both
- Prefer QGIS Processing for complex operations (dissolve, clip, reproject)

## Feature Attribute NULL

A `NULL`/unset feature attribute is `qgis.core.NULL` (a `QVariant` sentinel),
**not** Python `None`. `value is None` never matches it; use
`value in (None, NULL)` or `value == NULL`. See `ai/core/testing-rules.md` →
"QGIS Attribute NULL vs. Python None" for the concrete bug this caused in
`processor._add_function_field_copy`.

## QGIS Processing

### Preferred Usage

```python
result = processing.run("native:buffer", {
    'INPUT': input_layer,
    'DISTANCE': distance,
    'SEGMENTS': 5,
    'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT
})
output_layer = result['OUTPUT']
```

- Use `QgsProcessing.TEMPORARY_OUTPUT` for intermediate results
- Extract the result layer from the result dict
- Check `_check_cancel(task)` before every `processing.run()` call in a
  cancellable pipeline (see every `_process_*` function in `processor.py`)

### Algorithms used in this plugin

| Algorithm | Purpose | Used in |
|-----------|---------|---------|
| `native:reprojectlayer` | Reproject a layer to the project CRS | `_reproject_if_needed` |
| `native:clip` | Clip to the optional study area | `_clip_if_needed` |
| `native:dissolve` | Merge geometries (study area, veg02_f/veg03_f) | `_prepare_clip_mask`, `_process_aux` |
| `native:polygonstolines` | Polygon boundaries -> lines (veg/gew inputs into AUX) | `_process_aux` |
| `native:extractbyexpression` | Filter `veg03_f` by `OBJART` 43005/43006 | `_process_aux` |

### Processing initialization is not automatic

`QgsApplication.initQgis()` does **not** register the `native:*` provider by
itself - that requires `processing.core.Processing.Processing.initialize()`.
Both the Dockerfile's build-time sanity check and `test/utilities.py`'s
`get_qgis_app()` call this explicitly. A standalone script that only calls
`initQgis()` and then `processing.run("native:dissolve", ...)` fails with
`Algorithm native:... not found`.

## API Version Compatibility

- **Target version**: QGIS 3.40
- **No deprecated API** - check the QGIS Python API documentation
  (`QgsField(name, type, len=...)` - passing `len` positionally instead of as
  a keyword is a common source of silently-wrong field definitions; see
  `ai/core/testing-rules.md`)
- When in doubt: use the QGIS PyQGIS Developer Cookbook as reference
- Use `QgsWkbTypes` constants (`QgsWkbTypes.MultiPolygon`, `.LineString`, ...)
  instead of deprecated enums for geometry types

## Coordinate Reference Systems

```python
# Read CRS from layer
crs = layer.crs()

# Create CRS object
crs = QgsCoordinateReferenceSystem("EPSG:25833")
```

- No implicit reprojection - `processor.py` always transforms explicitly via
  `_reproject_if_needed`, comparing `layer.crs() == target_crs` first (an
  identical CRS returns the same layer object, no transform call)
- `process_atkis` fixes the project CRS from `ver01_l`'s own CRS - every other
  input (HU, study area, other ATKIS layers) is reprojected to match
- `_write_gpkg` raises `ValueError` if a later input layer has a different
  **valid** CRS than the first layer - never silently mixes CRSes in one output
