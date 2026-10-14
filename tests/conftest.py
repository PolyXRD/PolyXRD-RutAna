"""pytest 共享 fixture 与路径常量。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rutana.core.dtypes import Pattern

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(__file__).parent / "data"
PY = r"D:/Project/XRD/python310/python.exe"

RANDOM_SEED = 20260701


@pytest.fixture()
def linear_pattern() -> Pattern:
    """严格升序的简单直线谱，供契约级冒烟测试。"""
    tt = np.arange(10.0, 40.0, 0.02)
    ii = 100.0 + 2.0 * tt
    return Pattern(two_theta=tt, intensity=ii, meta={"source": "fixture"})
