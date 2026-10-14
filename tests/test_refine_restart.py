"""P2-1（QA 测试补强）· 重启路径直接单元测试（v1.0.0 语义修正版）。

历史背景：v0.1.0 时代 v75 宽扫谱 + 缺省起点会让首轮 LM 掉进 U=V=0 角点陷阱
（首轮 Rwp≈14% > 10% 触发重启，采纳后 Rwp≈2.9%）。v1.0.0 修正 Caglioti 语义
（tanθ 而非 tan 2θ，见 rutana/core/profile/forward.py::caglioti_2theta）后，
陷阱根因消除：LM 从任何起点都能收敛到全局盆地，重启链不再被触发。

本文件相应改为双向断言：
- 正向回归：正常谱上不误触发重启（陷阱不复发的回归护栏），参数精确复原；
- 保险机制：构造 LM 必然失败的纯噪声谱，验证重启链仍会被触发并返回结果。
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from dataclasses import replace

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bench_b  # noqa: E402

from rutana.core.dtypes import Pattern  # noqa: E402
from rutana.core.profile.forward import ProfileParams  # noqa: E402
from rutana.core.refine.nonlinear import RefineConfig, refine  # noqa: E402


def _cfg() -> RefineConfig:
    return RefineConfig(refine_zero=True, refine_uvw=True, refine_eta=False,
                        n_bg=3, max_iter=40, tmin=5.0, tmax=90.0)


def _refine_on(ratio: float):
    bench_b.ensure_virtual_b()
    st_a, st_r = bench_b.load_builtin_structs()
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / f"v{ratio:g}_wide.xy")
    return refine([st_a, st_r], pat, ProfileParams(integrated=False), _cfg())


# ---------- 正向回归：正常起点不误触发（旧角点陷阱不复发的护栏） ----------

@pytest.mark.parametrize("ratio", [50.0, 75.0])
def test_no_restart_on_normal_start(ratio):
    """v1.0.0 语义修正后，缺省起点首轮即收敛 -> restarted=False。"""
    res = _refine_on(ratio)
    assert res.restarted is False
    assert res.success is True
    assert res.rf.rwp <= 10.0


def test_params_recovered_without_restart():
    """不触发重启时也应恢复真值参数（U≈0.02, W≈0.02, zero≈0.03）。"""
    prm = _refine_on(75.0).params
    assert abs(prm.zero - 0.03) < 0.02
    assert abs(prm.U - 0.02) < 0.01
    assert abs(prm.W - 0.02) < 0.01


# ---------- 保险机制：LM 失败时重启链被触发 ----------

def test_restart_fires_when_lm_fails():
    """纯噪声谱上首轮 LM 失败 -> 触发重启链（保险机制仍有效）。"""
    bench_b.ensure_virtual_b()
    st_a, st_r = bench_b.load_builtin_structs()
    rng = np.random.default_rng(7)
    grid = np.arange(5.0, 90.0, 0.02)
    pat = Pattern(two_theta=grid, intensity=rng.poisson(100.0, grid.size),
                  meta={})
    cfg = replace(_cfg(), max_iter=15)  # 噪声上小迭代预算，确保首轮失败
    res = refine([st_a, st_r], pat,
                 ProfileParams(anode="Cu", integrated=False), cfg)
    assert res.restarted is True
    # 重启链跑完后仍能返回合法结果
    assert res.rf.rwp > 0.0
    assert len(res.history) > 40
