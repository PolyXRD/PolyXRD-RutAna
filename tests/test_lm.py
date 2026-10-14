"""T4.3 验收 · LM 优化器测试：Rosenbrock / 线性 LS / max_iter / bounds。"""
from __future__ import annotations

import numpy as np
import pytest
import scipy.linalg

from rutana.core.refine.lm import lm_minimize


def _rosenbrock_residual(x):
    return np.array([10.0 * (x[1] - x[0] ** 2), 1.0 - x[0]])


def test_rosenbrock_converges():
    res = lm_minimize(_rosenbrock_residual, np.array([-1.2, 1.0]),
                      max_iter=60)
    assert res.cost < 1e-6
    assert res.success
    assert res.n_iter <= 60


def test_linear_least_squares_matches_lstsq():
    rng = np.random.default_rng(20260701)
    A = rng.standard_normal((200, 4))
    c_true = np.array([1.5, -2.0, 0.3, 4.0])
    y = A @ c_true
    res = lm_minimize(lambda c: A @ c - y, np.zeros(4))
    c_ref, *_ = scipy.linalg.lstsq(A, y)
    assert np.allclose(res.x, c_ref, rtol=1e-4, atol=1e-6)


def test_max_iter_respected():
    calls = {"n": 0}

    def res_fn(x):
        calls["n"] += 1
        return np.array([x[0] - 3.0])

    res = lm_minimize(res_fn, np.array([0.0]), max_iter=1)
    assert res.n_iter <= 1
    # 只允许 1 次接受迭代对应的有限次残差评估
    assert calls["n"] < 20


def test_bounds_clipped():
    res = lm_minimize(lambda x: np.array([(x[0] - 2.0) ** 2 * 0.0 + (x[0] - 2.0)]),
                      np.array([0.5]), bounds=(np.array([0.0]), np.array([1.0])))
    assert res.x[0] == pytest.approx(1.0, abs=1e-6)
    assert 0.0 <= res.x[0] <= 1.0


def test_lambda_overflow_reports_failure():
    # 常数残差: 无任何下降方向 -> LM 应以 success=False 退出
    res = lm_minimize(lambda x: np.ones(3), np.array([0.0]))
    assert not res.success
    assert np.ones(3).shape == (3,)
