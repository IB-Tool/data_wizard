"""Central test configuration for Data Wizard.

Single source of truth for two things:

1. The local QGIS bootstrap (``apply_qgis_environment``), applied from
   ``test/__init__.py`` before anything imports ``qgis``.
2. The location of the committed test data under ``Testdaten/`` and the
   ``requires_atkis_testdaten`` skip marker derived from it.

Everything path-related is driven by ``test_config.ini`` so the layout is
declared in exactly one place. Test modules must not re-derive these paths —
import them from here instead.
"""

import configparser
import os
import sys
from pathlib import Path

import pytest

CONFIG_FILE = Path(__file__).parent / 'test_config.ini'

parser = configparser.ConfigParser()
# Explicit UTF-8: the [testdata] paths contain umlauts ("ALKIS Gebäude"), and
# configparser would otherwise fall back to the platform encoding (cp1252 on
# Windows), which makes the file non-portable.
parser.read(CONFIG_FILE, encoding='utf-8')

QGIS_PREFIX_PATH = parser.get('qgis', 'prefix_path', fallback=r'C:\\Program Files\\QGIS 3.40.0')

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def apply_qgis_environment():
    """Apply QGIS environment variables and sys.path entries."""
    os.environ.setdefault('QGIS_PREFIX_PATH', QGIS_PREFIX_PATH)
    os.environ.setdefault('PYTHONPATH', str(Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python'))
    paths = [
        Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python',
        Path(QGIS_PREFIX_PATH) / 'apps' / 'qgis' / 'python' / 'plugins',
        Path(QGIS_PREFIX_PATH) / 'apps' / 'Python312' / 'Lib' / 'site-packages',
    ]
    for p in paths:
        p_str = str(p)
        if os.path.exists(p_str) and p_str not in sys.path:
            sys.path.insert(0, p_str)


# ---------------------------------------------------------------------------
# Committed test data (Testdaten/)
# ---------------------------------------------------------------------------

#: Root of the committed test data.
TESTDATEN_DIR = PROJECT_ROOT / parser.get('testdata', 'dir', fallback='Testdaten')

#: Folder holding the flat ATKIS Basis-DLM shapefiles. processor._load_shp
#: does not search recursively, so this must be the folder that directly
#: contains ver01_l.shp etc. — it is what gets passed as source_dir.
ATKIS_DIR = TESTDATEN_DIR / parser.get(
    'testdata', 'atkis_subdir', fallback='ATKIS Basis DLM dataset')

#: Building footprint file passed as hu_path.
HU_SHP = TESTDATEN_DIR / parser.get(
    'testdata', 'hu_file', fallback='ALKIS Gebäude/GebauedeBauwerk.shp')

#: The seven ATKIS source layers processor.process_atkis reads. Keep in sync
#: with processor._process_rn / _process_aux.
ATKIS_LAYERS = ('ver01_l', 'ver02_l', 'ver03_l', 'veg02_f', 'veg03_f',
                'gew01_f', 'gew01_l')

#: True when the full extract is present and the end-to-end tests can run.
ATKIS_DATA_AVAILABLE = (
    ATKIS_DIR.is_dir()
    and all((ATKIS_DIR / f'{name}.shp').exists() for name in ATKIS_LAYERS)
    and HU_SHP.exists()
)

TESTDATA_SKIP_REASON = (
    f"Test data incomplete - expected the seven ATKIS layers in {ATKIS_DIR} "
    f"and the building footprints at {HU_SHP}. See docs/test-strategy.md."
)

#: Shared skip marker for every test that needs the real ATKIS/ALKIS extract.
requires_atkis_testdaten = pytest.mark.skipif(
    not ATKIS_DATA_AVAILABLE, reason=TESTDATA_SKIP_REASON)


def missing_atkis_layers():
    """Return the ATKIS layer names absent from ATKIS_DIR (empty when complete)."""
    return [name for name in ATKIS_LAYERS
            if not (ATKIS_DIR / f'{name}.shp').exists()]
