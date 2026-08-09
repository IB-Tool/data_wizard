# Data Preparation Automation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **No git repository:** `data_wizard` is not currently a git repo (`git status` → "fatal: not a git repository"). Skip every `git add`/`git commit` step below unless the user has initialized git first — just save the files.

**Goal:** Rework `data_wizard` so that, given a folder of raw ATKIS data and a separately chosen building-footprint file, it automatically produces `HU.gpkg`, `RN.gpkg`, and `AUX.gpkg` — reprojecting and (optionally) clipping every input first — matching the workflow in `docs/data-preparation.md`.

**Architecture:** `processor.py` is rewritten around a shared `_write_gpkg()` writer (handles both the "keep all fields, no forced singlepart" case for HU and the "no fields, forced singlepart" case for RN/Aux) plus two small `_reproject_if_needed()` / `_clip_if_needed()` helpers applied uniformly to every raw input before layer-specific processing. The dialog gains two new fields (HU file picker, optional study-area file picker); `data_wizard.py` wires them through to the new `process_atkis()` signature.

**Tech Stack:** PyQGIS (`qgis.core`, `qgis.processing`), Qt Designer `.ui` file, no QGIS test runner available in this environment — verification for QGIS-dependent behavior is manual (Task 5). `python3` (no `qgis` module) is available for plain syntax checks (`py_compile`) and XML well-formedness checks.

---

### Task 1: Rewrite `processor.py`

**Files:**
- Modify (full rewrite): `processor.py`

- [ ] **Step 1: Write the new file**

```python
# -*- coding: utf-8 -*-
"""
ATKIS Basis-DLM Verarbeitungslogik

Erzeugt aus ATKIS-Rohdaten und einer separat gewählten Gebäudedatei:
  HU.gpkg  – Gebäudegrundrisse (unverändert übernommen, alle Felder erhalten)
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
import processing
from qgis.core import (
    QgsVectorLayer, QgsVectorFileWriter, QgsWkbTypes,
    QgsCoordinateTransformContext, QgsFeature, QgsFields,
    QgsProcessing,
)

HU_FUNCTION_FIELDS = ("fkt", "gfkzshh", "funktion")


# ── Grundbausteine ──────────────────────────────────────────────────────

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


def _reproject_if_needed(layer, target_crs, log=None, label=""):
    """Reprojiziert layer nach target_crs, falls das CRS abweicht."""
    if layer.crs() == target_crs:
        return layer
    if log:
        log(f"  {label}: reprojiziere {layer.crs().authid()} -> "
            f"{target_crs.authid()} ...")
    return processing.run("native:reprojectlayer", {
        'INPUT': layer,
        'TARGET_CRS': target_crs,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _clip_if_needed(layer, clip_mask, log=None, label=""):
    """Klippt layer auf clip_mask, falls ein Untersuchungsgebiet gesetzt ist."""
    if clip_mask is None:
        return layer
    if log:
        log(f"  {label}: klippe auf Untersuchungsgebiet ...")
    return processing.run("native:clip", {
        'INPUT': layer,
        'OVERLAY': clip_mask,
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']


def _prepare_layer(layer, target_crs, clip_mask, log=None, label=""):
    """Reproject + Clip in dieser Reihenfolge (Clip braucht übereinstimmendes CRS)."""
    layer = _reproject_if_needed(layer, target_crs, log, label)
    layer = _clip_if_needed(layer, clip_mask, log, label)
    return layer


def _prepare_clip_mask(study_area_path, target_crs, log=None):
    """Lädt das optionale Untersuchungsgebiet, reprojiziert es und dissolved
    mehrere Polygone zu einer einzigen Clip-Maske. Gibt None zurück, wenn
    kein Untersuchungsgebiet angegeben wurde (= kein Zuschnitt)."""
    if not study_area_path:
        return None
    log_ = log or (lambda m: None)
    log_("Untersuchungsgebiet: lade ...")
    layer = QgsVectorLayer(study_area_path, "study_area", "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {study_area_path}")
    layer = _reproject_if_needed(layer, target_crs, log, "Untersuchungsgebiet")
    if layer.featureCount() > 1:
        log_("Untersuchungsgebiet: dissolve (mehrere Polygone) ...")
        layer = processing.run("native:dissolve", {
            'INPUT': layer,
            'FIELD': [],
            'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
        })['OUTPUT']
    return layer


def _write_gpkg(input_layers, output_path, geometry_type,
                 force_singlepart, keep_fields, log=None, task=None):
    """
    Liest mehrere Eingabe-Layer (Pfad oder QgsVectorLayer) und schreibt sie
    als ein GeoPackage.

    :param geometry_type: QgsWkbTypes-Konstante für den Ziel-Layer
    :param force_singlepart: Multipart-Geometrien werden beim Schreiben in
        ihre Einzelteile zerlegt (für RN/AUX per input-data.md gefordert;
        für HU nicht gesetzt, da für Polygone nicht vorgeschrieben)
    :param keep_fields: übernimmt die Feldstruktur des ersten Eingabe-Layers
        und kopiert sie je Feature (nötig für HU, damit
        fkt/gfkzshh/funktion erhalten bleibt). Setzt voraus, dass alle
        input_layers dasselbe Feldschema haben — bei HU ist das immer
        genau ein Layer.

    Kein Processing-Algorithmus – vollständig threadsicher.
    """
    first_input = input_layers[0]
    first = first_input if isinstance(first_input, QgsVectorLayer) \
        else QgsVectorLayer(first_input, "tmp", "ogr")
    if not first.isValid():
        raise ValueError(f"Layer ungültig: {first_input}")
    crs = first.crs()
    fields = first.fields() if keep_fields else QgsFields()
    if not isinstance(first_input, QgsVectorLayer):
        del first

    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = "GPKG"
    options.fileEncoding = "UTF-8"

    writer = QgsVectorFileWriter.create(
        output_path, fields, geometry_type,
        crs, QgsCoordinateTransformContext(), options)

    for inp in input_layers:
        if task and task.isCanceled():
            raise Exception("Verarbeitung abgebrochen.")
        if isinstance(inp, QgsVectorLayer):
            layer = inp
            name = layer.name()
        else:
            name = os.path.basename(inp)
            layer = QgsVectorLayer(inp, "tmp", "ogr")
        if log:
            log(f"  Schreibe {name} ...")
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

def _process_hu(hu_path, target_crs, clip_mask, target_dir, log=None, task=None):
    log_ = log or (lambda m: None)
    log_("HU: lade Gebäudedatei ...")
    layer = QgsVectorLayer(hu_path, "hu", "ogr")
    if not layer.isValid():
        raise ValueError(f"Layer ungültig: {hu_path}")

    field_names = {f.name().lower() for f in layer.fields()}
    if not field_names & set(HU_FUNCTION_FIELDS):
        log_(f"WARNUNG: HU enthält keines der Felder {HU_FUNCTION_FIELDS} "
             f"- die Funktionscode-Filterung in IBTool wird nicht "
             f"funktionieren.")

    layer = _prepare_layer(layer, target_crs, clip_mask, log, "HU")

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
    ver01_l = _prepare_layer(ver01_l, target_crs, clip_mask, log, "ver01_l")
    ver02_l = _prepare_layer(
        _load_shp(source_dir, "ver02_l"), target_crs, clip_mask, log, "ver02_l")

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
    ver03_l = _prepare_layer(
        _load_shp(source_dir, "ver03_l"), target_crs, clip_mask, log, "ver03_l")
    aux_inputs.append(ver03_l)

    log_("AUX: veg02_f dissolve ...")
    veg02_f = _prepare_layer(
        _load_shp(source_dir, "veg02_f"), target_crs, clip_mask, log, "veg02_f")
    p_veg02_dis = processing.run("native:dissolve", {
        'INPUT': veg02_f, 'FIELD': [], 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg02_f Polygone zu Linien ...")
    p_veg02_lines = processing.run("native:polygonstolines", {
        'INPUT': p_veg02_dis, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_veg02_lines)

    log_("AUX: veg03_f Filter 43005/43006 ...")
    veg03_f = _prepare_layer(
        _load_shp(source_dir, "veg03_f"), target_crs, clip_mask, log, "veg03_f")
    p_veg03_filt = processing.run("native:extractbyexpression", {
        'INPUT': veg03_f,
        'EXPRESSION': 'to_int("OBJART") IN (43005, 43006)',
        'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg03_f dissolve ...")
    p_veg03_dis = processing.run("native:dissolve", {
        'INPUT': p_veg03_filt, 'FIELD': [], 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    log_("AUX: veg03_f Polygone zu Linien ...")
    p_veg03_lines = processing.run("native:polygonstolines", {
        'INPUT': p_veg03_dis, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_veg03_lines)

    log_("AUX: gew01_f Polygone zu Linien ...")
    gew01_f = _prepare_layer(
        _load_shp(source_dir, "gew01_f"), target_crs, clip_mask, log, "gew01_f")
    p_gew01f_lines = processing.run("native:polygonstolines", {
        'INPUT': gew01_f, 'OUTPUT': QgsProcessing.TEMPORARY_OUTPUT,
    })['OUTPUT']
    aux_inputs.append(p_gew01f_lines)

    log_("AUX: füge gew01_l hinzu ...")
    gew01_l = _prepare_layer(
        _load_shp(source_dir, "gew01_l"), target_crs, clip_mask, log, "gew01_l")
    aux_inputs.append(gew01_l)

    log_("AUX: merge + singlepart -> AUX.gpkg ...")
    _write_gpkg(
        aux_inputs, os.path.join(target_dir, "AUX.gpkg"),
        QgsWkbTypes.LineString, force_singlepart=True, keep_fields=False,
        log=log, task=task)
    log_("AUX.gpkg fertig.")


# ── Einstiegspunkt ───────────────────────────────────────────────────────

def process_atkis(source_dir, hu_path, target_dir, study_area_path=None,
                   feedback=None, task=None):
    """
    :param source_dir: Ordner mit den ATKIS SHP-Dateien (ver01_l, ver02_l,
        ver03_l, veg02_f, veg03_f, gew01_f, gew01_l) — flach, ohne
        Unterordner-Suche
    :param hu_path: Pfad zur separat bereitgestellten Gebäudedatei (SHP/GPKG)
    :param target_dir: Ausgabeordner für HU.gpkg, RN.gpkg und AUX.gpkg
    :param study_area_path: optionaler Pfad zu einem Untersuchungsgebiet
        (SHP/GPKG); wenn gesetzt, werden alle Rohlayer darauf geklippt,
        sonst wird der volle Umfang der Rohdaten verarbeitet
    :param feedback: optionale Callback-Funktion für Statusmeldungen
    :param task: optionaler QgsTask – wird auf Abbruch geprüft
    """

    def log(msg):
        if feedback:
            feedback(msg)

    def check_cancel():
        if task and task.isCanceled():
            raise Exception("Verarbeitung abgebrochen.")

    check_cancel()
    log("Projekt-CRS: ermittle aus ver01_l ...")
    ver01_l_raw = _load_shp(source_dir, "ver01_l")
    target_crs = ver01_l_raw.crs()
    log(f"Projekt-CRS: {target_crs.authid()}")

    check_cancel()
    clip_mask = _prepare_clip_mask(study_area_path, target_crs, log)

    check_cancel()
    _process_hu(hu_path, target_crs, clip_mask, target_dir, log, task)

    check_cancel()
    _process_rn(source_dir, target_crs, clip_mask, target_dir, log, task,
                ver01_l=ver01_l_raw)

    check_cancel()
    _process_aux(source_dir, target_crs, clip_mask, target_dir, log, task)
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile processor.py`
Expected: no output, exit code 0. (This only checks syntax — `qgis`/`processing` imports cannot be resolved outside QGIS, so this does not catch runtime errors. Task 5 covers real runtime verification.)

---

### Task 2: Extend `data_wizard_dialog_base.ui` with HU and study-area fields

**Files:**
- Modify (full rewrite): `data_wizard_dialog_base.ui`

- [ ] **Step 1: Write the new file**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<ui version="4.0">
 <class>Data_WizardDialogBase</class>
 <widget class="QDialog" name="Data_WizardDialogBase">
  <property name="geometry">
   <rect>
    <x>0</x>
    <y>0</y>
    <width>560</width>
    <height>220</height>
   </rect>
  </property>
  <property name="windowTitle">
   <string>IB-Tool Data Wizard</string>
  </property>
  <layout class="QVBoxLayout" name="verticalLayout">
   <item>
    <layout class="QGridLayout" name="gridLayout">
     <property name="verticalSpacing">
      <number>8</number>
     </property>
     <item row="0" column="0">
      <widget class="QLabel" name="label_source">
       <property name="text">
        <string>Quellordner:</string>
       </property>
      </widget>
     </item>
     <item row="0" column="1">
      <widget class="QLineEdit" name="lineEdit_source">
       <property name="placeholderText">
        <string>Ordner mit ATKIS SHP-Dateien ...</string>
       </property>
      </widget>
     </item>
     <item row="0" column="2">
      <widget class="QPushButton" name="btn_source">
       <property name="text">
        <string>...</string>
       </property>
       <property name="maximumWidth">
        <number>30</number>
       </property>
      </widget>
     </item>
     <item row="1" column="0">
      <widget class="QLabel" name="label_hu">
       <property name="text">
        <string>Gebäudedatei:</string>
       </property>
      </widget>
     </item>
     <item row="1" column="1">
      <widget class="QLineEdit" name="lineEdit_hu">
       <property name="placeholderText">
        <string>Gebäudegrundrisse (SHP/GPKG) ...</string>
       </property>
      </widget>
     </item>
     <item row="1" column="2">
      <widget class="QPushButton" name="btn_hu">
       <property name="text">
        <string>...</string>
       </property>
       <property name="maximumWidth">
        <number>30</number>
       </property>
      </widget>
     </item>
     <item row="2" column="0">
      <widget class="QLabel" name="label_studyarea">
       <property name="text">
        <string>Untersuchungsgebiet (optional):</string>
       </property>
      </widget>
     </item>
     <item row="2" column="1">
      <widget class="QLineEdit" name="lineEdit_studyarea">
       <property name="placeholderText">
        <string>Polygon zum Zuschneiden, leer = kein Zuschnitt ...</string>
       </property>
      </widget>
     </item>
     <item row="2" column="2">
      <widget class="QPushButton" name="btn_studyarea">
       <property name="text">
        <string>...</string>
       </property>
       <property name="maximumWidth">
        <number>30</number>
       </property>
      </widget>
     </item>
     <item row="3" column="0">
      <widget class="QLabel" name="label_target">
       <property name="text">
        <string>Zielordner:</string>
       </property>
      </widget>
     </item>
     <item row="3" column="1">
      <widget class="QLineEdit" name="lineEdit_target">
       <property name="placeholderText">
        <string>Ausgabeordner für HU.gpkg / RN.gpkg / AUX.gpkg ...</string>
       </property>
      </widget>
     </item>
     <item row="3" column="2">
      <widget class="QPushButton" name="btn_target">
       <property name="text">
        <string>...</string>
       </property>
       <property name="maximumWidth">
        <number>30</number>
       </property>
      </widget>
     </item>
    </layout>
   </item>
   <item>
    <widget class="QDialogButtonBox" name="button_box">
     <property name="orientation">
      <enum>Qt::Horizontal</enum>
     </property>
     <property name="standardButtons">
      <set>QDialogButtonBox::Cancel|QDialogButtonBox::Ok</set>
     </property>
    </widget>
   </item>
  </layout>
 </widget>
 <resources/>
 <connections>
  <connection>
   <sender>button_box</sender>
   <signal>accepted()</signal>
   <receiver>Data_WizardDialogBase</receiver>
   <slot>accept()</slot>
   <hints>
    <hint type="source_label">
     <x>248</x>
     <y>120</y>
    </hint>
    <hint type="destination_label">
     <x>157</x>
     <y>130</y>
    </hint>
   </hints>
  </connection>
  <connection>
   <sender>button_box</sender>
   <signal>rejected()</signal>
   <receiver>Data_WizardDialogBase</receiver>
   <slot>reject()</slot>
   <hints>
    <hint type="source_label">
     <x>316</x>
     <y>120</y>
    </hint>
    <hint type="destination_label">
     <x>286</x>
     <y>130</y>
    </hint>
   </hints>
  </connection>
 </connections>
</ui>
```

- [ ] **Step 2: XML well-formedness check**

Run: `python3 -c "import xml.dom.minidom as m; m.parse('data_wizard_dialog_base.ui'); print('OK')"`
Expected: `OK`

---

### Task 3: Extend `data_wizard_dialog.py` with the new fields' handlers

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


class Data_WizardDialog(QtWidgets.QDialog, FORM_CLASS):
    def __init__(self, parent=None):
        super(Data_WizardDialog, self).__init__(parent)
        self.setupUi(self)
        self.btn_source.clicked.connect(self._browse_source)
        self.btn_hu.clicked.connect(self._browse_hu)
        self.btn_studyarea.clicked.connect(self._browse_studyarea)
        self.btn_target.clicked.connect(self._browse_target)

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

    def get_source_dir(self):
        return self.lineEdit_source.text().strip()

    def get_hu_file(self):
        return self.lineEdit_hu.text().strip()

    def get_study_area_file(self):
        return self.lineEdit_studyarea.text().strip()

    def get_target_dir(self):
        return self.lineEdit_target.text().strip()
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile data_wizard_dialog.py`
Expected: no output, exit code 0.

---

### Task 4: Wire the new fields through `data_wizard.py`

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

    def __init__(self, source_dir, hu_path, target_dir, study_area_path, iface):
        super().__init__("ATKIS Verarbeitung", QgsTask.CanCancel)
        self.source_dir = source_dir
        self.hu_path = hu_path
        self.target_dir = target_dir
        self.study_area_path = study_area_path
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

        source_dir = self.dlg.get_source_dir()
        hu_path = self.dlg.get_hu_file()
        study_area_path = self.dlg.get_study_area_file()
        target_dir = self.dlg.get_target_dir()

        if not source_dir or not hu_path or not target_dir:
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                "Bitte Quellordner, Gebäudedatei und Zielordner angeben.",
                level=Qgis.Warning, duration=5)
            return

        task = _AtkisTask(source_dir, hu_path, target_dir,
                           study_area_path or None, self.iface)
        QgsApplication.taskManager().addTask(task)

        self.iface.messageBar().pushMessage(
            "Data Wizard",
            "Verarbeitung läuft im Hintergrund – siehe Task-Manager und Log-Meldungen.",
            level=Qgis.Info, duration=5)
```

- [ ] **Step 2: Syntax check**

Run: `python3 -m py_compile data_wizard.py`
Expected: no output, exit code 0.

---

### Task 5: Manual end-to-end verification in QGIS

QGIS itself is not available in this shell (`import qgis` fails — no `QGIS_PREFIX_PATH`/module). This task must be run by the user in their real QGIS Desktop install, where the plugin is already deployed
(`C:\Users\Oliver\AppData\Roaming\QGIS\QGIS3\profiles\default\python\plugins\data_wizard`).

**Files:**
- None (manual QGIS session)

- [ ] **Step 1: Reload the plugin**

In QGIS: Plugin Reloader (or close/reopen QGIS) so the edited `.py`/`.ui` files are picked up.

- [ ] **Step 2: Run without a study area**

Open the plugin, fill in a source folder containing `ver01_l.shp`,
`ver02_l.shp`, `ver03_l.shp`, `veg02_f.shp`, `veg03_f.shp`, `gew01_f.shp`,
`gew01_l.shp`, choose a building-footprint file (ideally in a *different*
CRS than the ATKIS data, to exercise the reprojection path), leave
"Untersuchungsgebiet" empty, choose a target folder, click OK.

Expected: success message names `HU.gpkg`, `RN.gpkg`, `AUX.gpkg`; all
three files exist in the target folder; opening them in QGIS shows
HU = polygons with the original attribute table intact (including
whichever of `fkt`/`gfkzshh`/`funktion` the source had), RN/AUX = lines
covering the full extent of the raw data (no clipping applied).

- [ ] **Step 3: Check RN/AUX have no multipart geometries**

In QGIS, open the RN.gpkg and AUX.gpkg attribute tables, add a temporary
field with the expression `num_geometries($geometry)`. Expected: `1` for
every feature (confirms singlepart).

- [ ] **Step 4: Run with a study area**

Repeat Step 2, this time pointing "Untersuchungsgebiet" at a small
polygon file that covers only part of the raw data's extent.

Expected: `HU.gpkg`/`RN.gpkg`/`AUX.gpkg` only contain features intersecting
the study area, visibly clipped to its boundary when compared against
the unclipped run from Step 2.

- [ ] **Step 5: Run the produced files through IBTool's Check button**

Load the produced `HU.gpkg`, `RN.gpkg`, `AUX.gpkg` (plus an existing Part
layer and Filter file) into IBTool and click **Check** (see
`docs/quickstart.md` → Step 3 — Validation in the `ibtool` project).

Expected: no errors specific to HU/RN/Aux (geometry type, required field,
multipart, minimum feature count) — any error here means a bug in this
plan's implementation, not a data problem, since HU/RN/Aux structure is
fully controlled by `processor.py`.

---

## Self-Review Notes

- **Spec coverage:** conditional clip (Task 1: `clip_mask=None` skips
  `native:clip`), CRS auto-reprojection (Task 1: `_reproject_if_needed`),
  Aux composition kept as-is including `gew01_l` (Task 1: `_process_aux`),
  separate HU file picker (Task 2/3), HU field-presence warning without
  hard validation (Task 1: `_process_hu`), fixed non-recursive raw file
  lookup (Task 1: `_load_shp`), fixed output names (Task 1: `_process_hu`/
  `_process_rn`/`_process_aux`) — all covered.
- **Placeholder scan:** none (`TBD`/`TODO`/"handle appropriately" not
  present in any step).
- **Type consistency:** `process_atkis(source_dir, hu_path, target_dir,
  study_area_path=None, feedback=None, task=None)` signature in Task 1
  matches the call in Task 4's `_AtkisTask.run()`; `get_hu_file()` /
  `get_study_area_file()` defined in Task 3 match their use in Task 4's
  `run()`.
