"""A 法净峰强度测量（T2.2 / T2.7）。

口径（GB/T 30793—2014 A 法）：取分析线最大衍射峰的净峰高作为峰强；
净峰面积作为辅助量输出。本模块默认不做任何平滑（T2.7 起可选，
标定与样品必须同参对称使用）。
"""

from __future__ import annotations

import numpy as np

from rutana.core.background import BgConfig, estimate_background
from rutana.core.dtypes import Pattern, PeakMeasure
from rutana.core.patterns import clip
from rutana.core.smooth import SmoothConfig, savitzky_golay

# GB/T 30793—2014 A 法分析线（Cu Kα）：锐钛型 (101) / 金红石型 (110)
ANATASE_2TH = 25.30
RUTILE_2TH = 27.44

# 背景估计的局部窗口半宽（度）：在峰搜索窗两侧各加 0.4 度留边缘取背景
BG_MARGIN = 0.4
# SNR 合格阈值（标准：0.1% 锐钛型信号 >= 4 倍噪声）
SNR_MIN = 4.0


def _robust_sigma(resid: np.ndarray) -> float:
    """残差的 MAD 稳健 sigma（1.4826 * median|x - med|）。"""
    if resid.size < 3:
        return 0.0
    med = float(np.median(resid))
    return float(1.4826 * np.median(np.abs(resid - med)))


def _half_width_crossing(tt: np.ndarray, resid: np.ndarray,
                         i_max: int, half: float) -> tuple[float | None, float | None]:
    """从峰位向两侧找 resid 降到 half 的线性插值交点，返回 (左, 右)。"""

    def walk(step: int) -> float | None:
        j = i_max
        n = tt.size
        while 0 <= j + step < n and resid[j + step] > half:
            j += step
        k = j + step
        if not (0 <= k < n) or resid[k] > half:
            return None  # 到窗口边界仍未降到半高：FWHM 不可定
        x1, x2 = float(tt[j]), float(tt[k])
        r1, r2 = float(resid[j]), float(resid[k])
        return x1 + (half - r1) * (x2 - x1) / (r2 - r1)

    return walk(-1), walk(1)


def measure_peak(p: Pattern, expected: float, tol: float = 0.4,
                 cfg: BgConfig = BgConfig(),
                 smooth: SmoothConfig = SmoothConfig()) -> PeakMeasure:
    """在 [expected-tol, expected+tol] 内测量单峰，返回 PeakMeasure。

    - 背景在 expected±(tol+BG_MARGIN) 的局部窗口内估计（对宽扫谱同样稳健）；
    - net_area 在峰搜索窗 [expected-tol, expected+tol] 内积分；
    - snr = net_height / MAD(resid)；ok = snr >= 4.0 且净高 > 0。
    """
    lo = max(expected - tol - BG_MARGIN, float(p.two_theta[0]))
    hi = min(expected + tol + BG_MARGIN, float(p.two_theta[-1]))
    if lo >= hi:
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, "局部窗口内无数据点")
    sub = clip(p, lo, hi)
    y = savitzky_golay(sub.intensity, smooth)
    bg = estimate_background(sub, cfg)
    resid = y - bg
    sel = (sub.two_theta >= expected - tol) & (sub.two_theta <= expected + tol)
    if not bool(sel.any()):
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, "搜索窗内无数据点")
    j = int(np.argmax(np.where(sel, y, -np.inf)))
    tt_max = float(sub.two_theta[j])
    net_height = float(y[j] - bg[j])
    step = float(np.median(np.diff(sub.two_theta)))
    net_area = float(np.sum(resid[sel]) * step)
    left, right = _half_width_crossing(sub.two_theta, resid, j,
                                       net_height / 2.0)
    fwhm = (right - left) if (left is not None and right is not None) \
        else float("nan")
    sigma = _robust_sigma(resid)
    snr = net_height / sigma if sigma > 0 else float("inf")
    ok = snr >= SNR_MIN and net_height > 0.0
    if ok:
        msg = "OK"
    elif net_height <= 0.0:
        msg = f"净峰高非正 ({net_height:.3f})"
    else:
        msg = f"SNR {snr:.2f} < {SNR_MIN:.1f}（检出限外）"
    return PeakMeasure(two_theta_at_max=tt_max, net_height=net_height,
                       net_area=net_area, background_at_max=float(bg[j]),
                       fwhm=fwhm, snr=float(snr), ok=bool(ok), message=msg)
