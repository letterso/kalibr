from __future__ import annotations

import importlib.util
import queue
import sys
import types
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[1]
TARGET_EXTRACTOR = (
    REPO_ROOT
    / "aslam_offline_calibration"
    / "kalibr"
    / "python"
    / "kalibr_common"
    / "TargetExtractor.py"
)


class FakeProgress:
    def sample(self, count=1):
        return count


class FakeManager:
    def Queue(self):
        return queue.Queue()


class FakeObservation:
    def clearImage(self):
        pass


class FakeDataset:
    topic = "/image"

    def numImages(self):
        return 1

    def readDataset(self):
        yield "stamp", np.zeros((2, 2), dtype=np.uint8)


class UncopyableDetector:
    def __copy__(self):
        raise RuntimeError("unregistered class - derived class not registered or exported")

    def findTarget(self, stamp, image):
        return True, FakeObservation()


def import_target_extractor(monkeypatch, warnings):
    fake_sm = types.SimpleNamespace(
        Progress2=lambda count: FakeProgress(),
        logWarn=warnings.append,
        logFatal=lambda message: (_ for _ in ()).throw(RuntimeError(message)),
    )
    monkeypatch.setitem(sys.modules, "sm", fake_sm)
    spec = importlib.util.spec_from_file_location("target_extractor_test", TARGET_EXTRACTOR)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module.multiprocessing, "Manager", lambda: FakeManager())
    return module


def test_multithreaded_extraction_falls_back_when_detector_cannot_be_copied(monkeypatch):
    warnings = []
    module = import_target_extractor(monkeypatch, warnings)
    monkeypatch.setattr(module.cv2, "destroyAllWindows", lambda: None)

    observations = module.extractCornersFromDataset(
        FakeDataset(), UncopyableDetector(), multithreading=True, numProcesses=1
    )

    assert len(observations) == 1
    assert warnings == [
        "Detector cannot be copied for multithreaded extraction; falling back to one process: "
        "unregistered class - derived class not registered or exported"
    ]


def test_extraction_ignores_unavailable_opencv_window_cleanup(monkeypatch):
    module = import_target_extractor(monkeypatch, [])

    def unavailable_highgui():
        raise module.cv2.error("HighGUI is unavailable")

    monkeypatch.setattr(module.cv2, "destroyAllWindows", unavailable_highgui)

    observations = module.extractCornersFromDataset(
        FakeDataset(), UncopyableDetector(), multithreading=False
    )

    assert len(observations) == 1
