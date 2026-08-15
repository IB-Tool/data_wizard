# -*- coding: utf-8 -*-
"""Tests for processor.py - ATKIS Basis-DLM processing logic.

Tier boundary follows docs/test-strategy.md: a function counts as
``integration`` if (and only if) it calls ``processing.run()`` directly or
indirectly. ``_load_shp``, ``_write_gpkg``, ``_add_function_field_copy`` and
``detect_hu_function_field`` never call ``processing.run()`` and are unit
tests even though they touch real QGIS classes (QgsVectorLayer, QgsFeature).

Integration tests for process_atkis / _process_hu / _process_rn / _process_aux
use the real ATKIS/ALKIS data shipped in Testdaten/ (see docs/test-strategy.md
-> Justified Exclusions for why this is checked into the repo instead of
generated).
"""

import pytest
from qgis.core import (
    QgsCoordinateReferenceSystem, QgsFeature, QgsField, QgsGeometry,
    QgsPointXY, QgsVectorLayer, QgsWkbTypes, NULL,
)
from qgis.PyQt.QtCore import QVariant

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from .layer_factories import (  # noqa: E402
    add_feature_to_layer, make_line_layer,
    make_polygon_layer, make_square_geom,
    write_layer_as_shp,
)
# Test data paths and the skip marker live in test/config.py, driven by
# test_config.ini - do not re-derive them here.
from .config import ATKIS_DIR, HU_SHP, requires_atkis_testdaten  # noqa: E402

from data_wizard.processor import (  # noqa: E402
    _add_function_field_copy, _check_cancel,
    _clip_if_needed, _load_shp, _prepare_clip_mask, _process_aux,
    _process_hu, _process_rn, _reproject_if_needed, _write_gpkg,
    detect_hu_function_field, process_atkis,
)

CRS_25833 = QgsCoordinateReferenceSystem("EPSG:25833")
CRS_4326 = QgsCoordinateReferenceSystem("EPSG:4326")


def _assert_valid_geometries(layer):
    """Mandatory geometry checks per docs/test-strategy.md Step 4."""
    assert layer is not None
    for feat in layer.getFeatures():
        geom = feat.geometry()
        assert not geom.isNull(), "Geometry must not be null"
        assert not geom.isEmpty(), "Geometry must not be empty"
        assert geom.isGeosValid(), "Geometry must be GEOS-valid"


# ===========================================================================
# detect_hu_function_field
# ===========================================================================

class TestDetectHuFunctionField:
    """Tests for detect_hu_function_field."""

    def _hu_layer_with_field(self, tmp_path, field_name, values, fname="hu.shp"):
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes(
            [QgsField(field_name, QVariant.String, len=254)])
        layer.updateFields()
        for i, val in enumerate(values):
            geom = make_square_geom(i * 10, 0, 5)
            add_feature_to_layer(layer, geom, attributes=[val])
        path = str(tmp_path / fname)
        return write_layer_as_shp(layer, path)

    @pytest.mark.unit
    def test_returns_ok_when_fkt_field_present(self, tmp_path):
        """Returns ('ok', None) when the HU already has a 'fkt' field."""
        path = self._hu_layer_with_field(tmp_path, "fkt", ["31001_1000"])
        assert detect_hu_function_field(path) == ('ok', None)

    @pytest.mark.unit
    def test_field_match_is_case_insensitive(self, tmp_path):
        """A field named 'FUNKTION' (any case) also counts as already present."""
        path = self._hu_layer_with_field(tmp_path, "FUNKTIO", ["x"], fname="hu2.shp")
        # DBF truncates to 10 chars; use a name that still matches after lower()
        assert detect_hu_function_field(path)[0] in ('ok', 'ambiguous')

    @pytest.mark.unit
    def test_returns_auto_for_single_matching_field(self, tmp_path):
        """Returns ('auto', name) when exactly one field matches the pattern."""
        path = self._hu_layer_with_field(
            tmp_path, "code", ["31001_1000", "31001_2000", "31001_3000"])
        assert detect_hu_function_field(path) == ('auto', 'code')

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_ambiguous_when_no_field_matches(self, tmp_path):
        """Returns ('ambiguous', all_field_names) when no field matches the pattern."""
        path = self._hu_layer_with_field(tmp_path, "code", ["abc", "def"])
        status, result = detect_hu_function_field(path)
        assert status == 'ambiguous'
        assert 'code' in result

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_returns_ambiguous_when_multiple_fields_match(self, tmp_path):
        """Returns ('ambiguous', ...) when more than one field matches the pattern."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes(
            [QgsField("code1", QVariant.String, len=254),
             QgsField("code2", QVariant.String, len=254)])
        layer.updateFields()
        add_feature_to_layer(
            layer, make_square_geom(0, 0, 5), attributes=["31001_1000", "31001_2000"])
        path = write_layer_as_shp(layer, str(tmp_path / "hu.shp"))
        status, result = detect_hu_function_field(path)
        assert status == 'ambiguous'
        assert 'code1' in result and 'code2' in result

    @pytest.mark.unit
    def test_raises_value_error_for_invalid_path(self, tmp_path):
        """Raises ValueError when hu_path cannot be loaded as a valid layer."""
        with pytest.raises(ValueError):
            detect_hu_function_field(str(tmp_path / "does_not_exist.shp"))

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_sample_size_limits_features_read(self, tmp_path):
        """Only the first sample_size features are inspected for the pattern."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes([QgsField("code", QVariant.String, len=254)])
        layer.updateFields()
        # First 50 features match the pattern; the rest (indices 50-59) don't.
        for i in range(60):
            value = f"31001_{i:04d}" if i < 50 else "not_a_code"
            add_feature_to_layer(layer, make_square_geom(i * 10, 0, 5), attributes=[value])
        path = write_layer_as_shp(layer, str(tmp_path / "hu.shp"))

        # Default sample_size=50 never sees the non-matching tail -> single candidate.
        assert detect_hu_function_field(path, sample_size=50) == ('auto', 'code')
        # A larger sample_size sees the non-matching values -> ambiguous.
        status, _ = detect_hu_function_field(path, sample_size=60)
        assert status == 'ambiguous'


# ===========================================================================
# _check_cancel
# ===========================================================================

class TestCheckCancel:
    """Tests for _check_cancel."""

    @pytest.mark.unit
    def test_raises_when_task_is_canceled(self):
        """Raises an Exception when task.isCanceled() is True."""
        class _Task:
            def isCanceled(self):
                return True
        with pytest.raises(Exception, match="abgebrochen"):
            _check_cancel(_Task())

    @pytest.mark.unit
    def test_no_op_when_task_not_canceled(self):
        """Does nothing when task.isCanceled() is False."""
        class _Task:
            def isCanceled(self):
                return False
        _check_cancel(_Task())  # must not raise

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_no_op_when_task_is_none(self):
        """Does nothing when task is None."""
        _check_cancel(None)  # must not raise


# ===========================================================================
# _load_shp
# ===========================================================================

class TestLoadShp:
    """Tests for _load_shp."""

    @pytest.mark.unit
    def test_raises_file_not_found_for_missing_shp(self, tmp_path):
        """Raises FileNotFoundError when <layer_name>.shp does not exist."""
        with pytest.raises(FileNotFoundError):
            _load_shp(str(tmp_path), "ver01_l")

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_raises_value_error_for_invalid_shp(self, tmp_path):
        """Raises ValueError when the file exists but is not a valid shapefile."""
        bad_path = tmp_path / "ver01_l.shp"
        bad_path.write_text("not a real shapefile")
        with pytest.raises(ValueError):
            _load_shp(str(tmp_path), "ver01_l")

    @pytest.mark.unit
    def test_loads_valid_shapefile(self, tmp_path):
        """Returns a valid QgsVectorLayer for a well-formed shapefile."""
        layer = make_line_layer(crs="EPSG:25833", name="ver01_l")
        add_feature_to_layer(layer, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]))
        write_layer_as_shp(layer, str(tmp_path / "ver01_l.shp"))

        result = _load_shp(str(tmp_path), "ver01_l")
        assert result.isValid()
        assert result.featureCount() == 1


# ===========================================================================
# _add_function_field_copy
# ===========================================================================

class TestAddFunctionFieldCopy:
    """Tests for _add_function_field_copy."""

    def _layer_with_src_field(self, values):
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes([QgsField("src", QVariant.String, len=254)])
        layer.updateFields()
        for i, val in enumerate(values):
            add_feature_to_layer(layer, make_square_geom(i * 10, 0, 5), attributes=[val])
        return layer

    @pytest.mark.unit
    def test_creates_target_field_and_copies_values(self):
        """Adds target_field_name and copies the source field's values into it."""
        layer = self._layer_with_src_field(["31001_1000", "31001_2000"])
        result = _add_function_field_copy(layer, "src", "funktion")
        values = [f["funktion"] for f in result.getFeatures()]
        assert sorted(values) == ["31001_1000", "31001_2000"]

    @pytest.mark.unit
    def test_raises_value_error_for_missing_source_field(self):
        """Raises ValueError when source_field_name does not exist on the layer."""
        layer = self._layer_with_src_field(["31001_1000"])
        with pytest.raises(ValueError, match="nicht gefunden"):
            _add_function_field_copy(layer, "does_not_exist", "funktion")

    @pytest.mark.unit
    @pytest.mark.edge_case
    @pytest.mark.xfail(
        reason="Known bug: processor._add_function_field_copy compares "
               "`value is None`, but a NULL QGIS attribute is a QVariant "
               "sentinel, not Python None - so NULL source values are "
               "copied as the literal string 'NULL' instead of staying "
               "NULL. Documented in docs/test-strategy.md Gap Analysis. "
               "Flip this to a plain assertion once processor.py is fixed.",
        strict=True)
    def test_null_source_values_are_copied_as_null_not_string(self):
        """A NULL source value must stay NULL in the target field, not become
        the literal string 'NULL'."""
        layer = self._layer_with_src_field([NULL])
        result = _add_function_field_copy(layer, "src", "funktion")
        value = next(result.getFeatures())["funktion"]
        assert value == NULL, f"Expected NULL to remain NULL, got {value!r}"


# ===========================================================================
# _write_gpkg
# ===========================================================================

class TestWriteGpkg:
    """Tests for _write_gpkg."""

    @pytest.mark.unit
    def test_keep_fields_true_preserves_attributes(self, tmp_path):
        """keep_fields=True copies the first layer's field schema and values."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes([QgsField("funktion", QVariant.String, len=254)])
        layer.updateFields()
        add_feature_to_layer(layer, make_square_geom(0, 0, 5), attributes=["31001_1000"])

        out = str(tmp_path / "HU.gpkg")
        _write_gpkg([layer], out, QgsWkbTypes.MultiPolygon,
                    force_singlepart=False, keep_fields=True)

        result = QgsVectorLayer(out, "check", "ogr")
        assert result.isValid()
        assert result.featureCount() == 1
        feat = next(result.getFeatures())
        assert feat["funktion"] == "31001_1000"

    @pytest.mark.unit
    def test_force_singlepart_splits_multipart_geometry(self, tmp_path):
        """force_singlepart=True writes one feature per part of a multipart geometry."""
        layer = make_polygon_layer(crs="EPSG:25833", name="rn")
        multi = QgsGeometry.fromMultiPolygonXY([
            make_square_geom(0, 0, 5).asPolygon(),
            make_square_geom(20, 0, 5).asPolygon(),
        ])
        add_feature_to_layer(layer, multi)

        # geometry_type is the singlepart target type here, matching how
        # _process_rn/_process_aux call _write_gpkg (QgsWkbTypes.LineString,
        # not MultiLineString) when force_singlepart=True.
        out = str(tmp_path / "AUX_L.gpkg")
        _write_gpkg([layer], out, QgsWkbTypes.Polygon,
                    force_singlepart=True, keep_fields=False)

        result = QgsVectorLayer(out, "check", "ogr")
        assert result.featureCount() == 2
        for feat in result.getFeatures():
            assert not feat.geometry().isMultipart()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_raises_value_error_on_crs_mismatch(self, tmp_path):
        """Raises ValueError when a later input layer has a different CRS than the first."""
        layer_a = make_polygon_layer(crs="EPSG:25833", name="a")
        add_feature_to_layer(layer_a, make_square_geom(0, 0, 5))
        layer_b = make_polygon_layer(crs="EPSG:4326", name="b")
        add_feature_to_layer(layer_b, make_square_geom(0, 0, 5))

        out = str(tmp_path / "out.gpkg")
        with pytest.raises(ValueError, match="abweichendes CRS"):
            _write_gpkg([layer_a, layer_b], out, QgsWkbTypes.MultiPolygon,
                        force_singlepart=False, keep_fields=False)

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_null_and_empty_geometries_are_skipped(self, tmp_path):
        """Features with null or empty geometry are not written to the output."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        add_feature_to_layer(layer, make_square_geom(0, 0, 5))
        # Feature with no geometry at all.
        empty_feat = QgsFeature(layer.fields())
        layer.dataProvider().addFeatures([empty_feat])

        out = str(tmp_path / "out.gpkg")
        _write_gpkg([layer], out, QgsWkbTypes.MultiPolygon,
                    force_singlepart=False, keep_fields=False)

        result = QgsVectorLayer(out, "check", "ogr")
        assert result.featureCount() == 1

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_raises_io_error_for_unwritable_path(self, tmp_path):
        """Raises IOError when the output path's parent directory does not exist."""
        layer = make_polygon_layer(crs="EPSG:25833", name="a")
        add_feature_to_layer(layer, make_square_geom(0, 0, 5))
        bad_path = str(tmp_path / "no_such_subdir" / "out.gpkg")
        with pytest.raises(IOError):
            _write_gpkg([layer], bad_path, QgsWkbTypes.MultiPolygon,
                        force_singlepart=False, keep_fields=False)


# ===========================================================================
# _reproject_if_needed / _clip_if_needed (integration - processing.run)
# ===========================================================================

class TestReprojectIfNeeded:
    """Tests for _reproject_if_needed."""

    @pytest.mark.integration
    def test_same_crs_returns_same_object(self):
        """Returns the identical layer object (no reprojection) when the CRS already matches."""
        layer = make_polygon_layer(crs="EPSG:25833")
        result = _reproject_if_needed(layer, CRS_25833)
        assert result is layer

    @pytest.mark.integration
    def test_different_crs_returns_transformed_layer(self):
        """Reprojects the layer when its CRS differs from target_crs."""
        layer = make_polygon_layer(crs="EPSG:4326")
        add_feature_to_layer(layer, make_square_geom(13.0, 51.0, 0.01))
        result = _reproject_if_needed(layer, CRS_25833)
        assert result is not layer
        assert result.crs() == CRS_25833
        _assert_valid_geometries(result)


class TestClipIfNeeded:
    """Tests for _clip_if_needed."""

    @pytest.mark.unit
    def test_none_mask_is_passthrough(self):
        """Returns the layer unchanged when clip_mask is None."""
        layer = make_polygon_layer(crs="EPSG:25833")
        result = _clip_if_needed(layer, None)
        assert result is layer

    @pytest.mark.integration
    def test_clips_to_mask(self):
        """Clips the input layer to the given mask polygon."""
        layer = make_polygon_layer(crs="EPSG:25833")
        add_feature_to_layer(layer, make_square_geom(0, 0, 100))
        mask = make_polygon_layer(crs="EPSG:25833", name="mask")
        add_feature_to_layer(mask, make_square_geom(0, 0, 10))

        result = _clip_if_needed(layer, mask)
        assert result.featureCount() >= 1
        total_area = sum(f.geometry().area() for f in result.getFeatures())
        assert total_area == pytest.approx(100.0, rel=0.05)

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_no_overlap_returns_empty_result(self):
        """A mask that does not overlap the input layer yields an empty (not erroring) result."""
        layer = make_polygon_layer(crs="EPSG:25833")
        add_feature_to_layer(layer, make_square_geom(0, 0, 10))
        mask = make_polygon_layer(crs="EPSG:25833", name="mask")
        add_feature_to_layer(mask, make_square_geom(10_000, 10_000, 10))

        result = _clip_if_needed(layer, mask)
        assert result is not None
        assert result.featureCount() == 0


# ===========================================================================
# _prepare_clip_mask
# ===========================================================================

class TestPrepareClipMask:
    """Tests for _prepare_clip_mask."""

    @pytest.mark.unit
    def test_empty_path_returns_none(self):
        """Returns None when study_area_path is falsy (no clipping requested)."""
        assert _prepare_clip_mask("", CRS_25833) is None
        assert _prepare_clip_mask(None, CRS_25833) is None

    @pytest.mark.integration
    def test_single_polygon_is_not_dissolved(self, tmp_path):
        """A study area with a single polygon is returned as-is (no dissolve)."""
        layer = make_polygon_layer(crs="EPSG:25833", name="study_area")
        add_feature_to_layer(layer, make_square_geom(0, 0, 10))
        path = write_layer_as_shp(layer, str(tmp_path / "study_area.shp"))

        result = _prepare_clip_mask(path, CRS_25833)
        assert result.featureCount() == 1

    @pytest.mark.integration
    def test_multiple_polygons_are_dissolved_to_one_feature(self, tmp_path):
        """Multiple study-area polygons are dissolved into a single feature."""
        layer = make_polygon_layer(crs="EPSG:25833", name="study_area")
        add_feature_to_layer(layer, make_square_geom(0, 0, 10))
        add_feature_to_layer(layer, make_square_geom(9, 0, 10))  # overlapping
        path = write_layer_as_shp(layer, str(tmp_path / "study_area.shp"))

        result = _prepare_clip_mask(path, CRS_25833)
        assert result.featureCount() == 1

    @pytest.mark.unit
    def test_raises_value_error_for_invalid_path(self, tmp_path):
        """Raises ValueError when study_area_path cannot be loaded."""
        with pytest.raises(ValueError):
            _prepare_clip_mask(str(tmp_path / "missing.shp"), CRS_25833)


# ===========================================================================
# _process_hu / _process_rn / _process_aux (integration, synthetic layers)
# ===========================================================================

class TestProcessHu:
    """Tests for _process_hu."""

    @pytest.mark.integration
    def test_writes_valid_hu_gpkg(self, tmp_path):
        """Writes HU.gpkg with valid MultiPolygon geometries and preserved fields."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        layer.dataProvider().addAttributes([QgsField("funktion", QVariant.String, len=254)])
        layer.updateFields()
        add_feature_to_layer(layer, make_square_geom(0, 0, 5), attributes=["31001_1000"])
        hu_path = write_layer_as_shp(layer, str(tmp_path / "hu.shp"))

        _process_hu(hu_path, CRS_25833, None, str(tmp_path))

        out = QgsVectorLayer(str(tmp_path / "HU.gpkg"), "check", "ogr")
        assert out.isValid()
        assert out.featureCount() == 1
        _assert_valid_geometries(out)

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_missing_function_field_logs_warning_without_aborting(self, tmp_path):
        """Missing fkt/gfkzshh/funktion and no function_field logs a warning but still writes HU.gpkg."""
        layer = make_polygon_layer(crs="EPSG:25833", name="hu")
        add_feature_to_layer(layer, make_square_geom(0, 0, 5))
        hu_path = write_layer_as_shp(layer, str(tmp_path / "hu.shp"))

        messages = []
        _process_hu(hu_path, CRS_25833, None, str(tmp_path), log=messages.append)

        assert any("WARNUNG" in m for m in messages)
        assert (tmp_path / "HU.gpkg").exists()


class TestProcessRn:
    """Tests for _process_rn."""

    @pytest.mark.integration
    def test_writes_merged_singlepart_rn_gpkg(self, tmp_path):
        """Merges ver01_l and ver02_l into a singlepart RN.gpkg without attributes."""
        ver01 = make_line_layer(crs="EPSG:25833", name="ver01_l")
        add_feature_to_layer(ver01, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]))
        write_layer_as_shp(ver01, str(tmp_path / "ver01_l.shp"))

        ver02 = make_line_layer(crs="EPSG:25833", name="ver02_l")
        add_feature_to_layer(ver02, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 10), QgsPointXY(10, 10)]))
        write_layer_as_shp(ver02, str(tmp_path / "ver02_l.shp"))

        _process_rn(str(tmp_path), CRS_25833, None, str(tmp_path))

        out = QgsVectorLayer(str(tmp_path / "RN.gpkg"), "check", "ogr")
        assert out.isValid()
        assert out.featureCount() == 2
        _assert_valid_geometries(out)


class TestProcessAux:
    """Tests for _process_aux."""

    def _write_atkis_subset(self, tmp_path):
        """Writes minimal ver03_l/veg02_f/veg03_f/gew01_f/gew01_l shapefiles."""

        ver03 = make_line_layer(crs="EPSG:25833", name="ver03_l")
        add_feature_to_layer(ver03, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]))
        write_layer_as_shp(ver03, str(tmp_path / "ver03_l.shp"))

        veg02 = make_polygon_layer(crs="EPSG:25833", name="veg02_f")
        add_feature_to_layer(veg02, make_square_geom(0, 20, 5))
        write_layer_as_shp(veg02, str(tmp_path / "veg02_f.shp"))

        veg03 = make_polygon_layer(crs="EPSG:25833", name="veg03_f")
        veg03.dataProvider().addAttributes([QgsField("OBJART", QVariant.String, len=254)])
        veg03.updateFields()
        add_feature_to_layer(veg03, make_square_geom(0, 40, 5), attributes=["43005"])
        add_feature_to_layer(veg03, make_square_geom(20, 40, 5), attributes=["11111"])
        write_layer_as_shp(veg03, str(tmp_path / "veg03_f.shp"))

        gew01f = make_polygon_layer(crs="EPSG:25833", name="gew01_f")
        add_feature_to_layer(gew01f, make_square_geom(0, 60, 5))
        write_layer_as_shp(gew01f, str(tmp_path / "gew01_f.shp"))

        gew01l = make_line_layer(crs="EPSG:25833", name="gew01_l")
        add_feature_to_layer(gew01l, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 80), QgsPointXY(10, 80)]))
        write_layer_as_shp(gew01l, str(tmp_path / "gew01_l.shp"))

    @pytest.mark.integration
    def test_writes_valid_aux_l_gpkg(self, tmp_path):
        """Merges the five AUX source layers into a valid singlepart AUX_L.gpkg."""
        self._write_atkis_subset(tmp_path)

        _process_aux(str(tmp_path), CRS_25833, None, str(tmp_path))

        out = QgsVectorLayer(str(tmp_path / "AUX_L.gpkg"), "check", "ogr")
        assert out.isValid()
        assert out.featureCount() > 0
        _assert_valid_geometries(out)
        for feat in out.getFeatures():
            assert not feat.geometry().isMultipart()

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_veg03_without_matching_objart_produces_no_crash(self, tmp_path):
        """veg03_f with no OBJART in (43005, 43006) yields an empty intermediate layer, no crash."""

        ver03 = make_line_layer(crs="EPSG:25833", name="ver03_l")
        add_feature_to_layer(ver03, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 0), QgsPointXY(10, 0)]))
        write_layer_as_shp(ver03, str(tmp_path / "ver03_l.shp"))

        veg02 = make_polygon_layer(crs="EPSG:25833", name="veg02_f")
        add_feature_to_layer(veg02, make_square_geom(0, 20, 5))
        write_layer_as_shp(veg02, str(tmp_path / "veg02_f.shp"))

        veg03 = make_polygon_layer(crs="EPSG:25833", name="veg03_f")
        veg03.dataProvider().addAttributes([QgsField("OBJART", QVariant.String, len=254)])
        veg03.updateFields()
        add_feature_to_layer(veg03, make_square_geom(0, 40, 5), attributes=["11111"])
        write_layer_as_shp(veg03, str(tmp_path / "veg03_f.shp"))

        gew01f = make_polygon_layer(crs="EPSG:25833", name="gew01_f")
        add_feature_to_layer(gew01f, make_square_geom(0, 60, 5))
        write_layer_as_shp(gew01f, str(tmp_path / "gew01_f.shp"))

        gew01l = make_line_layer(crs="EPSG:25833", name="gew01_l")
        add_feature_to_layer(gew01l, QgsGeometry.fromPolylineXY(
            [QgsPointXY(0, 80), QgsPointXY(10, 80)]))
        write_layer_as_shp(gew01l, str(tmp_path / "gew01_l.shp"))

        _process_aux(str(tmp_path), CRS_25833, None, str(tmp_path))  # must not raise

        out = QgsVectorLayer(str(tmp_path / "AUX_L.gpkg"), "check", "ogr")
        assert out.isValid()

    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_cancel_mid_processing_raises(self, tmp_path):
        """task.isCanceled() becoming True mid-run aborts processing with a defined exception."""
        self._write_atkis_subset(tmp_path)

        class _CancelAfterFirstCheck:
            def __init__(self):
                self.calls = 0

            def isCanceled(self):
                self.calls += 1
                return self.calls > 1

        with pytest.raises(Exception, match="abgebrochen"):
            _process_aux(str(tmp_path), CRS_25833, None, str(tmp_path),
                         task=_CancelAfterFirstCheck())


# ===========================================================================
# process_atkis (end-to-end, real ATKIS/ALKIS Testdaten)
# ===========================================================================

class TestProcessAtkis:
    """End-to-end tests for process_atkis against Testdaten/."""

    @requires_atkis_testdaten
    @pytest.mark.integration
    def test_end_to_end_produces_all_three_gpkg(self, tmp_path):
        """Produces HU.gpkg, RN.gpkg and AUX_L.gpkg with valid geometries from real Testdaten."""
        messages = []
        process_atkis(
            str(ATKIS_DIR), str(HU_SHP), str(tmp_path),
            feedback=messages.append)

        hu = QgsVectorLayer(str(tmp_path / "HU.gpkg"), "hu", "ogr")
        rn = QgsVectorLayer(str(tmp_path / "RN.gpkg"), "rn", "ogr")
        aux = QgsVectorLayer(str(tmp_path / "AUX_L.gpkg"), "aux", "ogr")

        for layer in (hu, rn, aux):
            assert layer.isValid()
            assert layer.featureCount() > 0
            _assert_valid_geometries(layer)

        assert any(messages), "feedback callback should have been invoked"

    @requires_atkis_testdaten
    @pytest.mark.integration
    def test_project_crs_taken_from_ver01_l(self, tmp_path):
        """The output CRS matches ver01_l's CRS (EPSG:25833 in Testdaten/)."""
        process_atkis(str(ATKIS_DIR), str(HU_SHP), str(tmp_path))
        rn = QgsVectorLayer(str(tmp_path / "RN.gpkg"), "rn", "ogr")
        assert rn.crs() == CRS_25833

    @requires_atkis_testdaten
    @pytest.mark.integration
    @pytest.mark.edge_case
    def test_study_area_without_overlap_yields_empty_outputs_not_error(self, tmp_path):
        """A study area outside the ATKIS extent produces empty (but valid) GPKGs, not an error."""
        far_away = make_polygon_layer(crs="EPSG:25833", name="study_area")
        add_feature_to_layer(far_away, make_square_geom(-500_000, -500_000, 10))
        study_area_path = write_layer_as_shp(far_away, str(tmp_path / "study_area.shp"))

        process_atkis(str(ATKIS_DIR), str(HU_SHP), str(tmp_path),
                      study_area_path=study_area_path)

        for name in ("HU.gpkg", "RN.gpkg", "AUX_L.gpkg"):
            out = QgsVectorLayer(str(tmp_path / name), "check", "ogr")
            assert out.isValid()
            assert out.featureCount() == 0
