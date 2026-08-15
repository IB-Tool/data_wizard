"""
Pytest configuration file for Data Wizard tests.

This file sets up the Python path BEFORE any test modules are imported.
CRITICAL: Must be executed before test collection!
"""

import sys
from pathlib import Path

# CRITICAL: Add the plugin's PARENT directory to sys.path IMMEDIATELY.
# This MUST happen before pytest tries to import test modules.
#
# 'data_wizard' is already a valid Python identifier, so — unlike
# IB-Tool-3's 'IB-Tool-3' folder name — no types.ModuleType alias stub is
# needed here. Adding the parent directory is enough for
# 'import data_wizard.processor' to resolve locally exactly like it does in
# the container (PYTHONPATH=/plugins).
plugin_root = Path(__file__).resolve().parent.parent
plugin_parent = plugin_root.parent

if str(plugin_parent) not in sys.path:
    sys.path.insert(0, str(plugin_parent))
    print(f"conftest.py: Added {plugin_parent} to sys.path")

# Verify the plugin package resolves as expected.
assert (plugin_root / "processor.py").exists(), \
    f"processor.py not found in {plugin_root}"
assert (plugin_root / "__init__.py").exists(), \
    f"__init__.py not found in {plugin_root}"


# ---------------------------------------------------------------------------
# Shared layer / geometry factory helpers
#
# These live in test/layer_factories.py (a regular Python module, not a
# pytest plugin). Import them in test files AFTER calling get_qgis_app():
#
#   from .utilities import get_qgis_app
#   QGIS_APP, _CANVAS, _IFACE, _PARENT = get_qgis_app()
#   from .layer_factories import (
#       make_polygon_layer, make_line_layer, make_square_geom, add_feature_to_layer
#   )
#
# Factories must NOT be imported from conftest.py because conftest runs as a
# pytest plugin before QGIS is initialised, and its module context causes
# QGIS' import hook (qgis.utils._import) to trigger a circular-import error.
# ---------------------------------------------------------------------------
