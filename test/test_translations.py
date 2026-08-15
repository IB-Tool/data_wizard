# coding=utf-8
# pylint: skip-file
"""Translation file test."""

__author__ = 'ottmar.hittzfeld@web.de'
__date__ = '2026-08-12'

import os
import unittest
from pathlib import Path


class DataWizardTranslationsTest(unittest.TestCase):
    """Test translations work."""

    def setUp(self):
        """Runs before each test."""
        if 'LANG' in os.environ:
            del os.environ['LANG']

    def tearDown(self):
        """Runs after each test."""
        if 'LANG' in os.environ:
            del os.environ['LANG']

    def test_qgis_translations(self):
        """German translation file (.qm) exists in the i18n directory."""
        plugin_dir = Path(__file__).parent.parent
        qm_path = plugin_dir / 'i18n' / 'Data_Wizard_de.qm'
        self.assertTrue(
            qm_path.exists(),
            f"Translation file not found: {qm_path}"
        )


if __name__ == "__main__":
    suite = unittest.makeSuite(DataWizardTranslationsTest)
    runner = unittest.TextTestRunner(verbosity=2)
    runner.run(suite)
