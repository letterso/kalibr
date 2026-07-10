from __future__ import annotations

import importlib.util
import types
from pathlib import Path

import matplotlib
import numpy as np

matplotlib.use("Agg")

REPO_ROOT = Path(__file__).resolve().parents[1]
ICC_PLOTS = (
    REPO_ROOT
    / "aslam_offline_calibration"
    / "kalibr"
    / "python"
    / "kalibr_imu_camera_calibration"
    / "IccPlots.py"
)


class FakeReprojectionError:
    def __init__(self, x, y):
        self._error = np.array([x, y], dtype=float)

    def error(self):
        return self._error


def import_icc_plots():
    spec = importlib.util.spec_from_file_location("icc_plots_test", ICC_PLOTS)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_reprojection_scatter_attaches_colorbar_to_current_axes():
    module = import_icc_plots()
    camera = types.SimpleNamespace(
        allReprojectionErrors=[
            [FakeReprojectionError(0.1, -0.2)],
            [FakeReprojectionError(-0.3, 0.4)],
        ],
        cornerUncertainty=1.0,
    )
    calibration = types.SimpleNamespace(
        CameraChain=types.SimpleNamespace(camList=[camera])
    )

    module.plotReprojectionScatter(calibration, 0, fno=99, noShow=True)

    figure = module.pl.figure(99)
    assert len(figure.axes) == 2
    module.pl.close(figure)
