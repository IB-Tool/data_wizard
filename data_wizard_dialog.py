# -*- coding: utf-8 -*-
import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'data_wizard_dialog_base.ui'))


def _skip_function_field_label():
    return QtWidgets.QApplication.translate(
        'Data_WizardDialog', "— no function code field / skip —")


class Data_WizardDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(Data_WizardDialog, self).__init__(parent)
        self.setupUi(self)
        self._hu_function_field = None
        self.btn_source.clicked.connect(self._browse_source)
        self.btn_hu.clicked.connect(self._browse_hu)
        self.btn_studyarea.clicked.connect(self._browse_studyarea)
        self.btn_target.clicked.connect(self._browse_target)
        self.lineEdit_hu.textChanged.connect(self._on_hu_text_changed)

    def _browse_source(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.tr("Select source folder"), self.lineEdit_source.text())
        if folder:
            self.lineEdit_source.setText(folder)

    def _browse_hu(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Select building footprint file"), self.lineEdit_hu.text(),
            self.tr("Vector files (*.shp *.gpkg)"))
        if path:
            self.lineEdit_hu.setText(path)
            self._resolve_hu_function_field(path)

    def _browse_studyarea(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, self.tr("Select study area"), self.lineEdit_studyarea.text(),
            self.tr("Vector files (*.shp *.gpkg)"))
        if path:
            self.lineEdit_studyarea.setText(path)

    def _browse_target(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, self.tr("Select target folder"), self.lineEdit_target.text())
        if folder:
            self.lineEdit_target.setText(folder)

    def _on_hu_text_changed(self, _text):
        """Verwirft eine zuvor erkannte Funktionscode-Spalte, sobald sich der
        Pfad ändert. _browse_hu ruft danach _resolve_hu_function_field auf,
        um sie für den neu gewählten Pfad wieder zu setzen; bei manueller
        Texteingabe bleibt sie auf None (= bisheriges Warnverhalten)."""
        self._hu_function_field = None

    def _resolve_hu_function_field(self, path):
        self._hu_function_field = None
        from .processor import detect_hu_function_field
        try:
            status, result = detect_hu_function_field(path)
        except ValueError as e:
            QtWidgets.QMessageBox.warning(self, "Data Wizard", str(e))
            return
        if status == 'ok':
            return
        if status == 'auto':
            self._hu_function_field = result
            return
        # status == 'ambiguous': Nutzer soll die Spalte wählen
        field_names = result
        skip_label = _skip_function_field_label()
        options = [skip_label] + field_names
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, self.tr("Select function code field"),
            self.tr("None of the expected columns (fkt/gfkzshh/funktion) found.\n"
                    "Which column contains the ATKIS function codes?"),
            options, 0, False)
        if ok and choice != skip_label:
            self._hu_function_field = choice

    def get_source_dir(self):
        return self.lineEdit_source.text().strip()

    def get_hu_file(self):
        return self.lineEdit_hu.text().strip()

    def get_hu_function_field(self):
        return self._hu_function_field

    def get_study_area_file(self):
        return self.lineEdit_studyarea.text().strip()

    def get_target_dir(self):
        return self.lineEdit_target.text().strip()
