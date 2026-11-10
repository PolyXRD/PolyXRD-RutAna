"""主峰参数与谢乐晶粒度（锐钛矿 / 金红石）。

用途
----
GUI 的「主峰参数」区在谱图下方常驻显示两相主峰的 2θ / d / (hkl) / 强度 /
半峰宽 / 晶粒尺寸；本模块是该表的**唯一数据来源**（纯 core，无 Qt 依赖），
便于单测与将来复用到报告/CLI。

口径（表内数值自洽，且与图上曲线一致）
------------------------------------
- 峰位、净峰高、半峰宽全部取自**实测谱**：逐峰调用
  :func:`rutana.core.peakmeasure.measure_peak`，用与 A 法相同的
  PROTOCOL_V100 背景配置（``linear_edges`` / edge_frac=0.14 / margin 0.18），
  保证「图上看到的峰」与「表里读到的数」是同一套处理；
- d 值由**实测峰位**经 Bragg 方程反算（单色 Kα1 波长），与同行的 2θ 一一对应；
- (hkl) 来自内置 CIF 的结构因子枚举（:mod:`rutana.core.profile.reflections`），
  与理论 2θ 最接近的实测峰绑定；
- 晶粒尺寸按谢乐公式 ``D = K·λ / (β·cosθ)``，K=0.9，β 为实测 FWHM（弧度）。
  **未扣除仪器展宽**，故为表观值：峰越宽给出的 D 越小，只能当作下限参考。

主峰如何挑
----------
每相按理论结构因子强度排序取前 ``n`` 个，且要求与已选峰相距
``MIN_PEAK_SEPARATION`` 度以上（避免把重叠峰误当成两个独立峰），
再按 2θ 升序输出。低于谱图起止范围的峰自动跳过。
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from rutana.core.dtypes import Pattern
from rutana.core.peakmeasure import PROTOCOL_V100, measure_peak
from rutana.core.profile.cif import CifStructure
from rutana.core.profile.reflections import compute_reflections

#: 谢乐常数（球形晶粒、无畸变近似下的通用取值 0.89~0.94，取 0.9）
SCHERRER_K = 0.9

#: Cu Kα1 波长 (Å)；谱图 meta 带 wavelength 时以 meta 为准
DEFAULT_WAVELENGTH = 1.540598

#: 每相默认显示的主峰条数
MAIN_PEAKS_PER_PHASE = 5

#: 两个主峰的最小间距（度）：近于此值的强峰视为重叠，只保留更强者
MIN_PEAK_SEPARATION = 0.6

#: 实测峰位搜索半窗（度）：覆盖零点偏移 + Kα2 复合峰重心偏移（高角约 0.2°）
SEARCH_TOL = 0.4

#: 宽容失败后的重试半窗（度）。重叠区（如金红石 211 夹在锐钛 105/211 之间）的
#: 宽窗会把邻峰裙边当背景，净峰高被吃掉、SNR 不达标；收窄到 0.25° 常能救回，
#: 且不会误判「本就不存在」的峰（那些峰窄窗同样测不出）。
NARROW_TOL = 0.25


@dataclass(frozen=True)
class MainPeak:
    """一条主峰记录（表的一行）。

    two_theta   : 实测峰位 2θ（度）；峰测不出时为理论位置；
    d           : 由 two_theta 反算的晶面间距 (Å)；
    hkl         : 晶面指数（来自理论反射，与理论位置最接近者）；
    intensity   : 净峰高（counts）；测不出时为 nan；
    rel_intensity: 相对本相最强主峰的百分比（%）；测不出时为 nan；
    fwhm        : 实测半峰宽（度，2θ 口径）；测不出时为 nan；
    size_nm     : 谢乐法表观晶粒尺寸 (nm)；无有效 FWHM 时为 None；
    ok          : 该峰是否成功测出（信噪比达标且半高宽可定）。
    """

    phase: str
    two_theta: float
    d: float
    hkl: tuple[int, int, int]
    intensity: float
    rel_intensity: float
    fwhm: float
    size_nm: float | None
    ok: bool = True


def bragg_d(two_theta_deg: float, wavelength: float = DEFAULT_WAVELENGTH) -> float:
    """Bragg 方程：由 2θ（度）与波长算晶面间距 d (Å)。"""
    theta = math.radians(float(two_theta_deg) / 2.0)
    s = math.sin(theta)
    if s <= 0:
        return float("nan")
    return float(wavelength) / (2.0 * s)


def scherrer_size_nm(fwhm_deg: float, two_theta_deg: float,
                     wavelength: float = DEFAULT_WAVELENGTH,
                     k: float = SCHERRER_K) -> float | None:
    """谢乐公式 D = K·λ / (β·cosθ)，返回 nm；参数无效时返回 None。

    fwhm_deg 为 2θ 口径的半峰宽（度），内部换算成弧度 β；
    θ 取 half of 2θ。未扣除仪器展宽，结果为表观晶粒尺寸。
    """
    try:
        fwhm = float(fwhm_deg)
        tt = float(two_theta_deg)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(fwhm) or not math.isfinite(tt) or fwhm <= 0.0:
        return None
    beta = math.radians(fwhm)
    cos_t = math.cos(math.radians(tt / 2.0))
    if beta <= 0.0 or cos_t <= 0.0:
        return None
    return float(k) * float(wavelength) / (beta * cos_t) / 10.0


def pattern_wavelength(pat: Pattern) -> float:
    """谱图波长：优先 meta（RAW/XRDML 读进来的 ``wavelength``），否则 Cu Kα1。"""
    meta = getattr(pat, "meta", None) or {}
    for key in ("wavelength", "wavelength_angstrom", "lambda"):
        try:
            value = float(meta.get(key))
        except (TypeError, ValueError):
            continue
        if 0.3 < value < 3.0:      # 常见靶材合理区间，防止元数据串用
            return value
    return DEFAULT_WAVELENGTH


def pick_main_reflections(refl, *, n: int = MAIN_PEAKS_PER_PHASE,
                          lo: float | None = None, hi: float | None = None,
                          min_sep: float = MIN_PEAK_SEPARATION):
    """从反射列表里挑主峰：按理论强度取前 n 个，且两两间距 >= min_sep。

    refl 为 ``compute_reflections`` 的返回；lo/hi 为可用 2θ 范围（谱图起止）。
    返回仍为 ``(2θ, d, intensity, hkl)`` 元组列表，按 2θ 升序。
    """
    cand = [r for r in refl
            if (lo is None or r[0] >= lo) and (hi is None or r[0] <= hi)]
    cand.sort(key=lambda r: r[2], reverse=True)
    chosen: list[tuple] = []
    for r in cand:
        if any(abs(r[0] - c[0]) < min_sep for c in chosen):
            continue
        chosen.append(r)
        if len(chosen) >= max(1, int(n)):
            break
    chosen.sort(key=lambda r: r[0])
    return chosen


def _measure(pat: Pattern, pos: float, tol: float):
    """单峰测量（V100 背景协议）；异常返回 None 而不抛出。"""
    try:
        return measure_peak(pat, float(pos), tol=tol, cfg=PROTOCOL_V100.bg,
                            bg_margin=PROTOCOL_V100.bg_margin)
    except Exception:  # noqa: BLE001 —— 单峰退化只影响该行
        return None


def _measured_ok(m) -> bool:
    """峰是否可用：信噪比达标且半高宽可定。"""
    return bool(m is not None and getattr(m, "ok", False)
                and math.isfinite(float(getattr(m, "fwhm", float("nan")))))


def main_peaks(pat: Pattern, phases: list[CifStructure], *,
               n: int = MAIN_PEAKS_PER_PHASE,
               wavelength: float | None = None,
               tol: float = SEARCH_TOL) -> list[MainPeak]:
    """按相依次给出主峰参数（锐钛矿在前，相内按 2θ 升序）。

    phases 顺序即输出顺序（GUI 传内置 [anatase, rutile]）；同一相内相对强度
    以该相最强主峰为 100%。测峰失败的行照常保留（ok=False），由界面显示「—」，
    便于用户看出「这一相在这个谱里几乎没有峰」。
    """
    if not phases:
        return []
    lam = float(wavelength) if wavelength else pattern_wavelength(pat)
    lo = float(np.min(pat.two_theta))
    hi = float(np.max(pat.two_theta))
    # 峰位搜索窗要落在谱内，边界峰留出背景余量，避免窗口被截断导致 FWHM 不可定
    edge = tol + PROTOCOL_V100.bg_margin
    rows: list[MainPeak] = []
    for struct in phases:
        try:
            refl = compute_reflections(struct, lam, lo, hi)
        except Exception:  # noqa: BLE001, S112 —— 结构异常不应拖垮整张表
            continue
        picked = pick_main_reflections(refl, n=n, lo=lo + edge, hi=hi - edge)
        if not picked:
            continue
        measured: list[tuple] = []
        for pos0, d0, _val, hkl in picked:
            m = _measure(pat, pos0, tol)
            if not _measured_ok(m) and tol > NARROW_TOL:
                # 重叠区兜底：收窄窗口再测一次（宽窗把邻峰裙边当成了背景）
                m2 = _measure(pat, pos0, NARROW_TOL)
                if _measured_ok(m2):
                    m = m2
            ok = _measured_ok(m)
            pos = float(m.two_theta_at_max) if ok else float(pos0)
            height = float(m.net_height) if ok else float("nan")
            fwhm = float(m.fwhm) if ok else float("nan")
            measured.append((pos, height, fwhm, hkl, d0, ok))
        peak_max = max((r[1] for r in measured if r[5]), default=float("nan"))
        for pos, height, fwhm, hkl, d0, ok in measured:
            d = bragg_d(pos, lam)
            if not math.isfinite(d):
                d = float(d0)
            rel = (height / peak_max * 100.0
                   if math.isfinite(peak_max) and peak_max > 0 else float("nan"))
            rows.append(MainPeak(
                phase=str(struct.name), two_theta=pos, d=d, hkl=tuple(hkl),
                intensity=height, rel_intensity=rel, fwhm=fwhm,
                size_nm=scherrer_size_nm(fwhm, pos, lam), ok=ok))
    return rows
