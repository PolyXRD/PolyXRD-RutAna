"""A 法净峰强度测量（T2.2 / T2.7 / v1.0.0 真实数据调优）。

口径
----
GB/T 30793—2014 A 法字面写「取分析线最大衍射峰的峰最大值」；但 v1.0.0
用岛津 TiO2 真实数据集（XRD-019）做了实证对比，**默认口径改为净峰面积**：

* 岛津 sheet1（峰面积口径）6 个标样：R²=0.99932，反算 K=1.2234（= 公布值）；
* 岛津 sheet2（峰高口径）6 个标样：R²=0.99110，反算 K=1.0452；
* 更关键的是稳健性：峰高正比于 1/FWHM，标定谱与未知谱的仪器展宽一旦不同就
  系统性漂移。本数据集上用「局部扫描 24–29°」标定、去预测「FullProf 全谱
  20–120°」的 8/18/36% 实测谱时，峰高口径最大相对误差 9.47%，而净峰面积
  口径仅 1.21%（详见 docs/VALIDATION_v1.0.0.md）。

净峰高（net_height）仍完整保留，作为可选项（``quantity="height"``）。

协议（APeakProtocol）
--------------------
测峰参数（峰位、积分窗、背景窗、背景模型、平滑、Kα2、口径）被封装成一个
不可变协议对象，标定与样品两侧必须共用同一协议（工程存档铁律）。

* ``PROTOCOL_LEGACY``：v0.1.0 行为（峰高、25.30/27.44、±0.4°、BG_MARGIN 0.4），
  保留以兼容 tests/golden/method_a_roundtrip.json 黄金基线；
* ``PROTOCOL_V100``  ：v1.0.0 真实数据优化协议（净峰面积、
  Cu Kα 双线复合峰重心 25.34/27.47、锐钛 ±0.25°、金红石 ±1.05°、
  背景边缘 +0.18°、linear_edges edge_frac=0.14、不平滑、不剥离 Kα2）。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np

from rutana.core.background import BgConfig, estimate_background
from rutana.core.dtypes import Pattern, PeakMeasure
from rutana.core.kalpha2 import KAlpha2Config, strip_kalpha2
from rutana.core.patterns import clip
from rutana.core.smooth import SmoothConfig, savitzky_golay

# GB/T 30793—2014 A 法分析线（Cu Kα1 卡片值），v0.1.0 起沿用，禁止改动
# （tests/golden/method_a_roundtrip.json 与 tools/bench.py 依赖此常量）
ANATASE_2TH = 25.30
RUTILE_2TH = 27.44

# v1.0.0：Cu Kα 双线（Kα1+Kα2）复合峰的重心实测位置。
# 岛津数据集实测峰位 25.32~25.36° / 27.44~27.50°（含约 +0.02° 零偏），
# 复合峰重心取 25.34 / 27.47 时校准线性度与预测误差最优
# （对比：用 25.30/27.44 时 worst 2.03%，用 25.34/27.47 时 worst 1.21%）。
ANATASE_2TH_KA = 25.34
RUTILE_2TH_KA = 27.47

# 背景估计的局部窗口半宽（度）：在积分窗两侧各加这么多留边缘取背景
BG_MARGIN = 0.4
# SNR 合格阈值（标准：0.1% 锐钛型信号 >= 4 倍噪声）
SNR_MIN = 4.0

# 峰强口径常量
QUANTITY_AREA = "area"
QUANTITY_HEIGHT = "height"

ProgressCb = Callable[[str, float | None], None]
CancelCb = Callable[[], bool]


@dataclass(frozen=True)
class APeakProtocol:
    """A 法测峰协议：两条分析线测量参数的完整集合（可序列化进工程存档）。

    quantity          : "area" 取净峰面积（默认）/ "height" 取净峰高；
    *_half_win        : 净峰面积积分半窗（度）；净峰高口径下同时用作峰位搜索半窗；
    bg_margin         : 在积分窗两侧额外外扩的背景估计边缘（度）；
    bg / smooth/kalpha2: 背景模型 / SG 平滑 / Kα2 剥离配置。
    """

    name: str = "legacy"
    anatase_2th: float = ANATASE_2TH
    rutile_2th: float = RUTILE_2TH
    anatase_half_win: float = 0.4
    rutile_half_win: float = 0.4
    bg_margin: float = BG_MARGIN
    bg: BgConfig = BgConfig()
    smooth: SmoothConfig = SmoothConfig()
    kalpha2: KAlpha2Config = KAlpha2Config()
    quantity: str = QUANTITY_HEIGHT

    def as_dict(self) -> dict:
        """序列化为可 JSON 化的 dict（写工程存档用）。"""
        return {"name": self.name,
                "anatase_2th": self.anatase_2th,
                "rutile_2th": self.rutile_2th,
                "anatase_half_win": self.anatase_half_win,
                "rutile_half_win": self.rutile_half_win,
                "bg_margin": self.bg_margin,
                "bg": {"mode": self.bg.mode, "edge_frac": self.bg.edge_frac,
                       "poly_deg": self.bg.poly_deg},
                "smooth": {"enabled": self.smooth.enabled,
                           "window": self.smooth.window,
                           "polyorder": self.smooth.polyorder},
                "kalpha2": {"enabled": self.kalpha2.enabled,
                            "ratio": self.kalpha2.ratio,
                            "anode": self.kalpha2.anode,
                            "iters": self.kalpha2.iters},
                "quantity": self.quantity}


# v0.1.0 兼容协议（黄金基线口径）
PROTOCOL_LEGACY = APeakProtocol(name="legacy")

# v1.0.0 真实数据优化协议（推荐用于实际仪器数据）
PROTOCOL_V100 = APeakProtocol(
    name="v1.0.0",
    anatase_2th=ANATASE_2TH_KA,
    rutile_2th=RUTILE_2TH_KA,
    anatase_half_win=0.25,
    rutile_half_win=1.05,
    bg_margin=0.18,
    bg=BgConfig(mode="linear_edges", edge_frac=0.14),
    smooth=SmoothConfig(),
    kalpha2=KAlpha2Config(),
    quantity=QUANTITY_AREA,
)


def get_protocol(name: str) -> APeakProtocol:
    """按名字取协议：v1 / v1.0.0 -> PROTOCOL_V100；legacy / v0.1.0 -> 兼容协议。"""
    key = (name or "").strip().lower()
    if key in ("v1", "v1.0.0", "v100", "real"):
        return PROTOCOL_V100
    if key in ("legacy", "v0.1.0", "v010", "golden"):
        return PROTOCOL_LEGACY
    raise ValueError(f"未知测峰协议: {name}（可选: legacy | v1）")


def peak_value(m: PeakMeasure, quantity: str = QUANTITY_AREA) -> float:
    """按口径从 PeakMeasure 取出峰强（面积或净高）。"""
    if quantity == QUANTITY_AREA:
        return float(m.net_area)
    if quantity == QUANTITY_HEIGHT:
        return float(m.net_height)
    raise ValueError(f"未知峰强口径: {quantity}")


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
        if r2 == r1:
            # 残差在此段恒定（如完全平坦谱）：交点不可定，取段末点兜底
            return x2
        return x1 + (half - r1) * (x2 - x1) / (r2 - r1)

    return walk(-1), walk(1)


def _emit(cb: ProgressCb | None, text: str, pct: float | None) -> None:
    """安全推送一条进度（回调为空则忽略）。"""
    if cb is None:
        return
    cb(text, pct)


def measure_peak(p: Pattern, expected: float, tol: float = 0.4,
                 cfg: BgConfig = BgConfig(),
                 smooth: SmoothConfig = SmoothConfig(),
                 bg_margin: float = BG_MARGIN,
                 kalpha2: KAlpha2Config = KAlpha2Config(),
                 progress_cb: ProgressCb | None = None,
                 cancel_cb: CancelCb | None = None) -> PeakMeasure:
    """在 [expected-tol, expected+tol] 内测量单峰，返回 PeakMeasure。

    - 背景在 expected±(tol+bg_margin) 的局部窗口内估计（对宽扫谱同样稳健）；
    - net_area 在积分窗 [expected-tol, expected+tol] 内积分；
    - snr = net_height / MAD(resid)；ok = snr >= 4.0 且净高 > 0。

    新增（v1.0.0，均为可选且带默认值，不传时行为与 v0.1.0 完全一致）：
    bg_margin / kalpha2 / progress_cb / cancel_cb。
    """
    _emit(progress_cb, "正在扣除背底", 0.05)
    if callable(cancel_cb) and cancel_cb():
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, "已取消")
    lo = max(expected - tol - bg_margin, float(p.two_theta[0]))
    hi = min(expected + tol + bg_margin, float(p.two_theta[-1]))
    if lo >= hi:
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, "局部窗口内无数据点")
    pat = strip_kalpha2(p, kalpha2)
    sub = clip(pat, lo, hi)
    _emit(progress_cb, "正在平滑与拟合背景", 0.35)
    y = savitzky_golay(sub.intensity, smooth)
    bg = estimate_background(sub, cfg)
    resid = y - bg
    sel = (sub.two_theta >= expected - tol) & (sub.two_theta <= expected + tol)
    if not bool(sel.any()):
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, "搜索窗内无数据点")
    _emit(progress_cb, "正在定位峰位与积分", 0.65)
    try:
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
    except Exception as exc:  # noqa: BLE001 —— 峰形退化等算术异常转可读提示，绝不裸抛
        return PeakMeasure(expected, 0.0, 0.0, 0.0, float("nan"), 0.0,
                           False, f"峰形退化，无法测量（{exc}）")
    ok = snr >= SNR_MIN and net_height > 0.0
    if ok:
        msg = "OK"
    elif net_height <= 0.0:
        msg = f"净峰高非正 ({net_height:.3f})"
    else:
        msg = f"SNR {snr:.2f} < {SNR_MIN:.1f}（检出限外）"
    _emit(progress_cb, "测峰完成", 1.0)
    return PeakMeasure(two_theta_at_max=tt_max, net_height=net_height,
                       net_area=net_area, background_at_max=float(bg[j]),
                       fwhm=fwhm, snr=float(snr), ok=bool(ok), message=msg)


def measure_pair(pat: Pattern, protocol: APeakProtocol = PROTOCOL_LEGACY,
                 progress_cb: ProgressCb | None = None,
                 cancel_cb: CancelCb | None = None
                 ) -> tuple[float, float, PeakMeasure, PeakMeasure]:
    """按给定协议测量一条谱上的锐钛型/金红石型峰强，返回 (ia, ir, ma, mr)。

    默认沿用 legacy 协议以兼容 v0.1.0 与黄金基线；真实仪器数据请用
    ``protocol=PROTOCOL_V100``（或 CLI 的 ``--protocol v1``）。
    """
    _emit(progress_cb, "正在测量锐钛型峰", 0.1)
    ma = measure_peak(pat, protocol.anatase_2th, tol=protocol.anatase_half_win,
                      cfg=protocol.bg, smooth=protocol.smooth,
                      bg_margin=protocol.bg_margin, kalpha2=protocol.kalpha2,
                      progress_cb=progress_cb, cancel_cb=cancel_cb)
    if callable(cancel_cb) and cancel_cb():
        raise RuntimeError("已取消")
    _emit(progress_cb, "正在测量金红石型峰", 0.6)
    mr = measure_peak(pat, protocol.rutile_2th, tol=protocol.rutile_half_win,
                      cfg=protocol.bg, smooth=protocol.smooth,
                      bg_margin=protocol.bg_margin, kalpha2=protocol.kalpha2,
                      progress_cb=progress_cb, cancel_cb=cancel_cb)
    _emit(progress_cb, "正在计算比率", 0.9)
    return (peak_value(ma, protocol.quantity),
            peak_value(mr, protocol.quantity), ma, mr)
