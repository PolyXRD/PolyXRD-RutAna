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
    resolve_wavelengths,
)
from rutana.core.profile.struct import compute_peaks

# FWHM 下限保护：防止 Caglioti 退化导致除零
MIN_W = 1e-4


def caglioti_2theta(U: float, V: float, W: float):
    """Caglioti 公式（正确的 2θ 口径）：FWHM² = U·tan²θ + V·tanθ + W，θ = 2θ/2。

    输入 pos 为 2θ（度）。注：家族 vendor 的 shape.caglioti 实现为 tan(2θ)
    （SynthPattern 原始引擎即如此调用，属家族级历史语义，其文档串写 tanθ 但
    代码求值于全角）；Rietveld 物理要求 tanθ，且 tan(2θ) 在 2θ>90° 后变负、
    FWHM 曲线完全失真——v1.0.0 真实数据实证这是 U,V→0 角点收敛的直接原因
    （精修器被迫用常数 W + 大 bfactor 补偿高角，Rwp 10.97% → 修后 9.5%）。
    为不破坏家族 vendor 冻结约定，在 RutAna 侧按正确口径包装。
    """
    def f(pos: float) -> float:
        t = math.tan(math.radians(pos) / 2.0)
        return math.sqrt(max(U * t * t + V * t + W, 1e-6))
    return f


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
    asym : 峰不对称度（低角尾展宽，s = asym/tanθ，v1.0.0 实测数据需要）
    bfactor: 经验高角衰减 exp(−B/2d²)（补偿 Debye-Waller/吸收类高角强度
             系统性偏差；v1.0.0 真实数据实测 B≈0.2，合成数据默认 0 = 关闭）
    integrated: True = 峰高按积分强度归一化（h/(FWHM·(1.06447+0.50633η))），
             这是 Rietveld 标量 S 的标准口径（Hill–Howard 定量依赖它）；
             v0.1.0 旧口径（峰高直乘）仅用于对照，False 时不归一化。
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
    asym: float = 0.0
    bfactor: float = 0.0
    integrated: bool = True


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


def _asym_split(pos_shifted: float, fwhm: float, asym: float) -> tuple[float, float]:
    """不对称峰形的左右 FWHM：s = asym/tanθ，左尾 (1+s)·FWHM、右尾 (1−s)·FWHM。

    低角衍射的轴向发散不对称随 tanθ 增大而减弱（v1.0.0 实测数据实证）。
    """
    if asym == 0.0:
        return fwhm, fwhm
    th = math.radians(max(pos_shifted, 1e-3) / 2.0)
    s = max(-0.85, min(0.85, asym / max(math.tan(th), 1e-3)))
    return fwhm * (1.0 + s), fwhm * (1.0 - s)


def _add_peak_windowed(prof: np.ndarray, grid: np.ndarray,
                       pos: float, height: float, fwhm: float, eta: float,
                       asym: float = 0.0, bfactor: float = 0.0,
                       d: float | None = None,
                       integrated: bool = True) -> None:
    """把单个峰只累加到 ±(8·FWHM + 0.05°) 窗口内（T4.8 性能路径）。

    pseudo-Voigt 在 8 个 FWHM 之外幅值 < 2e-5（Lorentz 尾巴），对 Rwp 的影响
    远低于计数噪声，与全网格计算逐点偏差 RMS < 1e-6·max。
    integrated=True 时 height 先除以 pV 峰面积换算系数，转为积分强度口径。
    """
    if bfactor > 0.0 and d is not None and d > 0:
        height = height * math.exp(min(50.0, -bfactor / (2.0 * d * d)))
    if integrated:
        height = height / max(fwhm * (1.06447 + 0.50633 * eta), 1e-12)
    fl, fr = _asym_split(pos, fwhm, asym)
    half = 8.0 * max(fl, fr) + 0.05
    i0, i1 = _window_slice(grid, pos, half)
    if i1 <= i0:
        return
    x = grid[i0:i1] - pos
    if fl == fr:
        prof[i0:i1] += height * _pv_peak(grid[i0:i1], pos, fwhm, eta)
    else:
        # 左右不同 FWHM 的分段 pseudo-Voigt（在峰位处拼接，峰位值连续）
        left = height * _pv_peak(x / fl * fwhm + pos, pos, fwhm, eta)
        right = height * _pv_peak(x / fr * fwhm + pos, pos, fwhm, eta)
        prof[i0:i1] += np.where(x < 0, left, right)


def compute_phase_profile_naive(struct: CifStructure, grid: np.ndarray,
                                prm: ProfileParams,
                                tmin: float = 5.0, tmax: float = 90.0) -> np.ndarray:
    """全网格参考实现（慢，供 T4.8 一致性测试对照）。"""
    peaks, _skipped = _phase_peaks(struct, prm, tmin, tmax)
    fwhm_func = caglioti_2theta(prm.U, prm.V, max(prm.W, MIN_W))
    prof = np.zeros_like(grid, dtype=np.float64)
    for pos, height, d in peaks:
        if height <= 0:
            continue
        fwhm = max(fwhm_func(pos), MIN_W)
        _add_peak_windowed(prof, grid, pos + prm.zero, height, fwhm, prm.eta,
                           prm.asym, prm.bfactor, d, prm.integrated)
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
    fwhm_func = caglioti_2theta(prm.U, prm.V, max(prm.W, MIN_W))
    prof = np.zeros_like(grid, dtype=np.float64)
    for pos, height, d in peaks:
        if height <= 0:
            continue
        fwhm = max(fwhm_func(pos), MIN_W)
        _add_peak_windowed(prof, grid, pos + prm.zero, height, fwhm, prm.eta,
                           prm.asym, prm.bfactor, d, prm.integrated)
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
