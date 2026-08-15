# coding=utf-8
"""Dialog test.

.. note:: This program is free software; you can redistribute it and/or modify
     it under the terms of the GNU General Public License as published by
     the Free Software Foundation; either version 2 of the License, or
     (at your option) any later version.

"""

__author__ = 'ottmar.hittzfeld@web.de'
__date__ = '2026-03-01'
__copyright__ = 'Copyright 2026, Oliver Harig'

import unittest
from unittest.mock import patch

import pytest
from qgis.PyQt.QtWidgets import QDialogButtonBox, QDialog

from .utilities import get_qgis_app

# Was: `QGIS_APP = get_qgis_app()`, binding the whole 4-tuple to one name -
# unused here, but a latent bug: any future use of QGIS_APP as "the app"
# object would actually get the tuple.
QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

# Was: `from data_wizard_dialog import Data_WizardDialog` - a bare import
# that only resolved because the container's CWD happened to be the plugin
# folder. The absolute package import below matches every other test file
# in this suite and resolves the same way locally and in Docker.
from data_wizard.data_wizard_dialog import Data_WizardDialog, _skip_function_field_label


class Data_WizardDialogTest(unittest.TestCase):
    """Test dialog works."""

    def setUp(self):
        """Runs before each test."""
        self.dialog = Data_WizardDialog(None)

    def tearDown(self):
        """Runs after each test."""
        self.dialog = None

    @pytest.mark.unit
    def test_dialog_ok(self):
        """Test we can click OK."""

        button = self.dialog.button_box.button(QDialogButtonBox.Ok)
        button.click()
        result = self.dialog.result()
        self.assertEqual(result, QDialog.Accepted)

    @pytest.mark.unit
    def test_dialog_cancel(self):
        """Test we can click cancel."""
        button = self.dialog.button_box.button(QDialogButtonBox.Cancel)
        button.click()
        result = self.dialog.result()
        self.assertEqual(result, QDialog.Rejected)


if __name__ == "__main__":
    suite = unittest.makeSuite(Data_WizardDialogTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)


# ===========================================================================
# Getters
# ===========================================================================

class TestDataWizardDialogGetters:
    """Tests for the get_*() accessor methods."""

    @pytest.fixture
    def dialog(self):
        return Data_WizardDialog(None)

    @pytest.mark.unit
    def test_get_source_dir_strips_whitespace(self, dialog):
        """get_source_dir() strips leading/trailing whitespace from the field."""
        dialog.lineEdit_source.setText("  /some/source  ")
        assert dialog.get_source_dir() == "/some/source"

    @pytest.mark.unit
    def test_get_hu_file_strips_whitespace(self, dialog):
        """get_hu_file() strips leading/trailing whitespace from the field."""
        dialog.lineEdit_hu.setText("  /some/hu.shp  ")
        assert dialog.get_hu_file() == "/some/hu.shp"

    @pytest.mark.unit
    def test_get_study_area_file_strips_whitespace(self, dialog):
        """get_study_area_file() strips leading/trailing whitespace from the field."""
        dialog.lineEdit_studyarea.setText("  /some/area.shp  ")
        assert dialog.get_study_area_file() == "/some/area.shp"

    @pytest.mark.unit
    def test_get_target_dir_strips_whitespace(self, dialog):
        """get_target_dir() strips leading/trailing whitespace from the field."""
        dialog.lineEdit_target.setText("  /some/target  ")
        assert dialog.get_target_dir() == "/some/target"

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_getters_return_empty_string_for_empty_fields(self, dialog):
        """All get_*() accessors return '' (not None) when the field is empty."""
        assert dialog.get_source_dir() == ""
        assert dialog.get_hu_file() == ""
        assert dialog.get_study_area_file() == ""
        assert dialog.get_target_dir() == ""

    @pytest.mark.unit
    def test_get_hu_function_field_is_none_initially(self, dialog):
        """get_hu_function_field() returns None before any HU file was resolved."""
        assert dialog.get_hu_function_field() is None


# ===========================================================================
# _on_hu_text_changed
# ===========================================================================

class TestOnHuTextChanged:
    """Tests for _on_hu_text_changed."""

    @pytest.fixture
    def dialog(self):
        return Data_WizardDialog(None)

    @pytest.mark.unit
    def test_resets_hu_function_field_to_none(self, dialog):
        """Any text change on the HU field clears a previously resolved function field."""
        dialog._hu_function_field = "gfkzshh"
        dialog._on_hu_text_changed("new/path.shp")
        assert dialog._hu_function_field is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_manual_text_edit_via_linetext_setText_also_resets(self, dialog):
        """Editing lineEdit_hu directly (not via _browse_hu) also resets the field
        - this is the documented behavior difference: manual edits do not
        re-run detection, so the field stays None until the next _browse_hu."""
        dialog._hu_function_field = "gfkzshh"
        dialog.lineEdit_hu.setText("manually/typed/path.shp")
        assert dialog._hu_function_field is None


# ===========================================================================
# _resolve_hu_function_field
# ===========================================================================

class TestResolveHuFunctionField:
    """Tests for _resolve_hu_function_field's four branches."""

    @pytest.fixture
    def dialog(self):
        return Data_WizardDialog(None)

    @pytest.mark.unit
    def test_ok_status_leaves_function_field_none(self, dialog):
        """status='ok' (field already present) leaves _hu_function_field at None."""
        with patch("data_wizard.processor.detect_hu_function_field",
                   return_value=('ok', None)):
            dialog._resolve_hu_function_field("hu.shp")
        assert dialog._hu_function_field is None

    @pytest.mark.unit
    def test_auto_status_sets_function_field(self, dialog):
        """status='auto' sets _hu_function_field to the detected column name."""
        with patch("data_wizard.processor.detect_hu_function_field",
                   return_value=('auto', 'gfkz_code')):
            dialog._resolve_hu_function_field("hu.shp")
        assert dialog._hu_function_field == 'gfkz_code'

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_ambiguous_status_uses_user_selected_field(self, dialog):
        """status='ambiguous' sets _hu_function_field to the user's QInputDialog choice."""
        with (
            patch("data_wizard.processor.detect_hu_function_field",
                  return_value=('ambiguous', ['field_a', 'field_b'])),
            patch("data_wizard.data_wizard_dialog.QtWidgets.QInputDialog.getItem",
                  return_value=('field_b', True)),
        ):
            dialog._resolve_hu_function_field("hu.shp")
        assert dialog._hu_function_field == 'field_b'

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_ambiguous_status_skip_choice_leaves_field_none(self, dialog):
        """Choosing the '- skip -' option in the ambiguous case leaves the field at None."""
        skip_label = _skip_function_field_label()
        with (
            patch("data_wizard.processor.detect_hu_function_field",
                  return_value=('ambiguous', ['field_a', 'field_b'])),
            patch("data_wizard.data_wizard_dialog.QtWidgets.QInputDialog.getItem",
                  return_value=(skip_label, True)),
        ):
            dialog._resolve_hu_function_field("hu.shp")
        assert dialog._hu_function_field is None

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_ambiguous_status_dialog_cancelled_leaves_field_none(self, dialog):
        """Cancelling the QInputDialog (ok=False) leaves the field at None."""
        with (
            patch("data_wizard.processor.detect_hu_function_field",
                  return_value=('ambiguous', ['field_a', 'field_b'])),
            patch("data_wizard.data_wizard_dialog.QtWidgets.QInputDialog.getItem",
                  return_value=('field_a', False)),
        ):
            dialog._resolve_hu_function_field("hu.shp")
        assert dialog._hu_function_field is None

    @pytest.mark.unit
    def test_value_error_shows_warning_and_leaves_field_none(self, dialog):
        """A ValueError from detect_hu_function_field shows a QMessageBox warning."""
        with (
            patch("data_wizard.processor.detect_hu_function_field",
                  side_effect=ValueError("Layer ungültig: hu.shp")),
            patch("data_wizard.data_wizard_dialog.QtWidgets.QMessageBox.warning") as mock_warn,
        ):
            dialog._resolve_hu_function_field("hu.shp")
        mock_warn.assert_called_once()
        assert dialog._hu_function_field is None
