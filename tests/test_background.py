"""T2.1 背景估计测试。"""

from __future__ import annotations

import numpy as np
import pytest

from rutana.core.background import BgConfig, estimate_background
from rutana.core.dtypes import Pattern


def _pattern(bg0: float = 1000.0, slope: float = 0.0,
             peak_h: float = 5000.0, peak_c: float = 30.0,
             fwhm: float = 0.30, n: int = 400, step: float = 0.05,
             t0: float = 20.0) -> Pattern:
    """直线背景 + 单高斯峰的合成谱。"""
    tt = t0 + step * np.arange(n)
    bg = bg0 + slope * (tt - t0)
    sig = fwhm / 2.3548
    y = bg + peak_h * np.exp(-0.5 * ((tt - peak_c) / sig) ** 2)
    return Pattern(two_theta=tt, intensity=y)


def test_constant_bg_linear_edges() -> None:
    """常数背景 1000 复现为 1000±1。"""
    bg = estimate_background(_pattern(peak_h=0.0), BgConfig())
    assert float(np.max(np.abs(bg - 1000.0))) <= 1.0


def test_linear_bg_with_peak_error_below_1pct() -> None:
    """直线背景 + 单峰：峰位处背景误差 < 1% of 背景真值。"""
    p = _pattern(slope=8.0, peak_c=30.0)
    bg = estimate_background(p, BgConfig())
    i = int(np.argmin(np.abs(p.two_theta - 30.0)))
    truth = 1000.0 + 8.0 * (30.0 - 20.0)
    assert abs(bg[i] - truth) < 0.01 * truth


def test_poly_mode_recovers_quadratic() -> None:
    """poly 模式（2 阶）对二次背景的恢复足够接近。"""
    tt = 20.0 + 0.05 * np.arange(400)
    truth = 800.0 + 5.0 * tt + 0.02 * tt ** 2
    p = Pattern(two_theta=tt, intensity=truth.copy())
    bg = estimate_background(p, BgConfig(mode="poly", poly_deg=2))
    assert bg.shape == truth.shape
    assert float(np.max(np.abs(bg - truth))) < 0.01 * float(truth.max())


def test_output_length_matches_input() -> None:
    """返回结果必须与输入等长。"""
    p = _pattern()
    for cfg in (BgConfig(), BgConfig(mode="poly", poly_deg=3)):
        assert estimate_background(p, cfg).size == p.intensity.size


def test_unknown_mode_raises() -> None:
    """未知模式抛 ValueError。"""
    with pytest.raises(ValueError):
        estimate_background(_pattern(), BgConfig(mode="spline"))


def test_poly_mode_min_edge_points() -> None:
    """poly 模式 deg>=2 恰好 4 个边缘点（每侧最少 2 点）时可用。"""
    tiny = Pattern(two_theta=np.array([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]),
                   intensity=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0]))
    bg = estimate_background(tiny, BgConfig(mode="poly", poly_deg=2))
    assert bg.shape == tiny.intensity.shape
    assert bool(np.allclose(bg, 1.0))
