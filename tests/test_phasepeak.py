"""主峰参数（谢乐晶粒度）与带 hkl 反射枚举的测试。

覆盖三层：
1. 数值口径：Bragg 反算 d、谢乐公式的解析值；
2. 与拟合热路径的一致性：``compute_reflections``（带 hkl）必须与
   ``compute_peaks``（无 hkl、全空间枚举）同位置同强度（后者是全空间，
   强度恰为本函数的 2 倍——Friedel 对）；
3. 端到端：合成谱上跑 ``main_peaks``，主峰指数、峰位、晶粒度量级都要对。
"""

from __future__ import annotations

import math
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest

from rutana.core.dtypes import Pattern
from rutana.core.phasepeak import (
    DEFAULT_WAVELENGTH,
    bragg_d,
    main_peaks,
    pick_main_reflections,
    scherrer_size_nm,
)
from rutana.core.profile.cif import parse_cif
from rutana.core.profile.forward import ProfileParams, compute_phase_profile
from rutana.core.profile.reflections import compute_reflections
from rutana.core.profile.struct import compute_peaks

DATA = Path(__file__).resolve().parent.parent / "rutana" / "data"


@pytest.fixture(scope="module")
def phases():
    return [parse_cif(str(DATA / "anatase.cif")),
            parse_cif(str(DATA / "rutile.cif"))]


def _synthetic(phases, *, w: float = 0.02, two_min: float = 20.0,
               two_max: float = 120.0, step: float = 0.01,
               seed: int = 7) -> Pattern:
    """两相合成谱（常数 FWHM、单色光、泊松噪声），用于端到端校验。

    两相各自归一化到主峰 18000 / 5000 counts，再叠 60 counts 常数背景，
    强度量级与真实谱一致（便于按 SNR 判断哪些峰该测得出）。
    """
    tt = np.arange(two_min, two_max + step, step)
    prm = ProfileParams(zero=0.0, U=0.0, V=0.0, W=w, eta=0.5, anode=None,
                        wavelength=DEFAULT_WAVELENGTH, integrated=True)
    ya = compute_phase_profile(phases[0], tt, prm)
    yr = compute_phase_profile(phases[1], tt, prm)
    y = 60.0 + 18000.0 * ya / ya.max() + 5000.0 * yr / yr.max()
    rng = np.random.default_rng(seed)
    return Pattern(tt, rng.poisson(y).astype(float))


# --------------------------------------------------------------------------- #
# 1. 数值口径
# --------------------------------------------------------------------------- #
def test_bragg_d_anatase_101():
    """锐钛矿 (101) d ≈ 3.512 Å（CIF 晶胞 a=3.7845, c=9.5143）。"""
    assert bragg_d(25.34, DEFAULT_WAVELENGTH) == pytest.approx(3.512, abs=2e-3)


def test_scherrer_analytic():
    """谢乐公式解析值：0.2° / 25.3° / Cu Kα1 -> 40.71 nm。"""
    d = scherrer_size_nm(0.2, 25.3)
    assert d == pytest.approx(40.71, abs=0.05)


def test_scherrer_invalid():
    """FWHM 非正 / nan / 无意义角度时返回 None（界面显示「—」）。"""
    assert scherrer_size_nm(0.0, 25.3) is None
    assert scherrer_size_nm(float("nan"), 25.3) is None
    assert scherrer_size_nm(-0.1, 25.3) is None


# --------------------------------------------------------------------------- #
# 2. 与 compute_peaks 一致性
# --------------------------------------------------------------------------- #
def test_reflections_match_compute_peaks(phases):
    """同窗口下位置/d 完全一致，强度为本函数的 2 倍（全空间 vs 半空间）。"""
    for struct in phases:
        refl = compute_reflections(struct, DEFAULT_WAVELENGTH, 20.0, 100.0)
        peaks, _skipped = compute_peaks(struct, DEFAULT_WAVELENGTH, 20.0, 100.0)
        assert len(refl) == len(peaks)
        for (pos, d, val, _hkl), (pos2, val2, d2) in zip(refl, peaks):
            assert pos == pytest.approx(pos2, abs=1e-9)
            assert d == pytest.approx(d2, rel=1e-12)
            assert 2.0 * val == pytest.approx(val2, rel=1e-9)


def test_reflections_hkl_are_conventional(phases):
    """最强反射的指数按卡片惯例（锐钛 101、金红石 110）。"""
    ana = compute_reflections(phases[0], DEFAULT_WAVELENGTH, 20.0, 60.0)
    rut = compute_reflections(phases[1], DEFAULT_WAVELENGTH, 20.0, 60.0)
    assert max(ana, key=lambda r: r[2])[3] == (1, 0, 1)
    assert max(rut, key=lambda r: r[2])[3] == (1, 1, 0)


def test_pick_main_reflections_spacing(phases):
    """主峰挑选：按强度取前 n，且两两间距不小于 min_sep。"""
    refl = compute_reflections(phases[0], DEFAULT_WAVELENGTH, 20.0, 120.0)
    picked = pick_main_reflections(refl, n=5, lo=20.0, hi=120.0)
    assert len(picked) == 5
    positions = [p[0] for p in picked]
    assert positions == sorted(positions)
    assert all(b - a >= 0.6 for a, b in pairwise(positions))


# --------------------------------------------------------------------------- #
# 3. 端到端
# --------------------------------------------------------------------------- #
def test_main_peaks_on_synthetic(phases):
    """合成谱：两相各 5 条主峰，指数/峰位正确，晶粒度接近设定 FWHM。"""
    pat = _synthetic(phases, w=0.02)
    rows = main_peaks(pat, phases)
    assert len(rows) == 10
    assert [r.phase for r in rows] == ["anatase"] * 5 + ["rutile"] * 5

    ana = [r for r in rows if r.phase == "anatase"]
    rut = [r for r in rows if r.phase == "rutile"]
    assert ana[0].hkl == (1, 0, 1)
    assert ana[0].two_theta == pytest.approx(25.28, abs=0.15)
    assert rut[0].hkl == (1, 1, 0)
    assert rut[0].two_theta == pytest.approx(27.45, abs=0.15)
    # 相对强度：每相最强峰为 100%
    assert ana[0].rel_intensity == pytest.approx(100.0, abs=0.5)
    assert rut[0].rel_intensity == pytest.approx(100.0, abs=0.5)

    # 合成谱 FWHM = sqrt(W) = 0.1414°，谢乐值应在 ±15% 内对上解析值
    expect = scherrer_size_nm(math.sqrt(0.02), ana[0].two_theta)
    assert ana[0].size_nm == pytest.approx(expect, rel=0.15)
    # 金红石 211（54.3°）夹在锐钛 105/211 之间，允许个别重叠峰测不出
    assert sum(r.ok for r in rows) >= 8


def test_main_peaks_respects_pattern_range(phases):
    """谱只到 30° 时，两相各只保留落在范围内的那条主峰。"""
    pat = _synthetic(phases, two_min=20.0, two_max=30.0)
    rows = main_peaks(pat, phases)
    assert len(rows) == 2
    assert [r.hkl for r in rows] == [(1, 0, 1), (1, 1, 0)]


def test_main_peaks_missing_phase_keeps_rows(phases):
    """纯锐钛矿谱：金红石各峰测不出但行仍在（ok=False，界面显示「—」）。"""
    pat = _synthetic(phases, w=0.02)
    prm = ProfileParams(zero=0.0, U=0.0, V=0.0, W=0.02, eta=0.5, anode=None,
                        wavelength=DEFAULT_WAVELENGTH)
    ya = compute_phase_profile(phases[0], pat.two_theta, prm)
    y = 60.0 + 18000.0 * ya / ya.max()
    rows = main_peaks(Pattern(pat.two_theta, y), phases)
    ana = [r for r in rows if r.phase == "anatase"]
    rut = [r for r in rows if r.phase == "rutile"]
    assert len(ana) == 5 and len(rut) == 5
    assert all(r.ok for r in ana)
    assert any(not r.ok for r in rut)
    assert all(r.size_nm is None for r in rut if not r.ok)
