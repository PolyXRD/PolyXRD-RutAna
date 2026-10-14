"""T2.2 净峰强度测量测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rutana.core.background import BgConfig
from rutana.core.dtypes import Pattern
from rutana.core.peakmeasure import measure_peak

DATA_DIR = Path(__file__).parent / "data"
V50 = DATA_DIR / "virtual/v50.xy"

requires_v50 = pytest.mark.skipif(not V50.exists(),
                                  reason="先运行 tools/gen_virtual.py")


def _gauss_peak(peak_h: float = 3000.0, bg0: float = 500.0,
                center: float = 25.30, fwhm: float = 0.15,
                noise: float = 0.0, seed: int = 20260701) -> Pattern:
    """背景 + 高斯峰（可选噪声）的窄窗合成谱。"""
    tt = 24.5 + 0.02 * np.arange(81)
    sig = fwhm / 2.3548
    rng = np.random.default_rng(seed)
    y = bg0 + peak_h * np.exp(-0.5 * ((tt - center) / sig) ** 2)
    if noise > 0:
        y = y + rng.normal(0.0, noise, tt.size)
    return Pattern(two_theta=tt, intensity=y)


def test_synthetic_gauss_position_height_snr() -> None:
    """合成高斯峰：峰位 ±0.05°、净高 ±5%、SNR>10、FWHM 合理。"""
    m = measure_peak(_gauss_peak(), 25.30)
    assert abs(m.two_theta_at_max - 25.30) <= 0.05
    assert m.net_height == pytest.approx(3000.0, rel=0.05)
    assert m.snr > 10.0
    assert m.ok and m.message == "OK"
    assert m.net_area > 0.0
    assert m.fwhm == pytest.approx(0.15, rel=0.25)
    assert m.background_at_max == pytest.approx(500.0, rel=0.02)


def test_low_snr_flagged() -> None:
    """纯噪声谱（无峰）：ok=False 且给出明确 message。"""
    m = measure_peak(_gauss_peak(peak_h=0.0, noise=5.0), 25.30)
    assert not m.ok
    assert m.message != ""


def test_window_without_points_guard() -> None:
    """搜索窗内无数据点时安全降级（ok=False）。"""
    tt = np.array([10.0, 10.02, 10.04])
    p = Pattern(two_theta=tt, intensity=np.array([1.0, 2.0, 3.0]))
    m = measure_peak(p, 25.30, tol=0.4)
    assert not m.ok
    assert m.net_height == 0.0


@requires_v50
def test_v50_anatase_peak() -> None:
    """v50 虚拟谱：锐钛型 25.30±0.05°，净高>0，SNR>10。"""
    from rutana.core.patterns import load_pattern
    m = measure_peak(load_pattern(V50), 25.30)
    assert abs(m.two_theta_at_max - 25.30) <= 0.05
    assert m.net_height > 0.0
    assert m.snr > 10.0


@requires_v50
def test_v50_rutile_peak() -> None:
    """v50 虚拟谱：金红石 27.44±0.05°，净高>0，SNR>10。"""
    from rutana.core.patterns import load_pattern
    m = measure_peak(load_pattern(V50), 27.44)
    assert abs(m.two_theta_at_max - 27.44) <= 0.05
    assert m.net_height > 0.0
    assert m.snr > 10.0


@requires_v50
def test_v50_wide_scan_same_peaks() -> None:
    """宽扫谱（5-90°）局部窗口背景下同样测得到两峰。"""
    from rutana.core.patterns import load_pattern
    pat = load_pattern(DATA_DIR / "virtual/v50_wide.xy")
    ma = measure_peak(pat, 25.30)
    mr = measure_peak(pat, 27.44)
    assert abs(ma.two_theta_at_max - 25.30) <= 0.05
    assert abs(mr.two_theta_at_max - 27.44) <= 0.05
    # 窄窗与宽扫的净峰高应高度一致（同谱同参数）
    na = measure_peak(load_pattern(V50), 25.30)
    assert ma.net_height == pytest.approx(na.net_height, rel=0.02)


def test_bg_config_passthrough() -> None:
    """显式传入 BgConfig 与默认行为一致。"""
    p = _gauss_peak()
    m1 = measure_peak(p, 25.30)
    m2 = measure_peak(p, 25.30, cfg=BgConfig())
    assert m1.net_height == pytest.approx(m2.net_height)
