"""T4.4 验收 · 非线性精修测试：v50 宽扫谱 Rwp≤10%（不释放 eta）+ 收敛曲线图。"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bench_b  # noqa: E402

from rutana.core.profile.forward import ProfileParams  # noqa: E402
from rutana.core.refine.nonlinear import RefineConfig, refine  # noqa: E402

OUT_DIR = ROOT / "tests" / "out"


@pytest.fixture(scope="module")
def v50_result():
    """v50 宽扫谱精修（模块级只跑一次）。返回 (RefineResult, 耗时秒)。"""
    bench_b.ensure_virtual_b()
    st_a, st_r = bench_b.load_builtin_structs()
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / "v50_wide.xy")
    cfg = RefineConfig(refine_zero=True, refine_uvw=True, refine_eta=False,
                       n_bg=3, max_iter=40)
    t0 = time.perf_counter()
    res = refine([st_a, st_r], pat, ProfileParams(integrated=False), cfg)
    return res, time.perf_counter() - t0


def test_refine_converges(v50_result):
    res, _elapsed = v50_result
    assert res.success


def test_rwp_within_10pct(v50_result):
    """标准硬条款: Rwp ≤ 10%（不释放 eta, n_bg=3）。"""
    res, _elapsed = v50_result
    assert res.rf.rwp <= 10.0


def test_recovered_params_close_to_truth(v50_result):
    """truth: zero=0.03, U=0.02, V=0, W=0.02, eta=0.5(固定)。"""
    res, _elapsed = v50_result
    prm = res.params
    assert abs(prm.zero - 0.03) < 0.02
    assert abs(prm.U - 0.02) < 0.01
    assert abs(prm.W - 0.02) < 0.01
    assert prm.eta == 0.5  # 未释放


def test_history_decreases(v50_result):
    """history 记录 Rwp 且整体收敛（末值显著低于首值）。"""
    res, _elapsed = v50_result
    h = res.history
    assert len(h) > 5
    assert h[-1] < h[0]
    assert min(h) <= res.rf.rwp + 1e-6


def test_refine_perf(v50_result):
    """一次完整精修 < 15 s。"""
    _res, elapsed = v50_result
    assert elapsed < 15.0


def test_convergence_plot(v50_result):
    """两条历史曲线（收敛 + 拟合图）输出到 tests/out/refine_v50.png。"""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    bench_b.ensure_virtual_b()
    res, _elapsed = v50_result
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / "v50_wide.xy")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4))
    ax1.plot(res.history, ".-")
    ax1.set_xlabel("residual evaluation")
    ax1.set_ylabel("Rwp (%)")
    ax1.set_title(f"v50 refine history (final {res.rf.rwp:.2f}%)")
    ax2.plot(pat.two_theta, pat.intensity - res.ycalc, ".", ms=1.5)
    ax2.axhline(0.0, color="C3", lw=0.8)
    ax2.set_xlabel("2θ (deg)")
    ax2.set_ylabel("obs - calc")
    png = OUT_DIR / "refine_v50.png"
    fig.tight_layout()
    fig.savefig(png, dpi=120)
    plt.close(fig)
    assert png.exists() and png.stat().st_size > 5000


def test_negative_scale_refine_drops_phase():
    """只有单相可解释时, 另一相 scale 应为 0（phase_dropped 非空不强制）。"""
    bench_b.ensure_virtual_b()
    st_a, st_r = bench_b.load_builtin_structs()
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / "v0.1_wide.xy")
    cfg = RefineConfig(n_bg=3, max_iter=40)
    res = refine([st_a, st_r], pat, ProfileParams(integrated=False), cfg)
    assert res.success
    assert res.scales[0] >= 0.0 and res.scales[1] >= 0.0
    assert res.rf.rwp <= 10.0
