# -*- coding: utf-8 -*-
"""Tests for data_wizard.py - Data_Wizard plugin class and _AtkisTask.

Unlike ibtoolpartion's test_ibtoolpartion.py, this file does not need a
sys.modules mock of qgis.* - QGIS actually imports and initialises correctly
in this plugin's test environment (see test/utilities.py), so the real
Data_Wizard / _AtkisTask classes are exercised against a MagicMock iface
instead of a fully mocked QGIS stack. This is simpler and closer to the
production import path.
"""

from unittest.mock import MagicMock

import pytest
from qgis.core import Qgis
from qgis.PyQt.QtCore import QSettings

from .utilities import get_qgis_app

QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()

from data_wizard.data_wizard import Data_Wizard, _AtkisTask  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _locale_setting():
    """Data_Wizard.__init__ reads QSettings 'locale/userLocale' and slices
    the result unconditionally (locale = ...value(...)[0:2]). QGIS Desktop
    always has this set, but a bare test environment does not, which would
    raise TypeError: 'NoneType' object is not subscriptable outside of it.
    Set a value up front so construction matches the real-world case that
    the code was written for. NOTE: this is a real fragility in
    data_wizard.py, not just a test gap - see docs/test-strategy.md ->
    Gap Analysis."""
    QSettings().setValue('locale/userLocale', 'de_DE')
    yield


@pytest.fixture
def mock_iface():
    """Fresh mock QGIS interface for each test.

    mainWindow() must return a real QObject (not a MagicMock) because
    add_action() passes it straight into QAction(icon, text, parent) -
    PyQt's sip bindings reject a non-QObject parent with a TypeError.
    """
    iface = MagicMock()
    iface.mainWindow.return_value = _PARENT
    iface.messageBar.return_value = MagicMock()
    return iface


@pytest.fixture
def plugin(mock_iface):
    """Fresh Data_Wizard instance for each test."""
    return Data_Wizard(mock_iface)


def _prepare_dialog(plugin_, *, source_dir="", hu_file="", target_dir="",
                    study_area="", hu_function_field=None):
    """Configure a mock dialog so run() skips real dialog creation/exec_()."""
    plugin_.first_start = False
    mock_dlg = MagicMock()
    mock_dlg.exec_.return_value = 1  # QDialog.Accepted-ish truthy value
    mock_dlg.get_source_dir.return_value = source_dir
    mock_dlg.get_hu_file.return_value = hu_file
    mock_dlg.get_hu_function_field.return_value = hu_function_field
    mock_dlg.get_study_area_file.return_value = study_area
    mock_dlg.get_target_dir.return_value = target_dir
    plugin_.dlg = mock_dlg
    return mock_dlg


# ===========================================================================
# Data_Wizard.__init__
# ===========================================================================

class TestDataWizardInit:
    """Tests for Data_Wizard.__init__."""

    @pytest.mark.unit
    def test_iface_is_stored(self, plugin, mock_iface):
        """Stores the iface argument as self.iface."""
        assert plugin.iface is mock_iface

    @pytest.mark.unit
    def test_first_start_is_none_before_initgui(self, plugin):
        """first_start is None before initGui() has been called."""
        assert plugin.first_start is None

    @pytest.mark.unit
    def test_actions_list_is_empty_on_creation(self, plugin):
        """actions list is empty directly after construction."""
        assert plugin.actions == []

    @pytest.mark.unit
    def test_task_running_is_false_on_creation(self, plugin):
        """_task_running starts False."""
        assert plugin._task_running is False

    @pytest.mark.unit
    def test_task_is_none_on_creation(self, plugin):
        """task starts as None."""
        assert plugin.task is None


# ===========================================================================
# Data_Wizard.tr
# ===========================================================================

class TestDataWizardTr:
    """Tests for Data_Wizard.tr."""

    @pytest.mark.unit
    def test_tr_returns_the_input_message_without_a_translation_installed(self, plugin):
        """tr() returns the message unchanged when no translator is installed for the locale."""
        assert plugin.tr("Hello") == "Hello"


# ===========================================================================
# Data_Wizard.add_action
# ===========================================================================

class TestDataWizardAddAction:
    """Tests for Data_Wizard.add_action."""

    @pytest.mark.unit
    def test_returns_a_non_none_action(self, plugin):
        """add_action() returns the created action object."""
        action = plugin.add_action(":/icon.png", "Test", lambda: None, parent=None)
        assert action is not None

    @pytest.mark.unit
    def test_appends_action_to_self_actions(self, plugin):
        """add_action() appends the new action to self.actions."""
        before = len(plugin.actions)
        plugin.add_action(":/icon.png", "Test", lambda: None, parent=None)
        assert len(plugin.actions) == before + 1

    @pytest.mark.unit
    def test_calls_addtoolbaricon_when_enabled(self, plugin, mock_iface):
        """add_action() calls iface.addToolBarIcon when add_to_toolbar=True."""
        plugin.add_action(":/icon.png", "Test", lambda: None,
                          add_to_toolbar=True, parent=None)
        mock_iface.addToolBarIcon.assert_called()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_skips_addtoolbaricon_when_disabled(self, plugin, mock_iface):
        """add_action() does not call iface.addToolBarIcon when add_to_toolbar=False."""
        plugin.add_action(":/icon.png", "Test", lambda: None,
                          add_to_toolbar=False, parent=None)
        mock_iface.addToolBarIcon.assert_not_called()

    @pytest.mark.unit
    def test_calls_addplugintomenu_when_enabled(self, plugin, mock_iface):
        """add_action() calls iface.addPluginToMenu when add_to_menu=True."""
        plugin.add_action(":/icon.png", "Test", lambda: None,
                          add_to_menu=True, parent=None)
        mock_iface.addPluginToMenu.assert_called()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_skips_addplugintomenu_when_disabled(self, plugin, mock_iface):
        """add_action() does not call iface.addPluginToMenu when add_to_menu=False."""
        plugin.add_action(":/icon.png", "Test", lambda: None,
                          add_to_menu=False, parent=None)
        mock_iface.addPluginToMenu.assert_not_called()


# ===========================================================================
# Data_Wizard.initGui / unload
# ===========================================================================

class TestDataWizardInitGui:
    """Tests for Data_Wizard.initGui."""

    @pytest.mark.unit
    def test_sets_first_start_to_true(self, plugin):
        """initGui() sets first_start to True."""
        plugin.initGui()
        assert plugin.first_start is True

    @pytest.mark.unit
    def test_registers_exactly_one_action(self, plugin):
        """initGui() adds exactly one entry to self.actions."""
        count_before = len(plugin.actions)
        plugin.initGui()
        assert len(plugin.actions) == count_before + 1


class TestDataWizardUnload:
    """Tests for Data_Wizard.unload."""

    @pytest.mark.unit
    def test_calls_removetoolbaricon_for_every_action(self, plugin, mock_iface):
        """unload() calls iface.removeToolBarIcon for every registered action."""
        plugin.initGui()
        mock_iface.removeToolBarIcon.reset_mock()
        plugin.unload()
        assert mock_iface.removeToolBarIcon.call_count >= 1

    @pytest.mark.unit
    def test_calls_removepluginmenu_for_every_action(self, plugin, mock_iface):
        """unload() calls iface.removePluginMenu for every registered action."""
        plugin.initGui()
        mock_iface.removePluginMenu.reset_mock()
        plugin.unload()
        assert mock_iface.removePluginMenu.call_count >= 1


# ===========================================================================
# Data_Wizard.run() - validation paths
# ===========================================================================

class TestDataWizardRunValidation:
    """Tests for input validation inside Data_Wizard.run()."""

    @pytest.mark.unit
    def test_missing_source_dir_triggers_warning(self, plugin, mock_iface):
        """run() pushes a warning when source_dir is empty."""
        _prepare_dialog(plugin, source_dir="", hu_file="x.shp", target_dir=".")
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_missing_hu_path_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when hu_path is empty."""
        _prepare_dialog(plugin, source_dir=str(tmp_path), hu_file="", target_dir=str(tmp_path))
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_missing_target_dir_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when target_dir is empty."""
        hu_file = tmp_path / "hu.shp"
        hu_file.write_text("x")
        _prepare_dialog(plugin, source_dir=str(tmp_path), hu_file=str(hu_file), target_dir="")
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_nonexistent_source_dir_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when source_dir does not exist on disk."""
        hu_file = tmp_path / "hu.shp"
        hu_file.write_text("x")
        _prepare_dialog(plugin, source_dir=str(tmp_path / "does_not_exist"),
                        hu_file=str(hu_file), target_dir=str(tmp_path))
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_nonexistent_hu_file_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when hu_path does not exist on disk."""
        _prepare_dialog(plugin, source_dir=str(tmp_path),
                        hu_file=str(tmp_path / "missing.shp"), target_dir=str(tmp_path))
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_nonexistent_target_dir_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when target_dir does not exist on disk."""
        hu_file = tmp_path / "hu.shp"
        hu_file.write_text("x")
        _prepare_dialog(plugin, source_dir=str(tmp_path), hu_file=str(hu_file),
                        target_dir=str(tmp_path / "does_not_exist"))
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_nonexistent_study_area_triggers_warning(self, plugin, mock_iface, tmp_path):
        """run() pushes a warning when a non-empty study_area_path does not exist."""
        hu_file = tmp_path / "hu.shp"
        hu_file.write_text("x")
        _prepare_dialog(plugin, source_dir=str(tmp_path), hu_file=str(hu_file),
                        target_dir=str(tmp_path), study_area=str(tmp_path / "missing.shp"))
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_called()

    @pytest.mark.unit
    def test_returns_early_when_dialog_rejected(self, plugin, mock_iface, tmp_path):
        """run() returns without validation or pushMessage when the dialog is cancelled."""
        mock_dlg = _prepare_dialog(plugin, source_dir=str(tmp_path))
        mock_dlg.exec_.return_value = 0  # QDialog.Rejected
        plugin.run()
        mock_iface.messageBar.return_value.pushMessage.assert_not_called()


class TestDataWizardRunTaskGuard:
    """Tests for the _task_running guard inside Data_Wizard.run()."""

    @pytest.mark.unit
    def test_second_call_while_task_running_is_rejected(self, plugin, mock_iface, tmp_path):
        """A second run() call while a task is already running is rejected with a warning."""
        hu_file = tmp_path / "hu.shp"
        hu_file.write_text("x")
        _prepare_dialog(plugin, source_dir=str(tmp_path), hu_file=str(hu_file),
                        target_dir=str(tmp_path))
        plugin._task_running = True

        plugin.run()

        mock_iface.messageBar.return_value.pushMessage.assert_called_once()
        args, kwargs = mock_iface.messageBar.return_value.pushMessage.call_args
        assert kwargs.get("level") == Qgis.Warning


class TestDataWizardOnTaskFinished:
    """Tests for Data_Wizard._on_task_finished."""

    @pytest.mark.unit
    def test_resets_task_running_to_false(self, plugin):
        """_on_task_finished() sets _task_running back to False."""
        plugin._task_running = True
        plugin._on_task_finished()
        assert plugin._task_running is False


# ===========================================================================
# _AtkisTask.run()
# ===========================================================================

class TestAtkisTaskRun:
    """Tests for _AtkisTask.run()."""

    @pytest.mark.unit
    def test_returns_false_and_sets_exception_on_failure(self, mock_iface, tmp_path):
        """run() returns False and stores the raised exception when process_atkis fails."""
        task = _AtkisTask(
            source_dir=str(tmp_path / "does_not_exist"),
            hu_path=str(tmp_path / "missing_hu.shp"),
            target_dir=str(tmp_path),
            study_area_path=None,
            hu_function_field=None,
            iface=mock_iface)

        result = task.run()

        assert result is False
        assert task.exception is not None
        assert isinstance(task.exception, Exception)


# ===========================================================================
# _AtkisTask.finished()
# ===========================================================================

class TestAtkisTaskFinished:
    """Tests for _AtkisTask.finished() in its three branches."""

    def _make_task(self, mock_iface, on_finished=None):
        return _AtkisTask(
            source_dir="src", hu_path="hu.shp", target_dir="target",
            study_area_path=None, hu_function_field=None,
            iface=mock_iface, on_finished=on_finished)

    @pytest.mark.unit
    def test_success_pushes_success_message_and_calls_on_finished(self, mock_iface):
        """finished(True) pushes a Success message and invokes on_finished()."""
        calls = []
        task = self._make_task(mock_iface, on_finished=lambda: calls.append(1))

        task.finished(True)

        assert calls == [1]
        _, kwargs = mock_iface.messageBar.return_value.pushMessage.call_args
        assert kwargs.get("level") == Qgis.Success

    @pytest.mark.unit
    @pytest.mark.edge_case
    def test_cancelled_pushes_info_message(self, mock_iface):
        """finished(False) after task.cancel() pushes an Info 'cancelled' message."""
        task = self._make_task(mock_iface)
        task.cancel()
        assert task.isCanceled() is True

        task.finished(False)

        _, kwargs = mock_iface.messageBar.return_value.pushMessage.call_args
        assert kwargs.get("level") == Qgis.Info

    @pytest.mark.unit
    def test_error_pushes_critical_message_with_exception_text(self, mock_iface):
        """finished(False) with a stored exception (not cancelled) pushes a Critical message."""
        task = self._make_task(mock_iface)
        task.exception = ValueError("boom")

        task.finished(False)

        args, kwargs = mock_iface.messageBar.return_value.pushMessage.call_args
        assert kwargs.get("level") == Qgis.Critical
        assert "boom" in args[1]
