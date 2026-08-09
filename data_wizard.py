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

    def __init__(self, *, source_dir, hu_path, target_dir, study_area_path,
                 hu_function_field, iface, on_finished=None):
        super().__init__("ATKIS Verarbeitung", QgsTask.CanCancel)
        self.source_dir = source_dir
        self.hu_path = hu_path
        self.target_dir = target_dir
        self.study_area_path = study_area_path
        self.hu_function_field = hu_function_field
        self.iface = iface
        self.on_finished = on_finished
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
        """Läuft im Haupt-Thread – sicher für UI-Zugriff.

        Wird garantiert aufgerufen, während dieses Task-Objekt selbst noch
        lebt (Qt ruft es direkt als Abschluss der Task auf) - daher der
        richtige Ort, um den Laufend-Zustand beim Plugin zurückzusetzen,
        statt das (ggf. später vom TaskManager zerstörte) Task-Objekt aus
        einem späteren Plugin-Aufruf heraus erneut abzufragen.
        """
        if self.on_finished:
            self.on_finished()
        if result:
            self.iface.messageBar().pushMessage(
                "Data Wizard",
                f"Fertig – HU.gpkg, RN.gpkg und AUX_L.gpkg in: {self.target_dir}",
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
        # Gleicher Menütitel wie IBTool selbst, damit beide Aktionen im
        # selben Untermenü landen: Erweiterungen -> IB-Tool -> Data Wizard
        self.menu = self.tr(u'&IB-Tool')
        self.first_start = None
        self.task = None
        # Eigener Laufend-Status statt self.task.status() abzufragen: Qt
        # kann das zugrunde liegende C++-Objekt einer abgeschlossenen Task
        # zerstören, auch während self.task (die Python-Referenz) noch
        # existiert - ein späterer Zugriff auf self.task.status() würfe
        # dann "wrapped C/C++ object ... has been deleted".
        self._task_running = False

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
            text=self.tr(u'Data Wizard'),
            callback=self.run,
            parent=self.iface.mainWindow())
        self.first_start = True

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu, action)
            self.iface.removeToolBarIcon(action)

    def _on_task_finished(self):
        """Von _AtkisTask.finished() im Haupt-Thread aufgerufen, sobald die
        Verarbeitung endet (Erfolg, Abbruch oder Fehler)."""
        self._task_running = False

    def run(self):
        if self.first_start:
            self.first_start = False
            self.dlg = Data_WizardDialog()

        self.dlg.show()
        result = self.dlg.exec_()

        if not result:
            return

        if self._task_running:
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

        self.task = _AtkisTask(
            source_dir=source_dir,
            hu_path=hu_path,
            target_dir=target_dir,
            study_area_path=study_area_path or None,
            hu_function_field=hu_function_field,
            iface=self.iface,
            on_finished=self._on_task_finished)
        self._task_running = True
        QgsApplication.taskManager().addTask(self.task)

        self.iface.messageBar().pushMessage(
            "Data Wizard",
            "Verarbeitung läuft im Hintergrund – siehe Task-Manager und Log-Meldungen.",
            level=Qgis.Info, duration=5)
