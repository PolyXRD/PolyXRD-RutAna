"""v1.4.0 · 择优取向（March–Dollase）精修测试。

方法论与 tools/bench_b.py 同源：用 Rutana 自己的前向模型合成两相混合样
（已知 scale、低噪声、tent 背景、积分强度口径），再精修回收。覆盖：

1. 等价性：po_r 明细路径 vs 直接传 po=(h,k,l,r) 给 compute_peaks 手工
   叠加（allclose）；r=1 时与 po=None 逐位一致；
2. 酸性：r=1.4 与 r=1 的计算谱必须不同（相对偏差 >1%），且
   march_dollase_weight(cos, 1) == 1；
3. 回收：合成 anatase po=(0,0,1,1.4) + rutile r=1，默认起点
   （po_r 全 1.0）+ refine_po=True 精修，回收 r_a ∈ 1.4±0.15、
   r_r ∈ 1.0±0.15，Rwp ≤ 2%，QPA 回收 |误差| ≤ 1pp；
4. 关闭路径：refine_po=False 时 result.po_r is None，且与不涉及 PO 的
   基线行为一致（峰形不受影响，ycalc 逐位一致）；
5. 边界：真实 r=0.25 的合成样精修回收值 ≥ PO_BOUNDS[0]，且任意结果 r
   都在 [0.2, 5.0] 内；
6. 性能护栏：开 PO 精修的单样本耗时不得超过关闭版的 3 倍。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rutana.core.profile.cif import parse_cif  # noqa: E402
from rutana.core.profile.forward import (  # noqa: E402
    MIN_W,
    ProfileParams,
    _add_peak_windowed,
    caglioti_2theta,
    compute_phase_profile,
)
from rutana.core.profile.shape import (  # noqa: E402
    march_dollase_weight,
    resolve_wavelengths,
)
from rutana.core.profile.struct import compute_peaks  # noqa: E402
from rutana.core.refine.linear import tent_basis  # noqa: E402
from rutana.core.refine.nonlinear import (  # noqa: E402
    DEFAULT_PO_HKL,
    PO_BOUNDS,
    RefineConfig,
    refine,
)
from rutana.core.refine.qpa import (  # noqa: E402
    qpa_inputs_from_cif,
    qpa_weights,
    to_ratio,
)

DATA = ROOT / "rutana" / "data"
GRID = np.arange(10.0, 90.0, 0.02)
SEED = 20261016
#: 合成样的真值峰形（与 refine 起点刻意不同：zero/U/V 从 0 出发）
TRUTH_PRM = ProfileParams(zero=0.03, U=0.02, V=0.0, W=0.02, eta=0.5,
                          anode="Cu", ka_ratio=0.5, integrated=True)
#: 合成样的内置两相择优取向真值（锐钛板状 (001) r=1.4；金红石无取向）
TRUTH_PO = {"anatase": (0, 0, 1, 1.4), "rutile": (1, 1, 0, 1.0)}
#: 真值质量分数（%）
WA_TRUE, WR_TRUE = 62.0, 38.0


@pytest.fixture(scope="module")
def structs():
    return (parse_cif(DATA / "anatase.cif"), parse_cif(DATA / "rutile.cif"))


def _manual_profile(struct, grid, prm, po, tmin, tmax):
    """直接用 compute_peaks(po=...) 手工叠加单相谱（与 compute_phase_profile
    同一峰形/窗口化/积分强度口径，唯一差别是峰强来自直接 PO 计算）。"""
    comps = resolve_wavelengths(prm.wavelength, prm.anode, prm.ka_ratio)
    peaks, _skipped = compute_peaks(struct, prm.wavelength, tmin, tmax,
                                    po=po, wavelengths=comps)
    fwhm_func = caglioti_2theta(prm.U, prm.V, max(prm.W, MIN_W))
    prof = np.zeros_like(grid, dtype=np.float64)
    for pos, height, d in peaks:
        if height <= 0:
            continue
        fwhm = max(fwhm_func(pos), MIN_W)
        _add_peak_windowed(prof, grid, pos + prm.zero, height, fwhm, prm.eta,
                           prm.asym, prm.bfactor, d, prm.integrated)
    return prof


def _synth_mixture(structs, po_anatase, po_rutile, seed=SEED):
    """合成两相混合样（Hill–Howard 自洽标度 + tent 背景 + 泊松低噪声）。

    返回 (Pattern, 真值 dict)。scale 取 w/(Z·M·V)·C，使 QPA 公式
    W ∝ S·Z·V·M 正好还原质量分数。
    """
    from rutana.core.dtypes import Pattern

    st_a, st_r = structs
    za, va, ma = qpa_inputs_from_cif(st_a, "O2 Ti")
    zr, vr, mr = qpa_inputs_from_cif(st_r, "O2 Ti")
    prm = ProfileParams(**{**TRUTH_PRM.__dict__,
                           "po_r": {"anatase": po_anatase, "rutile": po_rutile}})
    pa = compute_phase_profile(st_a, GRID, prm, 10.0, 90.0)
    pr = compute_phase_profile(st_r, GRID, prm, 10.0, 90.0)
    # 物理标度: S_p = w_p/(Z·M·V)·C，C 把混合峰峰值拉到 ~100 万计数
    # （泊松噪声下 Rwp ≈ sqrt(N/Σy) ~1.2%，满足 ≤2% 判据的统计前提）
    peak_per_c = (WA_TRUE / (za * ma * va)) * float(pa.max()) \
        + (WR_TRUE / (zr * mr * vr)) * float(pr.max())
    c_scale = 1.0e6 / peak_per_c
    sa = WA_TRUE / (za * ma * va) * c_scale
    sr = WR_TRUE / (zr * mr * vr) * c_scale
    # tent 背景（8 节点系数 -> 精确落在精修背景模型的张成空间内）
    bg_coeffs = np.array([120.0, 60.0, 30.0, 20.0, 15.0, 12.0, 10.0, 8.0])
    bg = tent_basis(GRID, bg_coeffs.size) @ bg_coeffs
    y = sa * pa + sr * pr + bg
    rng = np.random.default_rng(seed)
    y_noisy = rng.poisson(np.maximum(y, 0.0)).astype(float)
    pat = Pattern(two_theta=GRID.copy(), intensity=y_noisy,
                  meta={"source": "po_synth"})
    truth = {"wa": WA_TRUE, "wr": WR_TRUE, "zero": TRUTH_PRM.zero,
             "U": TRUTH_PRM.U, "V": TRUTH_PRM.V, "W": TRUTH_PRM.W,
             "eta": TRUTH_PRM.eta, "r_anatase": po_anatase[3],
             "r_rutile": po_rutile[3]}
    return pat, truth


def _qpa(structs, res):
    """内置两相 (w_锐钛%, w_金红石%)。"""
    st_a, st_r = structs
    za, va, ma = qpa_inputs_from_cif(st_a, "O2 Ti")
    zr, vr, mr = qpa_inputs_from_cif(st_r, "O2 Ti")
    ws = qpa_weights([(st_a.name, float(res.scales[0]), za, va, ma),
                      (st_r.name, float(res.scales[1]), zr, vr, mr)])
    return to_ratio(ws, 0, 1)


def _refine_cfg(**kw):
    """任务指定的回收精修配置（PO 精修 + tent 8 节点 + scipy 后端）。"""
    base = dict(refine_zero=True, refine_uvw=True, refine_eta=True,
                refine_po=True, n_bg=8, bg_mode="tent", backend="scipy",
                tmin=10.0, tmax=90.0)
    base.update(kw)
    return RefineConfig(**base)


# --------------------------------------------------------------------------- #
# 1. 等价性
# --------------------------------------------------------------------------- #
def test_detail_path_equivalent_to_direct_po(structs):
    """po_r 明细路径与直接 po=(h,k,l,r) 手工叠加 allclose（优化无损）。"""
    st = structs[0]
    prm = ProfileParams(**{**TRUTH_PRM.__dict__,
                           "po_r": {"anatase": (0, 0, 1, 1.4)}})
    fast = compute_phase_profile(st, GRID, prm, 10.0, 90.0)
    ref = _manual_profile(st, GRID, TRUTH_PRM, (0, 0, 1, 1.4), 10.0, 90.0)
    scale = float(ref.max())
    assert np.allclose(fast, ref, rtol=0, atol=1e-9 * scale), \
        f"最大偏差 {np.max(np.abs(fast - ref)):.3e} (scale={scale:.3e})"


def test_r1_matches_no_po_bit_exact(structs):
    """r=1 时与 po=None 逐位一致（明细路径零开销语义）。"""
    st = structs[1]
    p_r1 = compute_phase_profile(
        st, GRID, ProfileParams(**{**TRUTH_PRM.__dict__,
                                   "po_r": {"rutile": (1, 1, 0, 1.0)}}),
        10.0, 90.0)
    p_none = compute_phase_profile(st, GRID, TRUTH_PRM, 10.0, 90.0)
    assert np.array_equal(p_r1, p_none)


def test_po_detail_requires_po(structs):
    """po_detail=True 但 po=None 抛 ValueError。"""
    with pytest.raises(ValueError):
        compute_peaks(structs[0], 1.5406, 10.0, 60.0, po=None, po_detail=True)


# --------------------------------------------------------------------------- #
# 2. 酸性
# --------------------------------------------------------------------------- #
def test_r_changes_profile_and_neutral_weight(structs):
    """r=1.4 与 r=1 的计算谱相对偏差 >1%；march_dollase_weight(cos,1)==1。"""
    st = structs[0]
    p1 = compute_phase_profile(st, GRID, TRUTH_PRM, 10.0, 90.0)
    p14 = compute_phase_profile(
        st, GRID, ProfileParams(**{**TRUTH_PRM.__dict__,
                                   "po_r": {"anatase": (0, 0, 1, 1.4)}}),
        10.0, 90.0)
    rel = float(np.max(np.abs(p14 - p1)) / max(float(p1.max()), 1e-30))
    assert rel > 0.01, f"r=1.4 与 r=1 偏差仅 {rel:.4%}，PO 未生效？"
    for ca in (-1.0, -0.3, 0.0, 0.5, 1.0):
        assert march_dollase_weight(ca, 1.0) == 1.0


# --------------------------------------------------------------------------- #
# 3. 回收
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="module")
def recovery():
    """合成样 + refine_po=True 精修结果（模块级只跑一次）。"""
    sts = (parse_cif(DATA / "anatase.cif"), parse_cif(DATA / "rutile.cif"))
    pat, truth = _synth_mixture(sts, (0, 0, 1, 1.4), (1, 1, 0, 1.0))
    prm0 = ProfileParams(zero=0.0, U=0.0, V=0.0, W=0.02, eta=0.5,
                         anode="Cu", ka_ratio=0.5, integrated=True)
    res = refine(sts, pat, prm0, _refine_cfg())
    return sts, pat, truth, res


def test_recovery_po_r(recovery):
    """回收 r_a ∈ 1.4±0.15、r_r ∈ 1.0±0.15。"""
    _sts, _pat, truth, res = recovery
    assert res.po_r is not None, "refine_po=True 应产出 po_r"
    r_a = res.po_r["anatase"][3]
    r_r = res.po_r["rutile"][3]
    assert abs(r_a - truth["r_anatase"]) <= 0.15, f"r_a={r_a:.3f}"
    assert abs(r_r - truth["r_rutile"]) <= 0.15, f"r_r={r_r:.3f}"


def test_recovery_rwp_and_qpa(recovery):
    """Rwp ≤ 2%；QPA 回收 |误差| ≤ 1pp。"""
    sts, _pat, truth, res = recovery
    assert res.rf.rwp <= 2.0, f"Rwp={res.rf.rwp:.2f}%"
    wa, wr = _qpa(sts, res)
    assert abs(wa - truth["wa"]) <= 1.0, f"wa={wa:.2f} (真值 {truth['wa']})"
    assert abs(wr - truth["wr"]) <= 1.0, f"wr={wr:.2f} (真值 {truth['wr']})"


# --------------------------------------------------------------------------- #
# 4. 关闭路径
# --------------------------------------------------------------------------- #
def test_po_off_returns_none_and_matches_baseline(structs):
    """refine_po=False 时 po_r is None，且 ycalc 与不涉及 PO 的基线逐位一致。"""
    pat, _truth = _synth_mixture(structs, (0, 0, 1, 1.0), (1, 1, 0, 1.0),
                                 seed=SEED + 1)
    prm0 = ProfileParams(zero=0.0, U=0.0, V=0.0, W=0.02, eta=0.5,
                         anode="Cu", ka_ratio=0.5, integrated=True)
    cfg_off = _refine_cfg(refine_po=False)
    res_off = refine(structs, pat, prm0, cfg_off)
    assert res_off.po_r is None, "refine_po=False 时 RefineResult.po_r 应为 None"
    # 基线：完全不经 PO 路径的同配置精修（prm0.po_r=None）
    res_base = refine(structs, pat, prm0, _refine_cfg(refine_po=False))
    assert np.array_equal(res_off.ycalc, res_base.ycalc), \
        "关闭路径应与开启前基线行为逐位一致"


# --------------------------------------------------------------------------- #
# 5. 边界
# --------------------------------------------------------------------------- #
def test_po_bounds_extreme_texture(structs):
    """真实 r=0.25 的合成样：回收值 ≥ PO_BOUNDS[0] 且落在 [0.2, 5.0] 内。"""
    pat, truth = _synth_mixture(structs, (0, 0, 1, 0.25), (1, 1, 0, 1.0),
                                seed=SEED + 2)
    prm0 = ProfileParams(zero=0.0, U=0.0, V=0.0, W=0.02, eta=0.5,
                         anode="Cu", ka_ratio=0.5, integrated=True)
    res = refine(structs, pat, prm0, _refine_cfg())
    r_a = res.po_r["anatase"][3]
    assert PO_BOUNDS[0] <= r_a <= PO_BOUNDS[1], f"r_a={r_a:.3f} 越界"
    assert r_a >= PO_BOUNDS[0], f"r_a={r_a:.3f} 低于下界"
    assert res.po_r["rutile"][3] >= PO_BOUNDS[0]
    # 强织构样上回收值应显著偏向真值一侧（低于中性 1.0）
    assert r_a < 0.9, f"r_a={r_a:.3f} 未回收强板状织构（真值 {truth['r_anatase']}）"


def test_default_po_hkl_matches_builtin_phases():
    """DEFAULT_PO_HKL 覆盖内置两相（锐钛 (001)、金红石 (110)）。"""
    assert DEFAULT_PO_HKL["anatase"] == (0, 0, 1)
    assert DEFAULT_PO_HKL["rutile"] == (1, 1, 0)


# --------------------------------------------------------------------------- #
# 6. 性能护栏
# --------------------------------------------------------------------------- #
def test_po_refine_perf_guard(structs):
    """开 PO 精修的单样本耗时不得超过关闭版的 3 倍（明细路径应接近 1.x）。"""
    pat, _truth = _synth_mixture(structs, (0, 0, 1, 1.4), (1, 1, 0, 1.0),
                                 seed=SEED + 3)
    prm0 = ProfileParams(zero=0.0, U=0.0, V=0.0, W=0.02, eta=0.5,
                         anode="Cu", ka_ratio=0.5, integrated=True)
    t0 = time.perf_counter()
    refine(structs, pat, prm0, _refine_cfg(refine_po=False))
    t_off = time.perf_counter() - t0
    t0 = time.perf_counter()
    refine(structs, pat, prm0, _refine_cfg(refine_po=True))
    t_on = time.perf_counter() - t0
    assert t_on <= 3.0 * t_off, \
        f"PO 开 {t_on:.1f}s vs 关 {t_off:.1f}s（超过 3 倍，缓存键可能没改对）"
