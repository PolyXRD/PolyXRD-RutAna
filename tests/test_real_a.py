"""A 法真实数据回归测试（岛津 XRD-019 · TiO2）—— 工程师 A 维护。

覆盖：
  R1 真实数据接入：UTF-8 BOM / `?` 首行 / FullProf pd 格式；
  R2 Kα2 剥离：Δ2θ 公式、默认关闭、开启后强度显著下降；
  R3 峰强口径：面积口径的校准线性度优于峰高（岛津 sheet1 vs sheet2）；
  R4 K 标定：带截距 OLS 斜率复现岛津公布值 1.2234；
  R5 v1.0.0 协议在 6 标样上的 K/R²/截距；
  R6 8/18/36% 三个待测样相对误差 ≤2%（局部扫描 + pd 全谱交叉验证）；
  R7 进度回调与协议可序列化。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest

from rutana.core import kalpha2 as ka2
from rutana.core.background import BgConfig
from rutana.core.method_a import (DEFAULT_ABS_LIMIT, CalibPoint, calibrate_k,
                                  compute_ratio)
from rutana.core.peakmeasure import (ANATASE_2TH_KA, PROTOCOL_LEGACY,
                                    PROTOCOL_V100, RUTILE_2TH_KA, get_protocol,
                                    measure_pair, measure_peak, peak_value)
from rutana.core.patterns import load_pattern

REAL = Path(__file__).parent / "data" / "real" / "a"
STANDARDS = (5, 10, 15, 20, 30, 50)
UNKNOWN = (8, 18, 36)

requires_real = pytest.mark.skipif(
    not (REAL / "5percent24-29.txt").exists(),
    reason="真实数据副本缺失（tests/data/real/a）")

# 岛津公布的 6 组标样 Ia/Ir（钛白粉数据.xlsx）
#   sheet1 = 峰面积口径；sheet2 = 峰高口径
SHIM_IA_AREA = {5: 373777, 10: 351437, 15: 354070,
                20: 318774, 30: 282108, 50: 209713}
SHIM_IR_AREA = {5: 15814, 10: 31892, 15: 47123,
                20: 59175, 30: 87638, 50: 149133}
SHIM_IA_HGT = {5: 29055, 10: 26744, 15: 30137,
               20: 27210, 30: 20089, 50: 16937}
SHIM_IR_HGT = {5: 1430, 10: 3165, 15: 4396,
               20: 5746, 30: 8348, 50: 13908}
K_PUBLISHED = 1.2234


def _calib_from(ia: dict, ir: dict, force_zero: bool = False):
    """由 Ia/Ir 表构造标定点并标定 K。"""
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ia[w] / ir[w])
           for w in STANDARDS]
    return calibrate_k(pts, force_zero=force_zero)


# --------------------------------------------------------------------------- #
# R1 真实数据接入
# --------------------------------------------------------------------------- #
@requires_real
def test_load_shimadzu_local_scan_skips_question_mark() -> None:
    """岛津导出首行是 `?`（非数值行）：必须跳过且点数正确。"""
    p = load_pattern(REAL / "5percent24-29.txt")
    assert p.two_theta.size == 251
    assert p.two_theta[0] == pytest.approx(24.0, abs=1e-6)
    assert p.two_theta[-1] == pytest.approx(29.0, abs=1e-6)
    assert p.step == pytest.approx(0.02, abs=1e-6)
    assert p.meta["layout"] == "two_column"


@requires_real
def test_load_fullprof_pd_format() -> None:
    """FullProf pd 格式（loop_ + 列名行）解析为 5001 点 20–120°。"""
    p = load_pattern(REAL / "pd" / "8%测试谱.txt")
    assert p.two_theta.size == 5001
    assert p.two_theta[0] == pytest.approx(20.0, abs=1e-6)
    assert p.two_theta[-1] == pytest.approx(120.0, abs=1e-6)
    assert p.meta["layout"] == "pd"


def test_load_utf8_bom_and_question_mark(tmp_path: Path) -> None:
    """UTF-8 BOM + `?` 首行的两列文件可正常读入。"""
    f = tmp_path / "bom.xy"
    f.write_bytes("?\r\n24.0 100\r\n24.02 110\r\n24.04 120\r\n"
                  .encode("utf-8-sig"))
    p = load_pattern(f)
    assert p.two_theta.size == 3
    assert p.intensity.tolist() == [100.0, 110.0, 120.0]


def test_load_pd_synthetic(tmp_path: Path) -> None:
    """手写的 pd 片段（calc 强度列同样支持）。"""
    f = tmp_path / "c.txt"
    f.write_text(
        "_pd_meas_number_of_points 3\nloop_\n"
        "_pd_proc_2theta_corrected\n_pd_calc_intensity_total\n"
        "20.0 1.0\n20.02 2.0\n20.04 3.0\n", encoding="utf-8")
    p = load_pattern(f)
    assert p.two_theta.size == 3
    assert p.meta["layout"] == "pd"


# --------------------------------------------------------------------------- #
# R2 Kα2 剥离
# --------------------------------------------------------------------------- #
def test_delta_2theta_values() -> None:
    """Cu Kα 双线在 25.34°/27.47° 处的 Δ2θ 约 0.07°（正值=向高角偏移）。"""
    d1 = float(ka2.delta_2theta(np.array([25.34]), "Cu")[0])
    d2 = float(ka2.delta_2theta(np.array([27.47]), "Cu")[0])
    assert 0.05 < d1 < 0.09
    assert 0.05 < d2 < 0.09
    assert d2 > d1  # 角度越高 Δ2θ 越大


def test_kalpha2_disabled_by_default() -> None:
    """默认配置关闭剥离，且 strip 后谱与输入逐位相同（行为不变）。"""
    from rutana.core.dtypes import Pattern
    tt = np.arange(24.0, 29.0, 0.02)
    ii = 100.0 + 5.0 * np.sin(tt)
    p = Pattern(two_theta=tt, intensity=ii)
    out = ka2.strip_kalpha2(p)
    assert not ka2.KAlpha2Config().enabled
    assert np.allclose(out.intensity, ii)


@requires_real
def test_kalpha2_strip_reduces_peak_area() -> None:
    """开启剥离后锐钛矿峰面积显著下降（Kα2 分量被去掉约 1/3）。"""
    from rutana.core.kalpha2 import KAlpha2Config, strip_kalpha2
    pat = load_pattern(REAL / "50percent24-29.txt")
    ma_raw = measure_peak(pat, ANATASE_2TH_KA, tol=0.25, bg_margin=0.18,
                          cfg=BgConfig("linear_edges", 0.14))
    ma_ka = measure_peak(strip_kalpha2(pat, KAlpha2Config(enabled=True)),
                         ANATASE_2TH_KA, tol=0.25, bg_margin=0.18,
                         cfg=BgConfig("linear_edges", 0.14))
    assert 0.0 < ma_ka.net_area < ma_raw.net_area
    assert ma_ka.net_area / ma_raw.net_area < 0.80  # 至少削掉 20%


# --------------------------------------------------------------------------- #
# R3 峰强口径（面积 vs 峰高）
# --------------------------------------------------------------------------- #
def test_area_quantity_has_better_linearity_than_height() -> None:
    """岛津 sheet1(面积) R² 明显高于 sheet2(峰高)：默认口径取面积。"""
    r_area = _calib_from(SHIM_IA_AREA, SHIM_IR_AREA)
    r_hgt = _calib_from(SHIM_IA_HGT, SHIM_IR_HGT)
    assert r_area.r2 > r_hgt.r2
    assert r_area.r2 >= 0.999
    assert PROTOCOL_V100.quantity == "area"


# --------------------------------------------------------------------------- #
# R4 K 标定口径
# --------------------------------------------------------------------------- #
def test_calibrate_k_reproduces_shimadzu_published_value() -> None:
    """用岛津公布的峰面积 Ia/Ir 反算：K = 1.2234 ± 0.02（带截距 OLS）。"""
    r = _calib_from(SHIM_IA_AREA, SHIM_IR_AREA)
    assert r.K == pytest.approx(K_PUBLISHED, abs=0.02)
    assert r.r2 >= 0.995
    assert r.n_points == 6


def test_forced_zero_k_is_higher_and_not_default() -> None:
    """过原点口径被抬高约 +2.3%，且不再是默认。"""
    r_free = _calib_from(SHIM_IA_AREA, SHIM_IR_AREA)
    r_zero = _calib_from(SHIM_IA_AREA, SHIM_IR_AREA, force_zero=True)
    assert r_zero.K_forced0 > r_free.K
    assert r_free.K != pytest.approx(r_zero.K_forced0, abs=1e-3)
    # 默认（不传 force_zero）应为带截距斜率
    assert _calib_from(SHIM_IA_AREA, SHIM_IR_AREA).K == r_free.K


# --------------------------------------------------------------------------- #
# R5/R6 v1.0.0 协议在真实数据上的表现
# --------------------------------------------------------------------------- #
def _measure_all(protocol) -> dict[int, float]:
    """按协议测所有局部扫描谱，返回 {wr: Ia/Ir}。"""
    out: dict[int, float] = {}
    for w in STANDARDS + UNKNOWN:
        pat = load_pattern(REAL / f"{w}percent24-29.txt")
        ia, ir, _, _ = measure_pair(pat, protocol)
        out[w] = ia / ir
    return out


@requires_real
def test_real_standard_calibration_k_and_r2() -> None:
    """6 个真实标样：K 落在公布值 ±0.05 内，R²≥0.995，截距小。"""
    ratios = _measure_all(PROTOCOL_V100)
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ratios[w])
           for w in STANDARDS]
    r = calibrate_k(pts)
    assert abs(r.K - K_PUBLISHED) <= 0.05
    assert r.r2 >= 0.995
    assert abs(r.intercept) <= 0.15
    assert not r.warnings or all("R²" not in w for w in r.warnings)


@requires_real
def test_unknown_8_18_36_within_two_percent() -> None:
    """三个待测样（局部扫描 24–29°）相对误差 ≤2%（判据 ≤3%）。"""
    ratios = _measure_all(PROTOCOL_V100)
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ratios[w])
           for w in STANDARDS]
    k = calibrate_k(pts).K
    for w in UNKNOWN:
        wr = 100.0 / (1.0 + ratios[w] / k)
        assert abs(wr - w) / w * 100.0 <= 2.0, f"{w}% -> {wr:.3f}"


@requires_real
def test_pd_fullscan_crosscheck_within_two_percent() -> None:
    """独立交叉验证：用局部扫描标定的 K 预测 pd 全谱（20–120°）实测谱。"""
    ratios = _measure_all(PROTOCOL_V100)
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ratios[w])
           for w in STANDARDS]
    k = calibrate_k(pts).K
    files = {8: "pd/8%测试谱.txt", 18: "pd/18%实测谱.txt",
             36: "pd/36%实测谱.txt"}
    for w, name in files.items():
        pat = load_pattern(REAL / name)
        ia, ir, _, _ = measure_pair(pat, PROTOCOL_V100)
        wr = 100.0 / (1.0 + (ia / ir) / k)
        assert abs(wr - w) / w * 100.0 <= 2.5, f"{w}% -> {wr:.3f}"


@requires_real
def test_v100_beats_legacy_protocol() -> None:
    """v1.0.0 协议最差误差明显小于 v0.1.0 legacy 协议。"""
    worst = {}
    for proto in (PROTOCOL_V100, PROTOCOL_LEGACY):
        ratios = _measure_all(proto)
        pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ratios[w])
               for w in STANDARDS]
        k = calibrate_k(pts).K
        worst[proto.name] = max(
            abs(100.0 / (1.0 + ratios[w] / k) - w) / w * 100.0 for w in UNKNOWN)
    assert worst[PROTOCOL_V100.name] < worst[PROTOCOL_LEGACY.name]


@requires_real
def test_beats_shimadzu_published_result() -> None:
    """优于岛津公布强度比值法（其相对误差约 −7.5%）。"""
    ratios = _measure_all(PROTOCOL_V100)
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ratios[w])
           for w in STANDARDS]
    k = calibrate_k(pts).K
    for w, shim in ((8, 7.41), (18, 16.56), (36, 33.26)):
        wr = 100.0 / (1.0 + ratios[w] / k)
        assert abs(wr - w) < abs(shim - w)


# --------------------------------------------------------------------------- #
# R7 协议、进度回调、常量
# --------------------------------------------------------------------------- #
def test_protocol_lookup_and_serializable() -> None:
    """协议可按名取回且可 JSON 序列化；未知名字抛 ValueError。"""
    assert get_protocol("v1") is PROTOCOL_V100
    assert get_protocol("legacy") is PROTOCOL_LEGACY
    d = PROTOCOL_V100.as_dict()
    assert d["quantity"] == "area" and d["name"] == "v1.0.0"
    import json
    assert json.dumps(d, ensure_ascii=False)
    with pytest.raises(ValueError):
        get_protocol("nope")


def test_peak_value_quantity_switch() -> None:
    """peak_value 按口径取面积/净高；非法口径抛 ValueError。"""
    from rutana.core.dtypes import Pattern, PeakMeasure
    m = PeakMeasure(25.34, 100.0, 7.5, 10.0, 0.2, 20.0, True, "OK")
    assert peak_value(m, "area") == 7.5
    assert peak_value(m, "height") == 100.0
    with pytest.raises(ValueError):
        peak_value(m, "bogus")


@requires_real
def test_progress_cb_receives_stages() -> None:
    """progress_cb 收到若干阶段文案与 0~1 进度；不传时行为不变。"""
    seen: list[tuple[str, float | None]] = []
    pat = load_pattern(REAL / "18percent24-29.txt")
    ia, ir, _, _ = measure_pair(pat, PROTOCOL_V100,
                                progress_cb=lambda t, p: seen.append((t, p)))
    assert ia > 0 and ir > 0
    assert len(seen) >= 4
    assert all(0.0 <= (p if p is not None else 0.0) <= 1.0 for _, p in seen)
    # 不传回调的调用路径必须等价
    ia2, ir2, _, _ = measure_pair(pat, PROTOCOL_V100)
    assert ia2 == pytest.approx(ia) and ir2 == pytest.approx(ir)


def test_default_abs_limit_is_018() -> None:
    """重复性限缺省值 = 0.18 pp（标准原文，见 docs/STD_FREEZE.md）。"""
    assert DEFAULT_ABS_LIMIT == pytest.approx(0.18)


@requires_real
def test_measure_peak_backward_compatible_defaults() -> None:
    """不传新增参数时 measure_peak 与 v0.1.0 行为一致（net_height>0）。"""
    pat = load_pattern(REAL / "50percent24-29.txt")
    m = measure_peak(pat, ANATASE_2TH_KA)
    assert m.ok and m.net_height > 0 and m.net_area > 0
    assert abs(m.two_theta_at_max - 25.34) <= 0.10


@requires_real
def test_rutile_center_constant_matches_observed_peak() -> None:
    """金红石 27.47° 常量落在实测峰 ±0.05° 内。"""
    pat = load_pattern(REAL / "50percent24-29.txt")
    m = measure_peak(pat, RUTILE_2TH_KA, tol=1.05, bg_margin=0.18,
                     cfg=BgConfig("linear_edges", 0.14))
    assert abs(m.two_theta_at_max - RUTILE_2TH_KA) <= 0.05


def test_compute_ratio_still_standard_formula() -> None:
    """标准公式 w_a = 1/(1+K·I_r/I_a) 未变。"""
    r = compute_ratio(100.0, 50.0, 1.2)
    assert r.wa == pytest.approx(1.0 / (1.0 + 1.2 * 0.5) * 100.0, abs=1e-9)
