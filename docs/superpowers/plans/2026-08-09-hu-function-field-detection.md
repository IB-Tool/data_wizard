# HU Function-Field Detection & Copy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **No git repository:** `data_wizard` is not a git repo. Skip every `git add`/`git commit` step — just save the files.

**Goal:** When the user's building-footprint file doesn't already have a `fkt`/`gfkzshh`/`funktion` column, detect the column that actually holds ATKIS function codes (heuristic first, dropdown fallback) and add a copy of it named `funktion` to the produced `HU.gpkg`.

**Architecture:** A new pure detection function (`detect_hu_function_field`) and a new field-copy helper (`_add_function_field_copy`) in `processor.py`; the dialog calls the detector synchronously when the user picks the building file (main thread, safe for `QMessageBox`/`QInputDialog`) and stores the result; the result flows through `data_wizard.py` → `_AtkisTask` → `process_atkis` → `_process_hu`, which performs the actual copy during processing.

**Tech Stack:** PyQGIS (`qgis.core`, `qgis.PyQt.QtCore.QVariant`, `qgis.PyQt.QtWidgets`), no QGIS test runner available in this environment — verification is `py_compile` plus a manual QGIS pass (Task 4).

---

### Task 1: Add detection + field-copy to `processor.py`

**Files:**
- Modify (full rewrite): `processor.py`

- [ ] **Step 1: Write the new file**

```python
# -*- coding: utf-8 -*-
"""
ATKIS Basis-DLM Verarbeitungslogik

Erzeugt aus ATKIS-Rohdaten und einer separat gewählten Gebäudedatei:
  HU.gpkg  – Gebäudegrundrisse (unverändert übernommen, alle Felder erhalten;
                          fehlt fkt/gfkzshh/funktion, wird eine erkannte
                          Funktionscode-Spalte als 'funktion' kopiert)
  RN.gpkg  – Straßennetz (ver01_l + ver02_l, gemerged, Singlepart)
  AUX.gpkg – Hilfslinien (ver03_l, veg02_f, veg03_f 43005/43006,
                          gew01_f, gew01_l → gemerged, Singlepart)

Ablauf: Das CRS von ver01_l wird als Projekt-CRS fixiert. Jeder Rohlayer
(inkl. Gebäudedatei und optionalem Untersuchungsgebiet) wird bei
abweichendem CRS automatisch reprojiziert. Ist ein Untersuchungsgebiet
angegeben, wird jeder Rohlayer darauf geklippt, bevor er weiterverarbeitet
wird.
"""

import os
import re
import processing
from qgis.core import (
    QgsVectorLayer, QgsVectorFileWriter, QgsWkbTypes,
    QgsCoordinateTransformContext, QgsFeature, QgsFields, QgsField,
    QgsProcessing,
)
from qgis.PyQt.QtCore import QVariant

HU_FUNCTION_FIELDS = ("fkt", "gfkzshh", "funktion")

# ATKIS-Objektartcode für Gebäude (AX_Gebaeude), siehe
# basis-dlm-aaa_ebenen_inhalt.csv. Funktionscode-Werte in HU haben die Form
# "31001_xxxx" (z.B. "31001_1000") — nur der 31001-Präfix ist plausibel für
# ein Gebäude-Funktionscode-Feld, ein generisches "5 Ziffern_4 Ziffern"
# Muster wäre zu unspezifisch.
FUNCTION_CODE_PATTERN = re.compile(r'^31001_\d{4}')


# ── Grundbausteine ──────────────────────────────────────────────────────

def _check_cancel(task):
    """Zentrale Abbruchprüfung – wird vor jedem teuren Schritt aufgerufen
    (Layer-Aufbereitung, processing.run, GeoPackage-Schreibschleife)."""
    if task and task.isCanceled():
        raise Exception("Verarbeitung abgebrochen.")


def _load_shp(source_dir, layer_name):
    """Lädt eine feste ATKIS-SHP-Datei direkt aus source_dir (kein
    rekursives Suchen in Unterordnern)."""
    path = os.path.join(source_dir, f"{layer_name}.shp")
    if not os.path.exists(path):
        raise FileNotFoundError(f"Datei nicht gefunden: {path}")
    layer = QgsVectorLayer(path, layer_name, "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {path}")
    return layer


def _reproject_if_needed(layer, target_crs, log=None, label="", task=None):
    """Reprojiziert layer nach target_crs, falls das CRS abweicht."""
    if layer.crs() == target_crs:
        return layer
    _check_cancel(task)
    if log:
        log(f"  {label}: reprojiziere {layer.crs().authid()} -> "
            f"{target_crs.authid()} ...")
    return processing.run("native:reprojectlayer", {
        'INPUT': layer,
        'TARGET_CRS': target_crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _clip_if_needed(layer, clip_mask, log=None, label="", task=None):
    """Klippt layer auf clip_mask, falls ein Untersuchungsgebiet gesetzt ist."""
    if clip_mask is None:
        return layer
    _check_cancel(task)
    if log:
        log(f"  {label}: klippe auf Untersuchungsgebiet ...")
    return processing.run("native:clip", {
        'INPUT': layer,
        'OVERLAY': clip_mask,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _prepare_layer(layer, target_crs, clip_mask, log=None, label="", task=None):
    """Reproject + Clip in dieser Reihenfolge (Clip braucht übereinstimmendes CRS)."""
    layer = _reproject_if_needed(layer, target_crs, log, label, task)
    layer = _clip_if_needed(layer, clip_mask, log, label, task)
    return layer


def _prepare_clip_mask(study_area_path, target_crs, log=None, task=None):
    """Lädt das optionale Untersuchungsgebiet, reprojiziert es und dissolved
    mehrere Polygone zu einer einzigen Clip-Maske. Gibt None zurück, wenn
    kein Untersuchungsgebiet angegeben wurde (= kein Zuschnitt)."""
    if not study_area_path:
        return None
    log_ = log or (lambda m: None)
    _check_cancel(task)
    log_("Untersuchungsgebiet: lade ...")
    layer = QgsVectorLayer(study_area_path, "study_area", "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {study_area_path}")
    layer = _reproject_if_needed(layer, target_crs, log, "Untersuchungsgebiet", task)
    if layer.featureCount() > 1:
        _check_cancel(task)
        log_("Untersuchungsgebiet: dissolve (mehrere Polygone) ...")
        layer = processing.run("native:dissolve", {
            'INPUT': layer,
            'FIELD': [],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        })['OUTPUT']
    return layer


def detect_hu_function_field(hu_path, sample_size=50):
    """
    Prüft, ob die Gebäudedatei bereits eines der erwarteten
    Funktionscode-Felder (fkt/gfkzshh/funktion) besitzt. Falls nicht,
    versucht eine Inhalts-Heuristik (ATKIS-Funktionscode-Muster
    '31001_xxxx', siehe FUNCTION_CODE_PATTERN) das richtige Feld zu
    erkennen.

    :param hu_path: Pfad zur Gebäudedatei (SHP/GPKG)
    :param sample_size: maximale Anzahl Features, die für die
        Inhaltsprüfung gelesen werden
    :returns: ('ok', None) wenn ein erwartetes Feld bereits existiert
        (nichts zu tun); ('auto', feldname) wenn genau ein Feld dem Muster
        entspricht; ('ambiguous', [alle Feldnamen]) wenn kein oder mehrere
        Felder passen — Aufrufer sollte den Nutzer eine Spalte wählen
        lassen.
    :raises ValueError: wenn hu_path nicht geladen werden kann.
    """
    layer = QgsVectorLayer(hu_path, "hu_probe", "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {hu_path}")

    field_names_lower = {f.name().lower() for f in layer.fields()}
    if field_names_lower & set(HU_FUNCTION_FIELDS):
        return ('ok', None)

    all_field_names = [f.name() for f in layer.fields()]
    samples = {name: [] for name in all_field_names}
    count = 0
    for feat in layer.getFeatures():
        if count >= sample_size:
            break
        count += 1
        for name in all_field_names:
            value = feat[name]
            if value is not None and value != '':
                samples[name].append(str(value))

    candidates = [
        name for name in all_field_names
        if samples[name] and all(
            FUNCTION_CODE_PATTERN.match(v) for v in samples[name])
    ]

    if len(candidates) == 1:
        return ('auto', candidates[0])
    return ('ambiguous', all_field_names)


def _add_function_field_copy(layer, source_field_name, target_field_name, log=None):
    """Fügt target_field_name als neues Textfeld hinzu und kopiert die
    Werte aus source_field_name hinein (für eine Gebäudedatei, deren
    Funktionscode-Spalte nicht fkt/gfkzshh/funktion heißt)."""
    if log:
        log(f"  HU: kopiere Feld '{source_field_name}' nach "
            f"'{target_field_name}' ...")
    if not layer.startEditing():
        raise ValueError(
            f"Layer nicht editierbar - Feld '{target_field_name}' konnte "
            f"nicht ergänzt werden.")
    layer.dataProvider().addAttributes(
        [QgsField(target_field_name, QVariant.String, len=254)])
    layer.updateFields()
    idx_new = layer.fields().indexFromName(target_field_name)
    idx_src = layer.fields().indexFromName(source_field_name)
    for feat in layer.getFeatures():
        value = feat[idx_src]
        layer.changeAttributeValue(
            feat.id(), idx_new, None if value is None else str(value))
    if not layer.commitChanges():
        raise ValueError(
            f"Änderungen konnten nicht übernommen werden beim Ergänzen "
            f"von '{target_field_name}'.")
    return layer


def _write_gpkg(input_layers, output_path, geometry_type,
                 force_singlepart, keep_fields, log=None, task=None):
    """
    Schreibt mehrere QgsVectorLayer-Objekte als ein GeoPackage.

    :param geometry_type: QgsWkbTypes-Konstante für den Ziel-Layer
    :param force_singlepart: Multipart-Geometrien werden beim Schreiben in
        ihre Einzelteile zerlegt (für RN/AUX per input-data.md gefordert;
        für HU nicht gesetzt, da für Polygone nicht vorgeschrieben)
    :param keep_fields: übernimmt die Feldstruktur des ersten Eingabe-Layers
        und kopiert sie je Feature (nötig für HU, damit
        fkt/gfkzshh/funktion erhalten bleibt). Setzt voraus, dass alle
        input_layers dasselbe Feldschema haben — bei HU ist das immer
        genau ein Layer.

    Alle input_layers müssen dasselbe CRS haben (wird von den Aufrufern
    über _prepare_layer sichergestellt); ein abweichendes CRS führt hier
    zu einem ValueError statt stillschweigend falsch georeferenzierter
    Geometrien im Ausgabe-GeoPackage.

    Kein Processing-Algorithmus – vollständig threadsicher.
    """
    first = input_layers[0]
    if not first.isValid():
        raise ValueError(f"Layer ungültig: {first.name()}")
    crs = first.crs()
    fields = first.fields() if keep_fields else QgsFields()

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"

    writer = QgsVectorFileWriter.create(
        output_path, fields, geometry_type,
        crs, QgsCoordinateTransformContext(), options)
    if writer.hasError() != QgsVectorFileWriter.NoError:
        raise IOError(
            f"Konnte GeoPackage nicht erstellen: {output_path} "
            f"({writer.errorMessage()})")

    for layer in input_layers:
        _check_cancel(task)
        if layer.crs().isValid() and layer.crs() != crs:
            raise ValueError(
                f"Layer '{layer.name()}' hat abweichendes CRS "
                f"({layer.crs().authid()} statt {crs.authid()})")
        if log:
            log(f"  Schreibe {layer.name()} ...")
        for feat in layer.getFeatures():
            geom = feat.geometry()
            if geom is None or geom.isNull() or geom.isEmpty():
                continue
            parts = geom.asGeometryCollection() if (
                force_singlepart and geom.isMultipart()) else [geom]
            for part in parts:
                nf = QgsFeature(fields) if keep_fields else QgsFeature()
                nf.setGeometry(part)
                if keep_fields:
                    nf.setAttributes(feat.attributes())
                writer.addFeature(nf)

    del writer


# ── HU ───────────────────────────────────────────────────────────────────

def _process_hu(hu_path, target_crs, clip_mask, target_dir, log=None,
                 task=None, function_field=None):
    log_ = log or (lambda m: None)
    log_("HU: lade Gebäudedatei ...")
    layer = QgsVectorLayer(hu_path, "hu", "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {hu_path}")

    field_names = {f.name().lower() for f in layer.fields()}
    has_function_field = bool(field_names & set(HU_FUNCTION_FIELDS))
    if not has_function_field and not function_field:
        log_(f"WARNUNG: HU enthält keines der Felder {HU_FUNCTION_FIELDS} "
             f"- die Funktionscode-Filterung in IBTool wird nicht "
             f"funktionieren.")

    _check_cancel(task)
    layer = _prepare_layer(layer, target_crs, clip_mask, log, "HU", task)

    if not has_function_field and function_field:
        _check_cancel(task)
        layer = _add_function_field_copy(layer, function_field, "funktion", log)

    _write_gpkg(
        [layer], os.path.join(target_dir, "HU.gpkg"),
        QgsWkbTypes.MultiPolygon, force_singlepart=False, keep_fields=True,
        log=log, task=task)
    log_("HU.gpkg fertig.")


# ── RN ───────────────────────────────────────────────────────────────────

def _process_rn(source_dir, target_crs, clip_mask, target_dir, log=None,
                 task=None, ver01_l=None):
    log_ = log or (lambda m: None)
    log_("RN: lade ver01_l + ver02_l ...")
    if ver01_l is None:
        ver01_l = _load_shp(source_dir, "ver01_l")
    _check_cancel(task)
    ver01_l = _prepare_layer(ver01_l, target_crs, clip_mask, log, "ver01_l", task)
    _check_cancel(task)
    ver02_l = _prepare_layer(
        _load_shp(source_dir, "ver02_l"), target_crs, clip_mask, log, "ver02_l", task)

    _write_gpkg(
        [ver01_l, ver02_l], os.path.join(target_dir, "RN.gpkg"),
        QgsWkbTypes.LineString, force_singlepart=True, keep_fields=False,
        log=log, task=task)
    log_("RN.gpkg fertig.")


# ── AUX ──────────────────────────────────────────────────────────────────

def _process_aux(source_dir, target_crs, clip_mask, target_dir, log=None, task=None):
    log_ = log or (lambda m: None)
    aux_inputs = []

    log_("AUX: füge ver03_l hinzu ...")
    _check_cancel(task)
    ver03_l = _prepare_layer(
        _load_shp(source_dir, "ver03_l"), target_crs, clip_mask, log, "ver03_l", task)
    aux_inputs.append(ver03_l)

    log_("AUX: veg02_f dissolve ...")
    _check_cancel(task)
    veg02_f = _prepare_layer(
        _load_shp(source_dir, "veg02_f"), target_crs, clip_mask, log, "veg02_f", task)
    _check_cancel(task)
    p_veg02_dis = processing.run("native:dissolve", {
        'INPUT': veg02_f, 'FIELD': [], 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg02_f Polygone zu Linien ...")
    _check_cancel(task)
    p_veg02_lines = processing.run("native:polygonstolines", {
        'INPUT': p_veg02_dis, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_veg02_lines)

    log_("AUX: veg03_f Filter 43005/43006 ...")
    _check_cancel(task)
    veg03_f = _prepare_layer(
        _load_shp(source_dir, "veg03_f"), target_crs, clip_mask, log, "veg03_f", task)
    _check_cancel(task)
    p_veg03_filt = processing.run("native:extractbyexpression", {
        'INPUT': veg03_f,
        'EXPRESSION': 'to_int("OBJART") IN (43005, 43006)',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg03_f dissolve ...")
    _check_cancel(task)
    p_veg03_dis = processing.run("native:dissolve", {
        'INPUT': p_veg03_filt, 'FIELD': [], 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg03_f Polygone zu Linien ...")
    _check_cancel(task)
    p_veg03_lines = processing.run("native:polygonstolines", {
        'INPUT': p_veg03_dis, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_veg03_lines)

    log_("AUX: gew01_f Polygone zu Linien ...")
    _check_cancel(task)
    gew01_f = _prepare_layer(
        _load_shp(source_dir, "gew01_f"), target_crs, clip_mask, log, "gew01_f", task)
    _check_cancel(task)
    p_gew01f_lines = processing.run("native:polygonstolines", {
        'INPUT': gew01_f, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_gew01f_lines)

    log_("AUX: füge gew01_l hinzu ...")
    _check_cancel(task)
    gew01_l = _prepare_layer(
        _load_shp(source_dir, "gew01_l"), target_crs, clip_mask, log, "gew01_l", task)
    aux_inputs.append(gew01_l)

    log_("AUX: merge + singlepart -> AUX.gpkg ...")
    _write_gpkg(
        aux_inputs, os.path.join(target_dir, "AUX.gpkg"),
        QgsWkbTypes.LineString, force_singlepart=True, keep_fields=False,
        log=log, task=task)
    log_("AUX.gpkg fertig.")


# ── Einstiegspunkt ───────────────────────────────────────────────────────

def process_atkis(source_dir, hu_path, target_dir, study_area_path=None,
                   hu_function_field=None, feedback=None, task=None):
    """
    :param source_dir: Ordner mit den ATKIS SHP-Dateien (ver01_l, ver02_l,
        ver03_l, veg02_f, veg03_f, gew01_f, gew01_l) — flach, ohne
        Unterordner-Suche
    :param hu_path: Pfad zur separat bereitgestellten Gebäudedatei (SHP/GPKG)
    :param target_dir: Ausgabeordner für HU.gpkg, RN.gpkg und AUX.gpkg
    :param study_area_path: optionaler Pfad zu einem Untersuchungsgebiet
        (SHP/GPKG); wenn gesetzt, werden alle Rohlayer darauf geklippt,
        sonst wird der volle Umfang der Rohdaten verarbeitet
    :param hu_function_field: optionaler Feldname in der Gebäudedatei, der
        als 'funktion' kopiert werden soll (siehe
        processor.detect_hu_function_field); wird ignoriert, wenn die
        Gebäudedatei bereits fkt/gfkzshh/funktion besitzt
    :param feedback: optionale Callback-Funktion für Statusmeldungen
    :param task: optionaler QgsTask – wird auf Abbruch geprüft
    """

    def log(msg):
        if feedback:
            feedback(msg)

    _check_cancel(task)
    log("Projekt-CRS: ermittle aus ver01_l ...")
    ver01_l_raw = _load_shp(source_dir, "ver01_l")
    target_crs = ver01_l_raw.crs()
    log(f"Projekt-CRS: {target_crs.authid()}")

    _check_cancel(task)
    clip_mask = _prepare_clip_mask(study_area_path, target_crs, log, task)

    _check_cancel(task)
    _process_hu(hu_path, target_crs, clip_mask, target_dir, log, task,
                function_field=hu_function_field)

    _check_cancel(task)
    _process_rn(source_dir, target_crs, clip_mask, target_dir, log, task,
                ver01_l=ver01_l_raw)

    _check_cancel(task)
    _process_aux(source_dir, target_crs, clip_mask, target_dir, log, task)
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile processor.py` (fall back to `python -m py_compile processor.py` or `py -m py_compile processor.py` if `python3` isn't found — prior tasks in this project found `python3` unreliable in this shell)
Expected: no output, exit code 0.

---

### Task 2: Wire detection into `data_wizard_dialog.py`

**Files:**
- Modify (full rewrite): `data_wizard_dialog.py`

- [ ] **Step 1: Write the new file**

```python
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
```

- [ ] **Step 2: Syntax check**

Run: `python -m py_compile data_wizard_dialog.py` (or `python3`/`py`, whichever resolves)
Expected: no output, exit code 0.

---

### Task 3: Wire `hu_function_field` through `data_wizard.py`

**Files:**
- Modify (full rewrite): `data_wizard.py`

- [ ] **Step 1: Write the new file**

```python
# -*- coding: utf-8 -*-
"""
/***************************************************************************
 Data_Wizard – QGIS Plugin
 Erzeugt IB-Tool-Eingabedaten aus ATKIS Basis-DLM SHP-Dateien.
 ***************************************************************************/
"""
from qgis.PyQt.QtCore import QSettings, QTranslator, QCoreApplication
from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction
from qgis.core import Qgis, QgsTask, QgsApplication, QgsMessageLog

from .resources import *
from .data_wizard_dialog import Data_WizardDialog
import os.path


class _AtkisTask(QgsTask):
    """Führt die ATKIS-Verarbeitung in einem Hintergrund-Thread aus."""

    def __init__(self, source_dir, hu_path, target_dir, study_area_path,
                 hu_function_field, iface):
        super().__init__("ATKIS Verarbeitung", QgsTask.CanCancel)
        self.source_dir = source_dir
        self.hu_path = hu_path
        self.target_dir = target_dir
        self.study_area_path = study_area_path
        self.hu_function_field = hu_function_field
        self.iface = iface
        self.exception = None

    def run(self):
        """Läuft im Hintergrund-Thread."""
        try:
            from .processor import process_atkis

            def log(msg):
                QgsMessageLog.logMessage(msg, "Data Wizard", Qgis.Info)

            process_atkis(self.source_dir, self.hu_path, self.target_dir,
                          study_area_path=self.study_area_path,
                          hu_function_field=self.hu_function_field,
                          feedback=log, task=self)
            return True
        except Exception as e:
            self.exception = e
            QgsMessageLog.logMessage(str(e), "Data Wizard", Qgis.Critical)
            return False

    def finished(self, result):
        """Läuft im Haupt-Thread – sicher für UI-Zugriff."""
        if result:
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Fertig – HU.gpkg, RN.gpkg und AUX.gpkg in: {self.target_dir}",
                level=Qgis.Success,
                duration=8)
        elif self.isCanceled():
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                "Verarbeitung abgebrochen.",
                level=Qgis.Info,
                duration=5)
        else:
            msg = str(self.exception) if self.exception else "Unbekannter Fehler"
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Fehler: {msg}",
                level=Qgis.Critical,
                duration=10)


class Data_Wizard:
    """QGIS Plugin Implementation."""

    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        locale = QSettings().value('locale/userLocale')[0:2]
        locale_path = os.path.join(
            self.plugin_dir, 'i18n',
            'Data_Wizard_{}.qm'.format(locale))
        if os.path.exists(locale_path):
            self.translator = QTranslator()
            self.translator.load(locale_path)
            QCoreApplication.installTranslator(self.translator)

        self.actions = []
        self.menu = self.tr(u'&IB-Tool-Data-Wizard')
        self.first_start = None
        self.task = None

    def tr(self, message):
        return QCoreApplication.translate('Data_Wizard', message)

    def add_action(self, icon_path, text, callback,
                   enabled_flag=True, add_to_menu=True,
                   add_to_toolbar=True, status_tip=None,
                   whats_this=None, parent=None):
        icon = QIcon(icon_path)
        action = QAction(icon, text, parent)
        action.triggered.connect(callback)
        action.setEnabled(enabled_flag)
        if status_tip is not None:
            action.setStatusTip(status_tip)
        if whats_this is not None:
            action.setWhatsThis(whats_this)
        if add_to_toolbar:
            self.iface.addToolBarIcon(action)
        if add_to_menu:
            self.iface.addPluginToMenu(self.menu, action)
        self.actions.append(action)
        return action

    def initGui(self):
        icon_path = ':/plugins/data_wizard/icon.png'
        self.add_action(
            icon_path,
            text=self.tr(u'IB-Tool-Data-Wizard'),
            callback=self.run,
            parent=self.iface.mainWindow())
        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(
                self.tr(u'&IB-Tool-Data-Wizard'), action)
            self.iface.removeToolBarIcon(action)

    def run(self):
        if self.first_start:
            self.first_start = False
            self.dlg = Data_WizardDialog()

        self.dlg.show()
        result = self.dlg.exec_()

        if not result:
            return

        if self.task is not None and self.task.status() in (QgsTask.Queued, QgsTask.Running):
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                "Eine Verarbeitung läuft bereits – bitte warten.",
                level=Qgis.Warning, duration=5)
            return

        source_dir = self.dlg.get_source_dir()
        hu_path = self.dlg.get_hu_file()
        hu_function_field = self.dlg.get_hu_function_field()
        study_area_path = self.dlg.get_study_area_file()
        target_dir = self.dlg.get_target_dir()

        if not source_dir or not hu_path or not target_dir:
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                "Bitte Quellordner, Gebäudedatei und Zielordner angeben.",
                level=Qgis.Warning, duration=5)
            return

        if not os.path.isdir(source_dir):
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Quellordner nicht gefunden: {source_dir}",
                level=Qgis.Warning, duration=5)
            return

        if not os.path.isfile(hu_path):
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Gebäudedatei nicht gefunden: {hu_path}",
                level=Qgis.Warning, duration=5)
            return

        if not os.path.isdir(target_dir):
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Zielordner nicht gefunden: {target_dir}",
                level=Qgis.Warning, duration=5)
            return

        if study_area_path and not os.path.isfile(study_area_path):
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Untersuchungsgebiet-Datei nicht gefunden: {study_area_path}",
                level=Qgis.Warning, duration=5)
            return

        self.task = _AtkisTask(source_dir, hu_path, target_dir,
                                study_area_path or None, hu_function_field,
                                self.iface)
        QgsApplication.taskManager().addTask(self.task)

        self.iface.messageBar().pushMessage(
            "Data Wizard",
            "Verarbeitung läuft im Hintergrund – siehe Task-Manager und Log-Meldungen.",
            level=Qgis.Info, duration=5)
```

- [ ] **Step 2: Syntax check**

Run: `python -m py_compile data_wizard.py` (or `python3`/`py`, whichever resolves)
Expected: no output, exit code 0.

---

### Task 4: Manual end-to-end verification in QGIS

QGIS is not available in this shell. Run by the user in their real QGIS Desktop install.

**Files:**
- None (manual QGIS session)

- [ ] **Step 1: Reload the plugin**

In QGIS: Plugin Reloader (or restart QGIS) so the edited files are picked up.

- [ ] **Step 2: Auto-detect case**

Prepare (or find) a building file whose function-code column is named
something other than `fkt`/`gfkzshh`/`funktion`, but is the *only* column
whose values look like `31001_xxxx`. Pick it via "Gebäudedatei wählen".

Expected: no dialog pops up (silent auto-detection); after a full run,
`HU.gpkg` has both the original column and a new `funktion` column with
identical values.

- [ ] **Step 3: Ambiguous case**

Prepare a building file where either no column matches the `31001_xxxx`
pattern, or more than one does. Pick it via "Gebäudedatei wählen".

Expected: a dropdown appears listing all columns plus "kein
Funktionscode-Feld / überspringen". Pick the correct column, run, and
confirm `HU.gpkg` gets a `funktion` column with the right values. Repeat,
this time choosing the skip option — confirm the run still completes and
`HU.gpkg` has no extra `funktion` column, same as before this feature.

- [ ] **Step 4: Already-correct case**

Pick a building file that already has `fkt`, `gfkzshh`, or `funktion`.

Expected: no dialog, no extra column added — behavior identical to before
this feature (the existing field is used as-is).

- [ ] **Step 5: Manual-edit invalidation**

Pick a building file via the browse button (triggers auto-detection or the
dropdown), then manually edit the text in the "Gebäudedatei" field to a
different path (without using the browse button) and start a run.

Expected: the previously detected field is not applied to the new path —
`HU.gpkg` for the manually-typed file falls back to the original
warning-only behavior (log warning if no expected field, no extra column
added), confirming the `textChanged` invalidation works.

---

## Self-Review Notes

- **Spec coverage:** heuristic against the fixed `31001_` object-art code
  (Task 1: `FUNCTION_CODE_PATTERN`), trigger on file-picker selection only
  (Task 2: `_browse_hu` calls `_resolve_hu_function_field`), dropdown
  fallback with skip option (Task 2: `_resolve_hu_function_field`
  ambiguous branch), fixed target name `funktion` (Task 1:
  `_process_hu`'s `_add_function_field_copy(..., "funktion", ...)` call),
  original column preserved (Task 1: `_add_function_field_copy` only adds
  a field, never removes/renames the source), manual-edit invalidation
  (Task 2: `_on_hu_text_changed`) — all covered.
- **Placeholder scan:** none.
- **Type consistency:** `process_atkis(..., hu_function_field=None, ...)`
  (Task 1) matches the call in Task 3's `_AtkisTask.run()`
  (`hu_function_field=self.hu_function_field`); `get_hu_function_field()`
  (Task 2) matches its use in Task 3's `Data_Wizard.run()`;
  `_process_hu(..., function_field=None)` (Task 1) matches
  `process_atkis`'s call to it (`function_field=hu_function_field`).
