"""P2-1（QA 测试补强）· 重启路径直接单元测试。

目标：直接断言"重启触发 → 重启后被采纳"，以及"正常路径不误触发"。
- 用例 1: v75 宽扫谱 + 缺省起点 —— 首轮 LM 已知会掉进 U=V=0 角点陷阱
  （首轮 Rwp≈14% > 10% 触发条件），重启链应被调用并采纳更优解（Rwp≈2.9%）。
  该案例即 docs/CIF_SOURCE.md §4.3 记录的 corner-trap 回归场景。
- 用例 2: v50 宽扫谱 + 缺省起点 —— 首轮即收敛（Rwp≈2.2%），断言
  restarted=False（不误触发、不拖慢正常路径）。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

import bench_b  # noqa: E402

from rutana.core.profile.forward import ProfileParams  # noqa: E402
from rutana.core.refine.nonlinear import RefineConfig, refine  # noqa: E402


def _refine_on(ratio: float):
    bench_b.ensure_virtual_b()
    st_a, st_r = bench_b.load_builtin_structs()
    pat = bench_b._load_pattern(bench_b.VIRTUAL_B / f"v{ratio:g}_wide.xy")
    cfg = RefineConfig(refine_zero=True, refine_uvw=True, refine_eta=False,
                       n_bg=3, max_iter=40)
    return refine([st_a, st_r], pat, ProfileParams(), cfg)


@pytest.fixture(scope="module")
def v75_result():
    """v75: 已知首轮掉角点陷阱 -> 必然触发重启链。"""
    return _refine_on(75.0)


def test_restart_triggered_and_adopted(v75_result):
    """重启链被调用（restarted=True），且最终结果优于触发阈值。"""
    res = v75_result
    assert res.restarted is True
    assert res.success is True
    assert res.rf.rwp <= 10.0
    # 重启应显著优于首轮角点陷阱解（首轮 Rwp≈14%，采纳后 ≈2.9%）
    assert res.rf.rwp < 10.0
    # history 同时包含首轮与重启链的评估记录
    assert len(res.history) > 40


def test_restart_lands_in_global_basin(v75_result):
    """采纳的重启解应恢复真值参数（U≈0.02, W≈0.02, zero≈0.03）。"""
    prm = v75_result.params
    assert abs(prm.zero - 0.03) < 0.02
    assert abs(prm.U - 0.02) < 0.01
    assert abs(prm.W - 0.02) < 0.01


def test_no_restart_on_normal_start():
    """正常起点首轮即收敛 -> restarted=False（不误触发）。"""
    res = _refine_on(50.0)
    assert res.restarted is False
    assert res.success is True
    assert res.rf.rwp <= 10.0
