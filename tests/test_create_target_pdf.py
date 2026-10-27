from __future__ import annotations

import runpy
import subprocess
import sys
from pathlib import Path

import pytest

TARGET_SCRIPT = (
    Path(__file__).resolve().parents[1]
    / "aslam_offline_calibration"
    / "kalibr"
    / "python"
    / "kalibr_create_target_pdf"
)


@pytest.mark.parametrize(
    "grid_args",
    [
        ["--type", "apriltag", "--nx", "5", "--ny", "7", "--tsize", "0.025", "--tspace", "0.3"],
        ["--type", "checkerboard", "--nx", "6", "--ny", "6", "--csx", "0.05", "--csy", "0.1"],
    ],
)
def test_generate_pdf_and_eps_without_tex(tmp_path, monkeypatch, grid_args):
    def unexpected_subprocess(*args, **kwargs):
        pytest.fail("Target generation must not invoke TeX or other external commands")

    monkeypatch.setattr(subprocess, "Popen", unexpected_subprocess)
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("MPLCONFIGDIR", str(tmp_path / "matplotlib"))
    monkeypatch.setattr(sys, "argv", [str(TARGET_SCRIPT), "--eps", *grid_args])
    monkeypatch.chdir(tmp_path)

    runpy.run_path(str(TARGET_SCRIPT), run_name="__main__")

    pdf = (tmp_path / "target.pdf").read_bytes()
    assert pdf.startswith(b"%PDF-")
    assert pdf.rstrip().endswith(b"%%EOF")
    assert b"/BaseFont /Times-Roman" in pdf

    eps = (tmp_path / "target.eps").read_text()
    assert eps.startswith("%!PS-Adobe-3.0 EPSF-3.0")
    assert "%%BoundingBox:" in eps
    assert "/Times-Roman" in eps
