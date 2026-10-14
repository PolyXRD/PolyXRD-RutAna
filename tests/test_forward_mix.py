"""T3.3 验收 · 两相混合交叉验证：本实现前向 vs SynthPattern 合成（RMS < 2%）。"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bench_b  # noqa: E402

from rutana.core.profile.forward import ProfileParams, compute_phase_profile  # noqa: E402
from rutana.core.refine.qpa import qpa_inputs_from_cif  # noqa: E402

SYNTH_DIR = Path(r"D:/Project/XRD/PolyXRD-SynthPattern")
PROFILE = bench_b.PROFILE


def _model_curve(wa: float) -> tuple[np.ndarray, np.ndarray]:
    """按 truth 配比用本实现 forward 重建合成曲线（含背景, 未加噪）。"""
    st_a, st_r = bench_b.load_builtin_structs()
    za, va, ma = qpa_inputs_from_cif(st_a, "O2 Ti")
    zr, vr, mr = qpa_inputs_from_cif(st_r, "O2 Ti")
    wr = 100.0 - wa
    # 与 bench_b 生成端同一物理标度: 生成器 scale = frac/V, frac ∝ w/(Z·M)
    fa = wa / (za * ma)
    fr = wr / (zr * mr)
    norm = fa + fr
    # 与 xse.make_grid 同构: tmin + step·arange(n)，保证点数与 obs 一致
    n = int(round((PROFILE["tmax"] - PROFILE["step"] - PROFILE["tmin"])
                  / PROFILE["step"])) + 1
    grid = PROFILE["tmin"] + PROFILE["step"] * np.arange(n)
    prm = ProfileParams(zero=PROFILE["zero"], U=PROFILE["U"], V=PROFILE["V"],
                        W=PROFILE["W"], eta=PROFILE["eta"],
                        anode=PROFILE["anode"], ka_ratio=PROFILE["ka_ratio"],
                        integrated=False)  # SynthPattern 合成器是峰高口径
    pa = compute_phase_profile(st_a, grid, prm, PROFILE["tmin"], PROFILE["tmax"])
    pr = compute_phase_profile(st_r, grid, prm, PROFILE["tmin"], PROFILE["tmax"])
    pattern = (fa / norm) / va * pa + (fr / norm) / vr * pr
    # 生成器把 pattern 峰值拉到 target_peak 后再加线性背景
    pattern = pattern * (PROFILE["target_peak"] / pattern.max())
    y = pattern + PROFILE["bg"][0] + PROFILE["bg"][1] * grid
    return grid, y


@pytest.mark.skipif(not SYNTH_DIR.exists(), reason="SynthPattern 仓库不在")
@pytest.mark.parametrize("wa", [25.0, 50.0, 75.0])
def test_forward_mix_crosscheck(wa):
    """去除整体标度后（各自除以最大值）逐点相对偏差 RMS < 2%。"""
    bench_b.ensure_virtual_b()
    import numpy as _np
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / f"v{wa:g}_wide.xy")
    _grid, model = _model_curve(wa)
    assert len(pat.intensity) == len(model)
    a = pat.intensity / pat.intensity.max()
    b = model / model.max()
    rms = float(_np.sqrt(_np.mean((a - b) ** 2)))
    assert rms < 0.02, f"v{wa:g}: RMS={rms:.4f}"
