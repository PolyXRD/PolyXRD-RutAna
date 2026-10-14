"""T2.3 A 法 K 值标定测试。"""

from __future__ import annotations

import pytest

from rutana.core.method_a import CalibPoint, calibrate_k


def test_exact_linear_forced_zero() -> None:
    """严格线性 y=1.234x（5 点）：K_forced0 == 1.234±1e-6，r2>0.9999。"""
    pts = [CalibPoint(x, 1.234 * x) for x in (0.2, 0.5, 1.0, 2.0, 4.0)]
    r = calibrate_k(pts)
    assert r.K_forced0 == pytest.approx(1.234, abs=1e-6)
    assert r.K == pytest.approx(1.234, abs=1e-6)
    assert r.r2 > 0.9999
    assert r.n_points == 5


def test_two_points_raises() -> None:
    """少于 3 个标定点必须抛 ValueError（标准硬性要求）。"""
    with pytest.raises(ValueError):
        calibrate_k([CalibPoint(1.0, 1.0), CalibPoint(2.0, 2.0)])


def test_ols_with_intercept() -> None:
    """force_zero=False 时采用带截距 OLS；intercept/r2 总是回填。"""
    pts = [CalibPoint(x, 1.234 * x + 0.5) for x in (0.2, 0.5, 1.0, 2.0, 4.0)]
    r_free = calibrate_k(pts, force_zero=False)
    assert r_free.K == pytest.approx(1.234, abs=1e-6)
    assert r_free.intercept == pytest.approx(0.5, abs=1e-6)
    r_forced = calibrate_k(pts, force_zero=True)
    assert r_forced.intercept == pytest.approx(0.5, abs=1e-6)
    # 有截距时过原点解会被抬高
    assert r_forced.K_forced0 > 1.234


def test_noisy_data_r2_below_one() -> None:
    """含噪数据 r2 < 1 但仍返回结果。"""
    pts = [CalibPoint(1.0, 1.0), CalibPoint(2.0, 2.05),
           CalibPoint(4.0, 3.90), CalibPoint(0.5, 0.52)]
    r = calibrate_k(pts)
    assert 0.9 < r.r2 < 1.0


def test_zero_x_raises() -> None:
    """ma_over_mr 全为零时无法标定，抛 ValueError。"""
    with pytest.raises(ValueError):
        calibrate_k([CalibPoint(0.0, 1.0), CalibPoint(0.0, 2.0),
                     CalibPoint(0.0, 3.0)])
