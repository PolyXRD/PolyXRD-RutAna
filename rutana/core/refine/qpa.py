"""B 法精修 · QPA 定量换算（T4.5 ★酸检卡）。

Hill–Howard (Rietveld) 质量分数:
    W_p = S_p·Z_p·V_p·M_p / Σ_q S_q·Z_q·V_q·M_q
其中 S 为精修相标度、Z 为晶胞内化学式单元数、V 为晶胞体积 (Å³)、M 为化学式量。
推导: 衍射强度 ∝ 晶胞数 × |F|²，晶胞数 ∝ w_p/(Z·M·V)，故 w_p ∝ S·Z·M·V。

★酸检: (ZMV)_锐/(ZMV)_金 = (4×136.3)/(2×62.42) ≈ 4.368。
  若 S_锐 = S_金，则 w_锐 = 4·136.3/(4·136.3 + 2·62.42) ≈ 81.37%（不是 50%）。
  任何 scale→质量分数的换算错误都会被这条测试立刻打出来。
"""
from __future__ import annotations

import re
from dataclasses import dataclass

import numpy as np

from rutana.core.profile.cif import CifStructure

# 常用元素摩尔质量 (g/mol, IUPAC 2021)。TiO2 = 47.867 + 2×15.999 = 79.865 ≈ 79.87
ATOMIC_MASS = {
    "H": 1.008, "He": 4.003, "Li": 6.94, "Be": 9.012, "B": 10.81,
    "C": 12.011, "N": 14.007, "O": 15.999, "F": 18.998, "Na": 22.990,
    "Mg": 24.305, "Al": 26.982, "Si": 28.085, "P": 30.974, "S": 32.06,
    "Cl": 35.45, "K": 39.098, "Ca": 40.078, "Ti": 47.867, "V": 50.942,
    "Cr": 51.996, "Mn": 54.938, "Fe": 55.845, "Co": 58.933, "Ni": 58.693,
    "Cu": 63.546, "Zn": 65.38, "Ga": 69.723, "Ge": 72.630, "As": 74.922,
    "Se": 78.971, "Br": 79.904, "Sr": 87.62, "Y": 88.906, "Zr": 91.224,
    "Nb": 92.906, "Mo": 95.95, "Ag": 107.868, "Cd": 112.414, "Sn": 118.710,
    "Sb": 121.760, "Ba": 137.327, "La": 138.905, "Ce": 140.116, "W": 183.84,
    "Pt": 195.084, "Au": 196.967, "Hg": 200.592, "Pb": 207.2, "Bi": 208.980,
}

_MASS_RE = re.compile(r"([A-Z][a-z]?)(\d*\.?\d*)")


@dataclass(frozen=True)
class PhaseWeight:
    """单相 QPA 输入/输出。"""

    name: str
    scale: float
    Z: int
    volume: float
    mass: float
    weight: float


def formula_mass(formula: str) -> float:
    """化学式 -> 摩尔质量 (g/mol)。支持 'TiO2' / 'O2 Ti' (COD 风格) 等。"""
    total = 0.0
    for elem, cnt in _MASS_RE.findall(formula.replace(" ", "")):
        if elem not in ATOMIC_MASS:
            raise ValueError(f"未知元素摩尔质量: {elem} (in {formula})")
        total += ATOMIC_MASS[elem] * (float(cnt) if cnt else 1.0)
    if total <= 0.0:
        raise ValueError(f"化学式量解析失败: {formula}")
    return total


def _formula_counts(formula: str) -> dict[str, float]:
    """化学式 -> {元素: 个数}。"""
    counts: dict[str, float] = {}
    for elem, cnt in _MASS_RE.findall(formula.replace(" ", "")):
        counts[elem] = counts.get(elem, 0.0) + (float(cnt) if cnt else 1.0)
    return counts


def infer_z(struct: CifStructure, formula: str) -> int:
    """由 CIF 全晶胞原子数 + 化学式反算 Z（晶胞内化学式单元数）。

    对每个元素计算 n_cell/n_formula，取一致的最小整数值。
    锐钛型 I41/amd 应得 4，金红石型 P42/mnm 应得 2（见 test_qpa）。
    """
    f_counts = _formula_counts(formula)
    if not f_counts:
        raise ValueError(f"化学式解析失败: {formula}")
    cell_counts: dict[str, float] = {}
    for (elem, _x, _y, _z, occ, _B) in struct.atoms:
        cell_counts[elem] = cell_counts.get(elem, 0.0) + float(occ)
    estimates = []
    for elem, n_f in f_counts.items():
        if elem in cell_counts and n_f > 0:
            estimates.append(cell_counts[elem] / n_f)
    if not estimates:
        raise ValueError(f"CIF 原子与化学式 {formula} 无公共元素")
    z_est = min(estimates)
    z_int = int(round(z_est))
    if z_int < 1 or abs(z_est - z_int) > 0.05:
        raise ValueError(f"Z 反算不一致: {estimates} (formula={formula})")
    return z_int


def qpa_inputs_from_cif(struct: CifStructure, formula: str) -> tuple[int, float, float]:
    """从 CifStructure 提取 (Z, V(Å³), M(g/mol)) 三元组，供 qpa_weights。"""
    return infer_z(struct, formula), float(struct.volume), formula_mass(formula)


def qpa_weights(weights: list[tuple[str, float, int, float, float]]) -> list[PhaseWeight]:
    """tuple = (name, scale, Z, cell_volume, formula_mass) -> 归一化质量分数。

    weight_p = S_p·Z_p·V_p·M_p / Σ；scale 全零或非法时抛 ValueError。
    """
    if not weights:
        raise ValueError("至少需要一个物相")
    total = 0.0
    raw = []
    for (name, scale, z, vol, mass) in weights:
        if scale < 0 or z <= 0 or vol <= 0 or mass <= 0:
            raise ValueError(f"非法 QPA 输入: {(name, scale, z, vol, mass)}")
        s = float(scale) * float(z) * float(vol) * float(mass)
        raw.append(s)
        total += s
    if total <= 0.0:
        raise ValueError("所有相 scale 之积为 0，无法定量")
    return [PhaseWeight(name=w[0], scale=float(w[1]), Z=int(w[2]),
                        volume=float(w[3]), mass=float(w[4]),
                        weight=float(s / total))
            for w, s in zip(weights, raw)]


def to_ratio(ws: list[PhaseWeight], i_anatase: int, i_rutile: int) -> tuple[float, float]:
    """从 PhaseWeight 列表取 (w_anatase %, w_rutile %)，两晶相相对比率。"""
    wa = ws[i_anatase].weight
    wr = ws[i_rutile].weight
    tot = wa + wr
    if tot <= 0.0:
        raise ValueError("两晶相质量分数之和为 0")
    return (100.0 * wa / tot, 100.0 * wr / tot)
