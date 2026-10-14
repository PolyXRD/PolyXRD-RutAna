"""T2.4 A 法结果计算测试。"""

from __future__ import annotations

import pytest

from rutana.core.method_a import (DEFAULT_ABS_LIMIT, RatioResult,
                                  combine_duplicates, compute_ratio)


def test_wa_fifty_when_ia_equals_ir() -> None:
    """K=1 且 ia=ir -> wa=50.000。"""
    r = compute_ratio(100.0, 100.0, 1.0)
    assert r.wa == pytest.approx(50.0, abs=1e-9)
    assert r.wr == pytest.approx(50.0, abs=1e-9)
    assert r.wa + r.wr == pytest.approx(100.0)


def test_wa_k2() -> None:
    """K=2、ir/ia=1 -> wa=33.333±1e-3。"""
    r = compute_ratio(100.0, 100.0, 2.0)
    assert r.wa == pytest.approx(33.3333, abs=1e-3)
    assert r.wr == pytest.approx(66.6667, abs=1e-3)


def test_zero_ir_gives_pure_anatase() -> None:
    """ir=0（检不出金红石）-> wa=100。"""
    r = compute_ratio(50.0, 0.0, 1.5)
    assert r.wa == pytest.approx(100.0)
    assert r.wr == pytest.approx(0.0)


def test_invalid_inputs_raise() -> None:
    """ia<=0 / ir<0 / K<=0 抛 ValueError。"""
    with pytest.raises(ValueError):
        compute_ratio(0.0, 10.0, 1.0)
    with pytest.raises(ValueError):
        compute_ratio(-1.0, 10.0, 1.0)
    with pytest.raises(ValueError):
        compute_ratio(10.0, -1.0, 1.0)
    with pytest.raises(ValueError):
        compute_ratio(10.0, 10.0, 0.0)


def test_combine_duplicates_within_default_limit() -> None:
    """双平行 95.10/95.20 -> abs_diff=0.10、within_limit=True。"""
    r1 = RatioResult(wa=95.10, wr=4.90, K=1.0, ia=100.0, ir=5.0)
    r2 = RatioResult(wa=95.20, wr=4.80, K=1.0, ia=100.0, ir=5.0)
    d = combine_duplicates(r1, r2)
    assert d["abs_diff"] == pytest.approx(0.10, abs=1e-9)
    assert d["within_limit"] is True
    assert d["limit"] == pytest.approx(DEFAULT_ABS_LIMIT)
    assert d["wa_mean"] == pytest.approx(95.15)


def test_combine_duplicates_custom_limit() -> None:
    """自定义更严的限值时判定翻转为 False。"""
    r1 = RatioResult(wa=95.10, wr=4.90, K=1.0, ia=100.0, ir=5.0)
    r2 = RatioResult(wa=95.20, wr=4.80, K=1.0, ia=100.0, ir=5.0)
    d = combine_duplicates(r1, r2, limit=0.05)
    assert d["within_limit"] is False
    assert d["limit"] == pytest.approx(0.05)
