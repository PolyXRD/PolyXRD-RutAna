"""B 法真实数据回归测试（v1.0.0）—— 岛津 XRD-019 数据集抽样。

完整四样验证见 tools/verify_realdata_b.py（结果冻结在
tests/golden/method_b_realdata.json）。此处抽两个端元样品做轻量回归：
- 8% pd 全谱（低配比端，最难）
- 36% pd 全谱（中段）
判据与验收一致：Rwp ≤ 10%（GB/T 30793 B 法硬条款）、金红石回收
|相对误差| ≤ 3%。
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from verify_realdata_b import M_TIO2, load_any  # noqa: E402

from rutana.core.profile.cif import parse_cif  # noqa: E402
from rutana.core.refine.nonlinear import refine  # noqa: E402
from rutana.core.refine.qpa import qpa_weights, to_ratio  # noqa: E402
from rutana.core.refine.realdata import real_config, real_params  # noqa: E402

REAL = ROOT / "tests" / "data" / "real"

_CASES = [
    ("pd/8%测试谱.txt", 8.0),
    ("pd/36%实测谱.txt", 36.0),
]


@pytest.fixture(scope="module")
def _structs():
    return (parse_cif(ROOT / "rutana" / "data" / "anatase.cif"),
            parse_cif(ROOT / "rutana" / "data" / "rutile.cif"))


@pytest.mark.parametrize("rel,truth", _CASES)
def test_realdata_b_sample(_structs, rel, truth):
    st_a, st_r = _structs
    pat = load_any(REAL / rel)
    res = refine([st_a, st_r], pat, real_params(), real_config())
    (fa_a, fc_a), (fa_r, fc_r) = res.cell_scales
    va = (st_a.cell[0] * fa_a) ** 2 * (st_a.cell[2] * fc_a)
    vr = (st_r.cell[0] * fa_r) ** 2 * (st_r.cell[2] * fc_r)
    ws = qpa_weights([(st_a.name, float(res.scales[0]), 4, va, M_TIO2),
                      (st_r.name, float(res.scales[1]), 2, vr, M_TIO2)])
    _wa, wr = to_ratio(ws, 0, 1)
    err_rel = 100.0 * (wr - truth) / truth
    # GB/T 30793 B 法：Rwp ≤ 10%
    assert res.rf.rwp <= 10.0, f"{rel}: Rwp={res.rf.rwp:.2f}%"
    # 定量回收（v1.0.0 实证最差 +2.62%，判据 ≤3%）
    assert abs(err_rel) <= 3.0, f"{rel}: wr={wr:.2f}% ({err_rel:+.2f}%rel)"


def test_run_method_b_returns_two_phase_quantities():
    """v1.1.0：GUI services.run_method_b 应返回内置两相定量 wa/wr。

    18% pd 全谱真跑一次，对照冻结基线 tests/golden/method_b_realdata.json
    （wr = 18.106）；容差 ±0.5pp 覆盖精修的微小数值抖动。
    """
    from rutana.gui import services

    pat = load_any(REAL / "pd/18%实测谱.txt")
    out = services.run_method_b(pat)
    wa, wr = out["wa"], out["wr"]
    assert wa is not None and wr is not None, "内置两相定量不应降级为 None"
    assert wr == pytest.approx(18.106, abs=0.5)
    assert wa + wr == pytest.approx(100.0, abs=0.01), "两相应归一到 100%"
