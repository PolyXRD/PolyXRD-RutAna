"""T2.7 可选平滑测试。"""

from __future__ import annotations

import numpy as np
import pytest

from rutana.core.smooth import SmoothConfig, savitzky_golay

SEED = 20260701


def test_disabled_returns_identical_copy() -> None:
    """默认关闭：数值逐位一致且返回副本（不共享内存）。"""
    y = np.arange(10.0)
    out = savitzky_golay(y, SmoothConfig())
    assert np.array_equal(out, y)
    assert out is not y


def test_enabled_reduces_noise() -> None:
    """开启后噪声标准差明显下降（SG(9,2) 降噪系数约 0.51），均值保持。"""
    rng = np.random.default_rng(SEED)
    y = 1000.0 + rng.normal(0.0, 10.0, 200)
    s = savitzky_golay(y, SmoothConfig(enabled=True, window=9))
    assert float(np.std(s - 1000.0)) < 0.6 * float(np.std(y - 1000.0))
    # SG 系数对称 -> 均值保持（对噪声这一随机变量的具体实现不敏感）
    assert abs(float(np.mean(s)) - float(np.mean(y))) < 0.1


def test_even_window_autofixed() -> None:
    """偶数窗口自动取奇，输出形状不变。"""
    y = np.sin(np.linspace(0.0, 6.0, 50))
    s = savitzky_golay(y, SmoothConfig(enabled=True, window=6))
    assert s.shape == y.shape


def test_window_larger_than_data() -> None:
    """窗口大于数据长度时安全降级（返回原值）。"""
    y = np.arange(4.0)
    s = savitzky_golay(y, SmoothConfig(enabled=True, window=9))
    assert np.array_equal(s, y)


def test_enabled_changes_signal() -> None:
    """开启平滑确实改变数据（与关闭状态不同）。"""
    rng = np.random.default_rng(SEED)
    y = 100.0 + rng.normal(0.0, 5.0, 100)
    off = savitzky_golay(y, SmoothConfig(enabled=False))
    on = savitzky_golay(y, SmoothConfig(enabled=True))
    assert not np.allclose(on, off)


def test_smoothed_peak_position_stable() -> None:
    """平滑后峰位漂移 < 0.01°（验收判据 ②）。"""
    tt = np.arange(24.5, 26.1, 0.02)
    rng = np.random.default_rng(SEED)
    y = 500.0 + 3000.0 * np.exp(-0.5 * ((tt - 25.30) / 0.0637) ** 2)
    y = y + rng.normal(0.0, 20.0, tt.size)
    pos_before = float(tt[int(np.argmax(y))])
    ys = savitzky_golay(y, SmoothConfig(enabled=True))
    pos_after = float(tt[int(np.argmax(ys))])
    assert abs(pos_after - pos_before) < 0.01
