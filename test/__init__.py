# Make sure QGIS_PREFIX_PATH and sys.path (qgis python, qgis python/plugins,
# QGIS's own site-packages) are set up before anything below imports qgis -
# needed when pytest is invoked with a plain system Python instead of the
# QGIS-bundled interpreter (python-qgis.bat already sets this up itself).
from .config import apply_qgis_environment
apply_qgis_environment()

# import qgis libs so that ve set the correct sip api version
import qgis   # pylint: disable=W0611  # NOQA
