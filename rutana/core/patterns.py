"""谱图读取与基础操作 —— A/B 法共用的数据入口（T1.1）。

实现说明：参考 PolyXRD-SynthPattern 的 load_measured() 思路自行实现，
不 import 兄弟仓库（项目铁律）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rutana.core.dtypes import Pattern

# 本卡支持的两列文本格式；.ras/.raw/.uxd 等二进制格式留待后续任务卡
SUPPORTED_EXTS = {".xy", ".txt", ".dat", ".csv"}


def _parse_two_column(text: str) -> tuple[np.ndarray, np.ndarray]:
    """解析两列文本：跳过 #/ / 开头注释行，容忍首个非数据行（表头）。"""
    xs: list[float] = []
    ys: list[float] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 2:
            if not xs:  # 尚未读到数据 -> 视为表头行，容忍
                continue
            raise ValueError(f"第 {lineno} 行列数不足（需要两列）: {raw!r}")
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            if not xs:  # 尚未读到数据 -> 视为表头行，容忍
                continue
            raise ValueError(f"第 {lineno} 行无法解析为数字: {raw!r}") from None
        xs.append(x)
        ys.append(y)
    if len(xs) < 2:
        raise ValueError("有效数据点不足 2 个，无法构成谱图")
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def load_pattern(path: str | Path) -> Pattern:
    """读取两列谱图文本（.xy/.txt/.dat/.csv），返回 Pattern。

    未知扩展名抛 NotImplementedError；行解析失败抛 ValueError。
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise NotImplementedError(f"暂不支持的格式: {ext}")
    tt, ii = _parse_two_column(p.read_text(encoding="utf-8", errors="replace"))
    meta = {"path": str(p), "source_format": ext.lstrip("."),
            "wavelength_anode": None}
    return Pattern(two_theta=tt, intensity=ii, meta=meta)


def clip(p: Pattern, tmin: float, tmax: float) -> Pattern:
    """按 2θ 区间 [tmin, tmax] 布尔掩码裁剪（不含端外插值）。"""
    if tmin > tmax:
        raise ValueError(f"裁剪区间非法: tmin={tmin} > tmax={tmax}")
    mask = (p.two_theta >= tmin) & (p.two_theta <= tmax)
    if not bool(mask.any()):
        raise ValueError(f"裁剪区间 [{tmin}, {tmax}] 内无数据点")
    return Pattern(two_theta=p.two_theta[mask].copy(),
                   intensity=p.intensity[mask].copy(),
                   meta=dict(p.meta))


def estimate_step(p: Pattern) -> float:
    """中位数步长（度）。"""
    return p.step
