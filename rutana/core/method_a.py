"""A 法（强度比值法）核心：K 标定与结果计算（T2.3 / T2.4）。

公式（GB/T 30793—2014）：
    K   = slope(I_a/I_r  vs  m_a/m_r)，默认过原点最小二乘
    w_a = 1/(1 + K·I_r/I_a) × 100%；w_r = 100 − w_a
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 双平行重复性限（绝对百分点）。
# 待 T0.2（STD_FREEZE.md）以标准原文核对后如有出入另开卡修订。
DEFAULT_ABS_LIMIT = 0.15


@dataclass(frozen=True)
class CalibPoint:
    """一个标准混合标定点：质量比与对应的净强度比。"""

    ma_over_mr: float
    ia_over_ir: float


@dataclass(frozen=True)
class CalibResult:
    """K 标定结果。K 为采用的值；K_forced0/intercept/r2 用于诊断与报警。"""

    K: float
    intercept: float
    r2: float
    n_points: int
    K_forced0: float


def calibrate_k(points: list[CalibPoint], force_zero: bool = True) -> CalibResult:
    """多点标定 K。

    - force_zero=True：过原点最小二乘 K = Σxy/Σx²（标准默认口径）；
    - 无论采用哪种口径，总是额外回填一份带截距 OLS 的 intercept 与 r2
      （r2 < 0.995 时由上层报警）；
    - n_points < 3 抛 ValueError（标准硬性要求，不给例外）。
    """
    if len(points) < 3:
        raise ValueError("K 值标定至少需要 3 个标准混合点")
    x = np.array([pt.ma_over_mr for pt in points], dtype=np.float64)
    y = np.array([pt.ia_over_ir for pt in points], dtype=np.float64)
    denom = float(np.sum(x * x))
    if denom <= 0.0:
        raise ValueError("标定点 ma_over_mr 全为零，无法标定")
    k0 = float(np.sum(x * y) / denom)
    slope, intercept = np.polyfit(x, y, 1)
    yhat = slope * x + intercept
    ss_res = float(np.sum((y - yhat) ** 2))
    ss_tot = float(np.sum((y - float(np.mean(y))) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0
    return CalibResult(K=k0 if force_zero else float(slope),
                       intercept=float(intercept), r2=float(r2),
                       n_points=len(points), K_forced0=k0)


@dataclass(frozen=True)
class RatioResult:
    """单次 A 法测定结果（内部全精度，报告层再四舍五入到两位小数）。"""

    wa: float
    wr: float
    K: float
    ia: float
    ir: float


def compute_ratio(ia: float, ir: float, K: float) -> RatioResult:
    """w_a = 1/(1 + K·I_r/I_a) × 100；w_r = 100 − w_a。

    ia <= 0 或 ir < 0 或 K <= 0 抛 ValueError。
    """
    if ia <= 0:
        raise ValueError("锐钛型净峰强度 ia 必须为正")
    if ir < 0:
        raise ValueError("金红石型净峰强度 ir 不能为负")
    if K <= 0:
        raise ValueError("K 值必须为正")
    wa = 1.0 / (1.0 + K * ir / ia) * 100.0
    return RatioResult(wa=wa, wr=100.0 - wa, K=float(K),
                       ia=float(ia), ir=float(ir))


def combine_duplicates(r1: RatioResult, r2: RatioResult,
                       limit: float = DEFAULT_ABS_LIMIT) -> dict:
    """双平行测定合成：均值、绝对差（百分点）、是否在重复限内。"""
    wa_mean = (r1.wa + r2.wa) / 2.0
    abs_diff = abs(r1.wa - r2.wa)
    return {"wa_mean": wa_mean, "abs_diff": abs_diff,
            "within_limit": bool(abs_diff <= limit), "limit": float(limit)}
