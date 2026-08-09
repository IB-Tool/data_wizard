# -*- coding: utf-8 -*-
import os

from qgis.PyQt import uic
from qgis.PyQt import QtWidgets

FORM_CLASS, _ = uic.loadUiType(os.path.join(
    os.path.dirname(__file__), 'data_wizard_dialog_base.ui'))

SKIP_FUNCTION_FIELD_LABEL = "— kein Funktionscode-Feld / überspringen —"


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
            self, "Quellordner wählen", self.lineEdit_source.text())
        if folder:
            self.lineEdit_source.setText(folder)

    def _browse_hu(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Gebäudedatei wählen", self.lineEdit_hu.text(),
            "Vektordateien (*.shp *.gpkg)")
        if path:
            self.lineEdit_hu.setText(path)
            self._resolve_hu_function_field(path)

    def _browse_studyarea(self):
        path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self, "Untersuchungsgebiet wählen", self.lineEdit_studyarea.text(),
            "Vektordateien (*.shp *.gpkg)")
        if path:
            self.lineEdit_studyarea.setText(path)

    def _browse_target(self):
        folder = QtWidgets.QFileDialog.getExistingDirectory(
            self, "Zielordner wählen", self.lineEdit_target.text())
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
        options = [SKIP_FUNCTION_FIELD_LABEL] + field_names
        choice, ok = QtWidgets.QInputDialog.getItem(
            self, "Funktionscode-Feld wählen",
            "Keine der erwarteten Spalten (fkt/gfkzshh/funktion) gefunden.\n"
            "Welche Spalte enthält die ATKIS-Funktionscodes?",
            options, 0, False)
        if ok and choice != SKIP_FUNCTION_FIELD_LABEL:
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
