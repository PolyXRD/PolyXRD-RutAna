"""可选 Savitzky-Golay 平滑（T2.7 / v1.0.0 实证结论）。

铁律：默认 enabled=False；平滑参数必须写入工程存档 JSON，
且标定与样品两侧必须使用同一参数（对称使用），否则破坏 K 值口径。

v1.0.0 实证（岛津 TiO2 数据集，净峰面积口径，6 标样标定 + 8/18/36% 预测）：
    关闭平滑 : K=1.2345  截距 −0.0706  R²=0.99861  最差相对误差 1.21%
    SG(5,2)  : K=1.2330  截距 −0.0855  R²=0.99787  最差相对误差 2.76%
    SG(9,2)  : K=1.2322  截距 −0.0763  R²=0.99809  最差相对误差 3.27%
真实数据上平滑**不改善**反而略劣（SG 卷积会削平峰顶、把峰尾强度重新分配，
而净峰面积本来就已对泊松噪声做了多通道平均）。合成无噪谱上平滑无影响。
→ 维持默认 enabled=False；仅在极弱峰（SNR<10）时可显式开启，且必须与
  标定同参（写入工程存档）。
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
from scipy.signal import savgol_filter


@dataclass(frozen=True)
class SmoothConfig:
    """SG 平滑配置。enabled=False 时所有调用方必须直通原始数据。"""

    enabled: bool = False
    window: int = 5
    polyorder: int = 2


def savitzky_golay(y: np.ndarray, cfg: SmoothConfig) -> np.ndarray:
    """按 cfg 对 y 做 SG 平滑；enabled=False 时原样返回（副本）。

    窗口自动取奇数并夹到 [polyorder+2, n(奇)] 内；无法平滑时原样返回。
    """
    arr = np.asarray(y, dtype=np.float64)
    if not cfg.enabled:
        return arr.copy()
    n = arr.size
    w = cfg.window if cfg.window % 2 == 1 else cfg.window + 1
    w = min(w, n if n % 2 == 1 else n - 1)
    if w <= cfg.polyorder + 1 or w < 5:
        return arr.copy()  # 窗口不足以产生有意义的平滑（如 3 点 2 阶=恒等）
    return savgol_filter(arr, window_length=int(w), polyorder=cfg.polyorder)
