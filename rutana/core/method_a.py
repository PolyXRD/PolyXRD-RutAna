"""A 法（强度比值法）核心：K 标定与结果计算（T2.3 / T2.4 / v1.0.0）。

公式（GB/T 30793—2014）：
    K   = slope(I_a/I_r  vs  m_a/m_r)，**默认带截距 OLS 斜率**
    w_a = 1/(1 + K·I_r/I_a) × 100%；w_r = 100 − w_a

v1.0.0 关于 K 口径的实证结论（岛津 TiO2 应用数据集 XRD-019）：
  用岛津公布的 6 组标样峰面积 Ia/Ir 反算，
    带截距 OLS 斜率 = 1.2234（= 岛津公布 K，R²=0.99932）
    强制过原点     = 1.2512（偏离 +2.3%）
  → 默认口径改为带截距 OLS 斜率；force_zero=True 仅作兼容选项保留。
  校准后应检查截距：截距显著不为 0 说明测峰协议（尤其背景窗）有系统偏差，
  此时标准公式 w_a = 1/(1+K·I_r/I_a) 不再严格成立，需要重调协议而不是硬用 K。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

# 双平行重复性限（绝对百分点）。
# 出处：GB/T 30793—2014 正文（经 XRData/TiO2/Application_News_AP_XRD-019.docx
# 原文引用核对）：对锐钛矿含量或金红石含量 ≥95% 的样品，由同一操作者所测得
# 的两个结果，其绝对差值应 ≤0.18%。详见 docs/STD_FREEZE.md。
DEFAULT_ABS_LIMIT = 0.18

# 再现性限（绝对百分点）。
# 出处：GB/T 30793—2014 §9.2「对锐钛型含量或金红石型含量 ≥95% 的样品，
# 不同实验室的操作者得到的两个结果，其绝对差值应 ≤0.22%」。
# 详见 docs/STD_FREEZE.md。
DEFAULT_REPRO_LIMIT = 0.22

# 校准线性度报警阈值（R² 低于此值应报警并复核标定）
R2_WARN = 0.995


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

    @property
    def r2_ok(self) -> bool:
        """R² 是否达到报警阈值（>=0.995）。"""
        return bool(self.r2 >= R2_WARN)

    @property
    def warnings(self) -> list[str]:
        """标定诊断告警列表（空列表表示无需告警）。"""
        out: list[str] = []
        if not self.r2_ok:
            out.append(f"标定线性度不足：R²={self.r2:.5f} < {R2_WARN}")
        # 阈值取 0.10·K：v1.0.0 默认协议在真实数据上截距 ≈ −0.07（≈5.7%·K）
        # 属健康范围；v0.1.0 legacy 协议截距 +0.20（≈15%·K）会被正确报警。
        if self.n_points and abs(self.intercept) > 0.10 * max(abs(self.K), 1e-9):
            out.append(f"校准截距偏大（{self.intercept:+.4f}），"
                       "测峰协议（背景窗/积分窗）可能存在系统偏差")
        return out


def calibrate_k(points: list[CalibPoint], force_zero: bool = False) -> CalibResult:
    """多点标定 K。

    - force_zero=False（v1.0.0 默认）：带截距 OLS 斜率；
    - force_zero=True：过原点最小二乘 K = Σxy/Σx²（v0.1.0 旧口径，兼容保留）；
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


def invert_ratio(ia_over_ir: float, calib: CalibResult,
                 use_intercept: bool = False) -> RatioResult:
    """由实测强度比 Ia/Ir 与标定结果反算 w_a/w_r。

    use_intercept=False（默认，标准口径）：m_a/m_r = (I_a/I_r)/K，
        等价于标准公式 w_a = 1/(1+K·I_r/I_a)；
    use_intercept=True：先扣截距再除 K，即 m_a/m_r = (I_a/I_r − b)/K，
        仅在截距显著不为 0、且确认截距来自可建模的系统项时使用。
    """
    if ia_over_ir <= 0:
        raise ValueError("强度比 Ia/Ir 必须为正")
    if calib.K <= 0:
        raise ValueError("K 值必须为正")
    ratio = (ia_over_ir - calib.intercept) / calib.K if use_intercept \
        else ia_over_ir / calib.K
    if ratio < 0:
        ratio = 0.0
    wa = ratio / (1.0 + ratio) * 100.0
    return RatioResult(wa=wa, wr=100.0 - wa, K=float(calib.K),
                       ia=float(ia_over_ir), ir=1.0)


def combine_duplicates(r1: RatioResult, r2: RatioResult,
                       limit: float = DEFAULT_ABS_LIMIT) -> dict:
    """双平行测定合成：均值、绝对差（百分点）、是否在重复限内。"""
    wa_mean = (r1.wa + r2.wa) / 2.0
    abs_diff = abs(r1.wa - r2.wa)
    return {"wa_mean": wa_mean, "abs_diff": abs_diff,
            "within_limit": bool(abs_diff <= limit), "limit": float(limit)}
