"""T1.3 谱图绘制工具测试。"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rutana.core.dtypes import Pattern
from rutana.core.plot import plot_fit, plot_overlay

MIN_BYTES = 5000  # 完成判据：PNG 存在且 > 5 KB


def _pat(t0: float = 20.0, t1: float = 30.0) -> Pattern:
    """构造简单测试谱。"""
    tt = np.arange(t0, t1, 0.1)
    return Pattern(two_theta=tt,
                   intensity=100.0 + 5.0 * tt + 50.0 *
                   np.exp(-0.5 * ((tt - 25.3) / 0.1) ** 2))


def test_plot_overlay_creates_png(tmp_path: Path) -> None:
    """plot_overlay 输出非空 PNG（>5 KB）。"""
    out = tmp_path / "overlay.png"
    plot_overlay([("样品A", _pat()), ("样品B", _pat(21.0, 31.0))],
                 "叠加测试", out)
    assert out.exists()
    assert out.stat().st_size > MIN_BYTES


def test_plot_fit_creates_png(tmp_path: Path) -> None:
    """plot_fit 输出非空 PNG（>5 KB，上 2 下 1 布局）。"""
    out = tmp_path / "fit.png"
    obs = _pat()
    calc = _pat()
    diff = Pattern(two_theta=obs.two_theta,
                   intensity=obs.intensity - calc.intensity)
    plot_fit(obs, calc, diff, out)
    assert out.exists()
    assert out.stat().st_size > MIN_BYTES
