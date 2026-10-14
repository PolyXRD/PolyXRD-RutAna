"""T3.1 验收 · 内置 CIF 测试：解析 / d 值 / 强度序 / Z / V。"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rutana.core.profile.cif import parse_cif
from rutana.core.profile.shape import resolve_wavelengths
from rutana.core.profile.struct import compute_peaks
from rutana.core.refine.qpa import infer_z, qpa_inputs_from_cif

DATA = Path(__file__).resolve().parent.parent / "rutana" / "data"

# PDF 卡参考（21-1272 锐钛型 / 21-1276 金红石型，最强 5 线，d 单位 Å）
REF = {
    "anatase": [3.520, 1.892, 2.378, 1.700, 1.667],
    "rutile": [3.247, 1.687, 2.487, 2.188, 1.452],
}
TOP3 = {"anatase": [3.520, 1.892, 2.378], "rutile": [3.247, 1.687, 2.487]}
EXPECT_Z = {"anatase": 4, "rutile": 2}
EXPECT_V = {"anatase": 136.3, "rutile": 62.42}
EXPECT_PEAK = {"anatase": 25.30, "rutile": 27.44}


def _top_lines(name: str, n: int = 5):
    st = parse_cif(DATA / f"{name}.cif")
    peaks, _sk = compute_peaks(st, 1.5406, 5.0, 90.0,
                               wavelengths=resolve_wavelengths(1.5406, None))
    pairs = sorted(((d, h) for _p, h, d in peaks),
                   key=lambda t: (-t[1], -t[0]))
    hmax = pairs[0][1]
    return st, [(d, 100.0 * h / hmax) for d, h in pairs[:n]], \
        sorted(peaks, key=lambda t: -t[1])[0]


@pytest.mark.parametrize("name", ["anatase", "rutile"])
def test_cif_parses(name):
    st = parse_cif(DATA / f"{name}.cif")
    assert st.cell[0] > 3.0 and st.cell[2] > 2.0
    # 全晶胞原子数: TiO2 每化学式单元 3 原子 -> 锐钛型 3×Z=12, 金红石型 3×Z=6
    assert len(st.atoms) == 3 * EXPECT_Z[name]


@pytest.mark.parametrize("name", ["anatase", "rutile"])
def test_d_values_within_0p5pct(name):
    """最强 5 线 d 值与 PDF 卡偏差 < 0.5%。"""
    _st, top, _strong = _top_lines(name)
    all_d = [d for d, _i in top] + _all_computed_d(name)
    for rd in REF[name]:
        best = min(abs(cd - rd) / rd for cd in all_d)
        assert best < 0.005, f"{name}: ref d={rd} 最近偏差 {best * 100:.3f}%"


def _all_computed_d(name: str) -> list[float]:
    st = parse_cif(DATA / f"{name}.cif")
    peaks, _sk = compute_peaks(st, 1.5406, 5.0, 90.0,
                               wavelengths=resolve_wavelengths(1.5406, None))
    return [d for _p, _h, d in peaks]


@pytest.mark.parametrize("name", ["anatase", "rutile"])
def test_top3_intensity_order_matches_card(name):
    """最强 3 线的强度排序与 PDF 卡一致。"""
    _st, top, _strong = _top_lines(name)
    for got, ref in zip(top, TOP3[name]):
        assert abs(got[0] - ref) / ref < 0.005


@pytest.mark.parametrize("name", ["anatase", "rutile"])
def test_strongest_peak_position(name):
    """最强峰 2θ 与标准值 ±0.05°。"""
    _st, _top, (pos, _h, _d) = _top_lines(name)
    assert abs(pos - EXPECT_PEAK[name]) < 0.05


@pytest.mark.parametrize("name", ["anatase", "rutile"])
def test_z_and_volume(name):
    """Z 反算 = 4/2，晶胞体积与标准值偏差 < 1%。"""
    st = parse_cif(DATA / f"{name}.cif")
    assert infer_z(st, "O2 Ti") == EXPECT_Z[name]
    z, v, m = qpa_inputs_from_cif(st, "O2 Ti")
    assert abs(v - EXPECT_V[name]) / EXPECT_V[name] < 0.01
    assert abs(m - 79.87) < 0.05
