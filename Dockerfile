# 1. Basis-Image mit QGIS 3.40
FROM 3liz/qgis-platform:3.40

# 2. Root-Rechte für Systeminstallationen
USER root

# 3. System-Updates, Headless-X-Server und Test-Abhängigkeiten installieren.
#    Data Wizard hat keine Runtime-Abhängigkeiten außerhalb der QGIS-eigenen
#    Prozessierungs-Algorithmen (siehe requirements-test.txt für Test-Deps).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
    xvfb \
    python3-pytest \
    python3-pytest-cov \
    python3-coverage \
    python3-pip \
 && rm -rf /var/lib/apt/lists/*

# 4. Arbeitsverzeichnis im Container
WORKDIR /plugins

# 5. Plugin-Code kopieren. Der Ordnername ist bereits ein gültiger
#    Python-Bezeichner, daher ist (anders als bei IB-Tool-3) kein
#    virtuelles Package-Alias nötig.
COPY . /plugins/data_wizard/

# 6. Umgebungsvariablen für headless mode und Processing setzen
ENV QT_QPA_PLATFORM=offscreen
ENV QGIS_PREFIX_PATH=/usr
ENV PYTHONPATH=/plugins:/usr/share/qgis/python:/usr/share/qgis/python/plugins
ENV QGIS_PLUGINPATH=/usr/share/qgis/python/plugins

# Arbeitsverzeichnis für die Testausführung
WORKDIR /plugins/data_wizard

# 7. Test-spezifische Python-Abhängigkeiten installieren
RUN if [ -f requirements-test.txt ]; then pip3 install --break-system-packages -r requirements-test.txt; fi

# 8. QGIS Processing Provider explizit initialisieren
RUN python3 -c "\
import sys; \
sys.path.insert(0, '/usr/share/qgis/python'); \
sys.path.insert(0, '/usr/share/qgis/python/plugins'); \
from qgis.core import QgsApplication; \
app = QgsApplication([], False); \
app.setPrefixPath('/usr', True); \
app.initQgis(); \
import processing; \
from processing.core.Processing import Processing; \
Processing.initialize(); \
print('Processing erfolgreich initialisiert'); \
app.exitQgis()"

# 9. Finale Test-Ausführung
CMD ["python3", "-m", "pytest", "test/", "-v", "--tb=short", "--cov", "--cov-report=xml", "--cov-report=html"]
