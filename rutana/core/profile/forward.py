"""B 法前向模型（T3.2 新增代码）：单相计算谱。

compute_phase_profile 返回**任意单位的 phase-only 曲线**：
- 不做任何归一化（标度留给线性层 S_p）
- 不加背景（背景是线性参数）
- 不加噪声（噪声只属于合成/实测数据）

数学: y(2θ) = Σ_hkl |F_hkl|²·LP(θ)·Ω(2θ − 2θ_hkl − zero)，Ω = pseudo-Voigt，
FWHM² 由 Caglioti 公式 U·tan²θ + V·tanθ + W 给出，anode 启用 Kα1/α2 双线。
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

import numpy as np

from rutana.core.profile.cif import CifStructure
from rutana.core.profile.shape import (
    DEFAULT_WAVELENGTH,
    _pv_peak,
    caglioti,
    resolve_wavelengths,
)
from rutana.core.profile.struct import compute_peaks

# FWHM 下限保护：防止 Caglioti 退化导致除零
MIN_W = 1e-4


@dataclass(frozen=True)
class ProfileParams:
    """B 法非线性峰形参数集。

    zero : 零点偏移 (度)，直接加在峰位上
    U,V,W: Caglioti FWHM² = U·tan²θ + V·tanθ + W
    eta  : pseudo-Voigt Lorentz 占比
    anode: 阳极靶 (启用 Kα1/α2 双线)；None = 单色光
    ka_ratio: Iα2/Iα1
    po_r : 每相 March–Dollase 择优取向 {phase_name: (h,k,l,r)}，None = 无
    wavelength: 基准波长 (Å)，仅 anode=None 时使用
    """

    zero: float = 0.0
    U: float = 0.0
    V: float = 0.0
    W: float = 0.02
    eta: float = 0.5
    anode: str | None = "Cu"
    ka_ratio: float = 0.5
    po_r: dict | None = None
    wavelength: float = DEFAULT_WAVELENGTH


def _window_slice(grid: np.ndarray, pos: float, half: float) -> tuple[int, int]:
    """峰 ±half 度窗口对应的网格下标区间 [i0, i1)（含边界修正）。"""
    i0 = int(np.searchsorted(grid, pos - half, side="left"))
    i1 = int(np.searchsorted(grid, pos + half, side="right"))
    return max(i0, 0), min(i1, grid.size)


# 衍射峰枚举缓存：peaks 只依赖 (结构, 波长, 窗口, po)，与 zero/U/V/W/eta 无关。
# 精修中每次残差评估都会调 forward，缓存让 LM 每代只做峰形叠加（T4.8 性能）。
_PEAKS_CACHE: dict[tuple, tuple] = {}
_PEAKS_CACHE_MAX = 256


def _phase_peaks(struct: CifStructure, prm: ProfileParams,
                 tmin: float, tmax: float):
    """计算该相的衍射峰列表 ([(pos, |F|²·LP·PO·wgt, d)], skipped)，带缓存。"""
    po = None
    if prm.po_r:
        po = prm.po_r.get(struct.name)
    key = (id(struct), struct.name, struct.cell, len(struct.atoms),
           prm.anode, prm.ka_ratio, prm.wavelength, float(tmin), float(tmax),
           tuple(po) if po is not None else None)
    hit = _PEAKS_CACHE.get(key)
    if hit is None:
        comps = resolve_wavelengths(prm.wavelength, prm.anode, prm.ka_ratio)
        peaks, skipped = compute_peaks(struct, prm.wavelength, tmin, tmax,
                                       po=po, wavelengths=comps)
        hit = (peaks, skipped)
        if len(_PEAKS_CACHE) >= _PEAKS_CACHE_MAX:
            _PEAKS_CACHE.clear()
        _PEAKS_CACHE[key] = hit
    return hit


def _add_peak_windowed(prof: np.ndarray, grid: np.ndarray,
                       pos: float, height: float, fwhm: float, eta: float) -> None:
    """把单个峰只累加到 ±(8·FWHM + 0.05°) 窗口内（T4.8 性能路径）。

    pseudo-Voigt 在 8 个 FWHM 之外幅值 < 2e-5（Lorentz 尾巴），对 Rwp 的影响
    远低于计数噪声，与全网格计算逐点偏差 RMS < 1e-6·max。
    """
    half = 8.0 * fwhm + 0.05
    i0, i1 = _window_slice(grid, pos, half)
    if i1 <= i0:
        return
    prof[i0:i1] += height * _pv_peak(grid[i0:i1], pos, fwhm, eta)


def compute_phase_profile_naive(struct: CifStructure, grid: np.ndarray,
                                prm: ProfileParams,
                                tmin: float = 5.0, tmax: float = 90.0) -> np.ndarray:
    """全网格参考实现（慢，供 T4.8 一致性测试对照）。"""
    peaks, _skipped = _phase_peaks(struct, prm, tmin, tmax)
    fwhm_func = caglioti(prm.U, prm.V, max(prm.W, MIN_W))
    prof = np.zeros_like(grid, dtype=np.float64)
    for pos, height, _d in peaks:
        if height <= 0:
            continue
        fwhm = max(fwhm_func(pos), MIN_W)
        prof += height * _pv_peak(grid, pos + prm.zero, fwhm, prm.eta)
    return prof


def compute_phase_profile(struct: CifStructure, grid: np.ndarray,
                          prm: ProfileParams,
                          tmin: float = 5.0, tmax: float = 90.0) -> np.ndarray:
    """计算单相计算谱（窗口化，无归一化/无背景/无噪声）。

    struct  : CifStructure（全晶胞原子）
    grid    : 2θ 网格 (度, 升序)
    prm     : 峰形参数
    tmin,tmax: 衍射峰枚举窗口（度）
    返回 float64 数组，与 grid 等长，全非负、最大值 > 0（晶胞合法时）。
    """
    grid = np.asarray(grid, dtype=np.float64)
    peaks, _skipped = _phase_peaks(struct, prm, tmin, tmax)
    fwhm_func = caglioti(prm.U, prm.V, max(prm.W, MIN_W))
    prof = np.zeros_like(grid, dtype=np.float64)
    for pos, height, _d in peaks:
        if height <= 0:
            continue
        fwhm = max(fwhm_func(pos), MIN_W)
        _add_peak_windowed(prof, grid, pos + prm.zero, height, fwhm, prm.eta)
    return prof


def strongest_peak_position(struct: CifStructure, prm: ProfileParams,
                            tmin: float = 5.0, tmax: float = 90.0) -> float:
    """最强衍射峰的 2θ 位置（不含 zero），供 QA 与测试。"""
    peaks, _skipped = _phase_peaks(struct, prm, tmin, tmax)
    if not peaks:
        raise ValueError(f"{struct.name}: 窗口内无衍射峰")
    return max(peaks, key=lambda t: t[1])[0]


def phase_profile_at(prms: dict[str, ProfileParams], structs: list[CifStructure],
                     grid: np.ndarray, tmin: float = 5.0,
                     tmax: float = 90.0) -> np.ndarray:
    """各相 profile 矩阵，shape (n_phase, N)，按 structs 顺序堆叠。"""
    rows = [compute_phase_profile(s, grid, prms[s.name], tmin, tmax)
            for s in structs]
    return np.vstack(rows)
