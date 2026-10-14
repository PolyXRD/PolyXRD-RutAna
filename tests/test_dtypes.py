"""T0.3 核心数据类型契约测试。"""

from __future__ import annotations

import numpy as np
import pytest

from rutana.core.dtypes import Pattern, PeakMeasure


def test_pattern_normal_construction() -> None:
    """正常构造：字段可读、类型为 float64、step 属性可用。"""
    tt = np.array([10.0, 10.02, 10.04])
    ii = np.array([1.0, 2.0, 3.0])
    p = Pattern(two_theta=tt, intensity=ii, meta={"path": "x.xy"})
    assert p.step == pytest.approx(0.02)
    assert p.two_theta.dtype == np.float64
    assert p.intensity.dtype == np.float64
    assert p.meta["path"] == "x.xy"


def test_pattern_length_mismatch_raises() -> None:
    """长度不等必须抛 ValueError。"""
    with pytest.raises(ValueError):
        Pattern(two_theta=np.arange(3.0), intensity=np.arange(4.0))


def test_pattern_not_ascending_raises() -> None:
    """非严格升序（含重复点）必须抛 ValueError。"""
    with pytest.raises(ValueError):
        Pattern(two_theta=np.array([1.0, 1.0, 2.0]),
                intensity=np.array([1.0, 2.0, 3.0]))


def test_peak_measure_fields() -> None:
    """PeakMeasure 字段齐全可赋值。"""
    m = PeakMeasure(two_theta_at_max=25.30, net_height=100.0, net_area=15.0,
                    background_at_max=50.0, fwhm=0.15, snr=20.0,
                    ok=True, message="OK")
    assert m.ok and m.message == "OK"
    assert m.fwhm == pytest.approx(0.15)
