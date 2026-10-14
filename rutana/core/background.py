"""A 法背景估计（T2.1）。窗口端点稳健线性 / 边缘多项式两种模式。"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from rutana.core.dtypes import Pattern


@dataclass(frozen=True)
class BgConfig:
    """背景估计配置。mode: linear_edges | poly。"""

    mode: str = "linear_edges"
    edge_frac: float = 0.10
    poly_deg: int = 1


def _edge_count(n: int, edge_frac: float) -> int:
    """每侧边缘点数（至少 2 点，至多 n//2）。"""
    k = max(2, int(round(n * edge_frac)))
    return min(k, n // 2)


def estimate_background(p: Pattern, cfg: BgConfig) -> np.ndarray:
    """估计与输入等长的背景曲线。允许出现负值（不裁剪）。

    linear_edges: 两端各 edge_frac 比例点取中位数（抗离群）后连直线。
    poly:         对两端边缘点做 poly_deg 次最小二乘拟合（>=2 阶需 >=4 点）。
    """
    tt = p.two_theta
    ii = p.intensity
    n = tt.size
    k = _edge_count(n, cfg.edge_frac)
    if cfg.mode == "linear_edges":
        xl = float(np.median(tt[:k]))
        xr = float(np.median(tt[-k:]))
        yl = float(np.median(ii[:k]))
        yr = float(np.median(ii[-k:]))
        if xr <= xl:
            return np.full(n, yl, dtype=np.float64)
        slope = (yr - yl) / (xr - xl)
        return yl + slope * (tt - xl)
    if cfg.mode == "poly":
        deg = int(cfg.poly_deg)
        if deg < 1:
            raise ValueError("poly_deg 至少为 1")
        xs = np.concatenate([tt[:k], tt[-k:]])
        ys = np.concatenate([ii[:k], ii[-k:]])
        if deg >= 2 and xs.size < 4:
            raise ValueError(">=2 阶多项式背景至少需要 4 个边缘点")
        coeffs = np.polyfit(xs, ys, deg)
        return np.polyval(coeffs, tt)
    raise ValueError(f"未知背景模式: {cfg.mode}")
