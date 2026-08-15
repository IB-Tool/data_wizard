"""
Shared layer and geometry factory helpers for Data Wizard tests.

Import this module AFTER calling get_qgis_app() in your test file so that
qgis.core is fully initialised when the module-level imports run.

Usage in test files:
    from .utilities import get_qgis_app
    QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
    from .layer_factories import (
        make_polygon_layer, make_line_layer, make_point_layer,
        make_square_geom, add_feature_to_layer,
        write_layer_as_shp, write_layer_as_gpkg,
    )
"""

from qgis.core import (
    QgsVectorLayer, QgsFeature, QgsGeometry, QgsPointXY,
    QgsVectorFileWriter, QgsCoordinateTransformContext,
)


def make_polygon_layer(crs: str = "EPSG:25833", name: str = "test_poly") -> QgsVectorLayer:
    """Return an empty in-memory polygon layer with the given CRS."""
    layer = QgsVectorLayer(f"Polygon?crs={crs}", name, "memory")
    layer.updateFields()
    return layer


def make_line_layer(crs: str = "EPSG:25833", name: str = "test_line") -> QgsVectorLayer:
    """Return an empty in-memory line layer with the given CRS."""
    layer = QgsVectorLayer(f"LineString?crs={crs}", name, "memory")
    layer.updateFields()
    return layer


def make_point_layer(crs: str = "EPSG:25833", name: str = "test_point") -> QgsVectorLayer:
    """Return an empty in-memory point layer with the given CRS."""
    layer = QgsVectorLayer(f"Point?crs={crs}", name, "memory")
    layer.updateFields()
    return layer


def make_square_geom(x0: float, y0: float, size: float) -> QgsGeometry:
    """Return an axis-aligned square QgsGeometry with bottom-left corner at (x0, y0)."""
    return QgsGeometry.fromPolygonXY([[
        QgsPointXY(x0,        y0),
        QgsPointXY(x0 + size, y0),
        QgsPointXY(x0 + size, y0 + size),
        QgsPointXY(x0,        y0 + size),
        QgsPointXY(x0,        y0),
    ]])


def add_feature_to_layer(layer: QgsVectorLayer, geom: QgsGeometry, attributes=None) -> QgsFeature:
    """Add a QgsFeature with the given geometry (and optional attributes) to layer."""
    feat = QgsFeature(layer.fields())
    feat.setGeometry(geom)
    if attributes is not None:
        feat.setAttributes(attributes)
    layer.dataProvider().addFeatures([feat])
    layer.updateExtents()
    return feat


def _write_layer(layer: QgsVectorLayer, path: str, driver_name: str) -> str:
    """Write layer to path using driver_name; returns the written path.

    Used because processor._load_shp and detect_hu_function_field expect
    file paths, not in-memory QgsVectorLayer objects.
    """
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = driver_name
    options.fileEncoding = "UTF-8"
    error, error_msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, path, QgsCoordinateTransformContext(), options)
    if error != QgsVectorFileWriter.NoError:
        raise IOError(f"Konnte Testlayer nicht schreiben: {path} ({error_msg})")
    return path


def write_layer_as_shp(layer: QgsVectorLayer, path: str) -> str:
    """Write layer as a Shapefile at path (path should end in .shp)."""
    return _write_layer(layer, path, "ESRI Shapefile")


def write_layer_as_gpkg(layer: QgsVectorLayer, path: str) -> str:
    """Write layer as a GeoPackage at path (path should end in .gpkg)."""
    return _write_layer(layer, path, "GPKG")
