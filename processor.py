# -*- coding: utf-8 -*-
"""
ATKIS Basis-DLM Verarbeitungslogik

Erzeugt aus ATKIS-Rohdaten und einer separat gewählten Gebäudedatei:
  HU.gpkg  – Gebäudegrundrisse (unverändert übernommen, alle Felder erhalten;
                          fehlt fkt/gfkzshh/funktion, wird eine erkannte
                          Funktionscode-Spalte als 'funktion' kopiert)
  RN.gpkg  – Straßennetz (ver01_l + ver02_l, gemerged, Singlepart)
  AUX_L.gpkg – Hilfslinien (ver03_l, veg02_f, veg03_f 43005/43006,
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
    QgsProcessing, QgsFeatureRequest, NULL,
)
from qgis.PyQt.QtCore import QVariant

HU_FUNCTION_FIELDS = ("fkt", "gfkzshh", "funktion")

# ATKIS-Objektartcode für Gebäude (AX_Gebaeude), siehe
# basis-dlm-aaa_ebenen_inhalt.csv. Funktionscode-Werte in HU haben die Form
# "31001_xxxx" (z.B. "31001_1000") — nur der 31001-Präfix ist plausibel für
# ein Gebäude-Funktionscode-Feld, ein generisches "5 Ziffern_4 Ziffern"
# Muster wäre zu unspezifisch.
FUNCTION_CODE_PATTERN = re.compile(r'^31001_\d{4}$')


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
            if value not in (None, NULL) and value != '':
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
    if idx_src == -1:
        raise ValueError(f"Feld '{source_field_name}' nicht gefunden.")
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
        layer = layer.materialize(QgsFeatureRequest())
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

    log_("AUX: merge + singlepart -> AUX_L.gpkg ...")
    _write_gpkg(
        aux_inputs, os.path.join(target_dir, "AUX_L.gpkg"),
        QgsWkbTypes.LineString, force_singlepart=True, keep_fields=False,
        log=log, task=task)
    log_("AUX_L.gpkg fertig.")


# ── Einstiegspunkt ───────────────────────────────────────────────────────

def process_atkis(source_dir, hu_path, target_dir, study_area_path=None,
                  hu_function_field=None, feedback=None, task=None):
    """
    :param source_dir: Ordner mit den ATKIS SHP-Dateien (ver01_l, ver02_l,
        ver03_l, veg02_f, veg03_f, gew01_f, gew01_l) — flach, ohne
        Unterordner-Suche
    :param hu_path: Pfad zur separat bereitgestellten Gebäudedatei (SHP/GPKG)
    :param target_dir: Ausgabeordner für HU.gpkg, RN.gpkg und AUX_L.gpkg
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
