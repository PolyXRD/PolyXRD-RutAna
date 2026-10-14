"""B 法精修 · 非线性层（T4.4，核心：变量投影 separable NLS）。

技术决策 D3：scale 与背景系数是线性参数，每次迭代内用 lstsq 解析求解；
LM 只迭代非线性参数 (zero, U, V, W[, eta])，待优化参数从 ~15 降到 ~5。

residual_fn(x):
  x -> 重建 ProfileParams -> compute_phase_profile 各相 -> solve_linear
  解析出 scale+背景 -> 返回加权残差 (y_obs − y_calc)/σ。
history 记录每次残差评估的 Rwp（含被拒绝的试探，画收敛曲线用）。
"""
from __future__ import annotations

import numpy as np
from dataclasses import dataclass, field

from rutana.core.dtypes import Pattern
from rutana.core.profile.cif import CifStructure
from rutana.core.profile.forward import (
    MIN_W,
    ProfileParams,
    compute_phase_profile,
)
from rutana.core.refine.lm import lm_minimize
from rutana.core.refine.linear import solve_linear_detail
from rutana.core.refine.rfactors import RFactors, compute_rfactors

# 参数边界（TASKS T4.4 冻结值）
ZERO_BOUNDS = (-0.5, 0.5)
UVW_BOUNDS = (0.0, 5.0)
ETA_BOUNDS = (0.05, 1.0)


@dataclass(frozen=True)
class RefineConfig:
    """精修开关与数值配置。"""

    refine_zero: bool = True
    refine_uvw: bool = True
    refine_eta: bool = False
    n_bg: int = 3
    max_iter: int = 40
    sigma: np.ndarray | None = None
    tmin: float = 5.0
    tmax: float = 90.0


@dataclass(frozen=True)
class RefineResult:
    """精修结果。phase_dropped 为被线性层剔除（scale=0）的相下标；
    restarted=True 表示角点陷阱检测触发过重启链（至少跑过一个重启起点）。"""

    params: ProfileParams
    scales: np.ndarray
    bg: np.ndarray
    ycalc: np.ndarray
    rf: RFactors
    success: bool
    history: list[float] = field(default_factory=list)
    phase_dropped: list[int] = field(default_factory=list)
    restarted: bool = False


def _pack(prm: ProfileParams, cfg: RefineConfig) -> np.ndarray:
    """按 cfg 开关把 ProfileParams 打包成 LM 向量。"""
    x = []
    if cfg.refine_zero:
        x.append(prm.zero)
    if cfg.refine_uvw:
        x.extend([prm.U, prm.V, prm.W])
    if cfg.refine_eta:
        x.append(prm.eta)
    return np.array(x, dtype=np.float64) if x else np.zeros(0)


def _unpack(x: np.ndarray, base: ProfileParams, cfg: RefineConfig) -> ProfileParams:
    """由 LM 向量重建 ProfileParams（未精修字段取 base 值）。"""
    i = 0
    zero, U, V, W, eta = base.zero, base.U, base.V, base.W, base.eta
    if cfg.refine_zero:
        zero = float(x[i]); i += 1
    if cfg.refine_uvw:
        U, V, W = float(x[i]), float(x[i + 1]), float(x[i + 2]); i += 3
    if cfg.refine_eta:
        eta = float(x[i]); i += 1
    return ProfileParams(zero=zero, U=U, V=V, W=max(W, MIN_W), eta=eta,
                         anode=base.anode, ka_ratio=base.ka_ratio,
                         po_r=base.po_r, wavelength=base.wavelength)


def _bounds(cfg: RefineConfig) -> tuple[np.ndarray, np.ndarray]:
    lo, hi = [], []
    if cfg.refine_zero:
        lo.append(ZERO_BOUNDS[0]); hi.append(ZERO_BOUNDS[1])
    if cfg.refine_uvw:
        # W 下限保护：防止 FWHM 退化成 0 导致除零
        lo.extend([UVW_BOUNDS[0], UVW_BOUNDS[0], MIN_W])
        hi.extend([UVW_BOUNDS[1]] * 3)
    if cfg.refine_eta:
        lo.append(ETA_BOUNDS[0]); hi.append(ETA_BOUNDS[1])
    return np.array(lo), np.array(hi)


def _build_residual(phases: list[CifStructure], pat: Pattern, base: ProfileParams,
                    cfg: RefineConfig, history: list[float]):
    """构造变量投影残差函数（闭包）。x = 启用的非线性参数 (zero?, U,V,W?, eta?)。"""
    tt, yo = pat.two_theta, pat.intensity
    sig = cfg.sigma
    if sig is None:
        sig = np.sqrt(np.maximum(yo, 1.0))

    def residual_fn(x: np.ndarray) -> np.ndarray:
        prm = _unpack(x, base, cfg)
        rows = [compute_phase_profile(s, tt, prm, cfg.tmin, cfg.tmax)
                for s in phases]
        basis = np.vstack(rows) if rows else np.zeros((0, tt.size))
        _coeffs, ycalc, _dropped = solve_linear_detail(
            basis, tt, yo, sig, cfg.n_bg)
        # history 记录每次评估的 Rwp（GSAS-II 口径，背景计入）
        history.append(compute_rfactors(
            yo, ycalc, n_params=x.size + basis.shape[0] + cfg.n_bg).rwp)
        return (yo - ycalc) / sig

    return residual_fn


def _rwp_at(phases: list[CifStructure], pat: Pattern, prm: ProfileParams,
            cfg: RefineConfig) -> float:
    """给定非线性参数下的 Rwp（解一次线性层），用于重启选点。"""
    tt, yo = pat.two_theta, pat.intensity
    sig = cfg.sigma if cfg.sigma is not None else np.sqrt(np.maximum(yo, 1.0))
    rows = [compute_phase_profile(s, tt, prm, cfg.tmin, cfg.tmax) for s in phases]
    _coeffs, ycalc, _dropped = solve_linear_detail(np.vstack(rows), tt, yo,
                                                   sig, cfg.n_bg)
    return compute_rfactors(yo, ycalc, n_params=cfg.n_bg).rwp


def _restart_points(prm_try: ProfileParams) -> list[ProfileParams]:
    """确定性修复起点（LM 角点陷阱的解药）。

    现象: 从 U=V=0 角点出发时 LM 会把 W 吸到下界、用 V 补偿，掉进 Rwp≈14~25%
    的浅极小且 λ 溢出无法逃逸（v75 实测）。任何 U>0 的起点都能收敛到全局盆。
    触发条件: LM 失败 / Rwp>10% / W 触界，用下面的点重试并保留最优。
    """
    pts = []
    for u, w in ((0.02, 0.02), (0.05, 0.01), (0.0, 0.02)):
        pts.append(ProfileParams(zero=prm_try.zero, U=u, V=0.0, W=w,
                                 eta=prm_try.eta, anode=prm_try.anode,
                                 ka_ratio=prm_try.ka_ratio, po_r=prm_try.po_r,
                                 wavelength=prm_try.wavelength))
    return pts


def refine(phases: list[CifStructure], pat: Pattern, prm0: ProfileParams,
           cfg: RefineConfig) -> RefineResult:
    """Rietveld 精修主入口（变量投影 + 自写 LM + 确定性多起点重启）。

    phases: 相列表（CifStructure，name 需与 prm0.po_r 的键对应）
    pat   : 实测/合成谱（Pattern）
    prm0  : 非线性参数初值
    cfg   : 精修开关
    """
    history: list[float] = []
    x0 = _pack(prm0, cfg)
    residual_fn = _build_residual(phases, pat, prm0, cfg, history)

    if x0.size:
        lo, hi = _bounds(cfg)
        lm = lm_minimize(residual_fn, x0, bounds=(lo, hi),
                         max_iter=cfg.max_iter)
        best_x, best_cost, success = lm.x, lm.cost, lm.success
        # ---- 多起点重启（仅 refine_uvw）: 角点陷阱检测 ----
        restarted = False
        if cfg.refine_uvw:
            prm_try = _unpack(best_x, prm0, cfg)
            stuck = ((not success) or prm_try.W <= 2.0 * MIN_W
                     or _rwp_at(phases, pat, prm_try, cfg) > 10.0)
            if stuck:
                restarted = True
                for cand in _restart_points(prm_try):
                    r2 = _build_residual(phases, pat, cand, cfg, history)
                    lm2 = lm_minimize(r2, _pack(cand, cfg), bounds=(lo, hi),
                                      max_iter=cfg.max_iter)
                    if lm2.cost < best_cost:
                        best_x, best_cost = lm2.x, lm2.cost
                        success = lm2.success
    else:
        # 无非线性自由度：只解一次线性层
        best_x, success = x0, True
        restarted = False
        residual_fn(best_x)

    prm = _unpack(best_x, prm0, cfg)
    rows = [compute_phase_profile(s, pat.two_theta, prm, cfg.tmin, cfg.tmax)
            for s in phases]
    basis = np.vstack(rows)
    coeffs, ycalc, dropped = solve_linear_detail(
        basis, pat.two_theta, pat.intensity,
        cfg.sigma if cfg.sigma is not None else np.sqrt(
            np.maximum(pat.intensity, 1.0)), cfg.n_bg)
    n_p = best_x.size + basis.shape[0] + cfg.n_bg
    rf = compute_rfactors(pat.intensity, ycalc, n_params=n_p,
                          sigma=cfg.sigma, include_bg=True)
    return RefineResult(params=prm, scales=coeffs[:basis.shape[0]].copy(),
                        bg=coeffs[basis.shape[0]:].copy(), ycalc=ycalc,
                        rf=rf, success=success, history=history,
                        phase_dropped=dropped, restarted=restarted)
