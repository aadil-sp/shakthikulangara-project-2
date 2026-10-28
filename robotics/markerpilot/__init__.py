"""MarkerPilot - overhead-camera ArUco navigation for a differential-drive robot car."""

import os as _os

# The filters here use tiny matrices. A multi-threaded BLAS gains nothing on
# them and fights OpenCV's thread pool: a 3x3 inverse took 160 ms after each
# marker detection on macOS. Must be set before numpy is imported.
for _var in ("OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "MKL_NUM_THREADS", "VECLIB_MAXIMUM_THREADS"):
    _os.environ.setdefault(_var, "1")


__version__ = "2.0.0"
APP_NAME = "MarkerPilot"
