"""QA 集成端到端测试（tests/test_integration_e2e.py · QA 工程师独有交付）。

覆盖（对照 docs/PROJECT_PLAN.md §8 三级验证）：
1. A 法端到端: load_pattern -> measure_peak -> compute_ratio vs 黄金基线；
2. B 法端到端: parse_cif -> refine -> qpa/to_ratio vs virtual_b truth；
3. CLI 与黄金基线一致性（子进程调用 rutana.cli.rutana）；
4. 边界与异常路径（load_pattern 空文件/单列/非升序、纯背景测峰、
   calibrate_k 点数不足）。

注：黄金基线 method_a_roundtrip.json 由 tools/bench.py 基于窄窗谱
(v50.xy 等) 冻结；宽扫谱 (v50_wide.xy) 噪声实现不同，仅做合理性断言。
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import numpy as np
import pytest

from rutana.core.dtypes import Pattern
from rutana.core.method_a import CalibPoint, compute_ratio, calibrate_k
from rutana.core.peakmeasure import ANATASE_2TH, RUTILE_2TH, measure_peak
from rutana.core.patterns import load_pattern
from rutana.core.profile.cif import parse_cif
from rutana.core.profile.forward import ProfileParams
from rutana.core.refine.nonlinear import RefineConfig, refine
from rutana.core.refine.qpa import qpa_inputs_from_cif, qpa_weights, to_ratio

ROOT = Path(__file__).resolve().parent.parent
GOLDEN_A = ROOT / "tests" / "golden" / "method_a_roundtrip.json"
VIRTUAL = ROOT / "tests" / "data" / "virtual"
VIRTUAL_B = ROOT / "tests" / "data" / "virtual_b"
DATA_DIR = ROOT / "rutana" / "data"

K_GOLDEN = 2.8235463971


def _golden_a_wa(wa_nominal: float) -> float:
    rows = json.loads(GOLDEN_A.read_text(encoding="utf-8"))["rows"]
    for r in rows:
        if r["wa_nominal"] == wa_nominal:
            return float(r["wa_measured"])
    raise KeyError(wa_nominal)


# --------------------------------------------------------------------------- #
# R2.1 A 法端到端
# --------------------------------------------------------------------------- #
class TestMethodAE2E:
    """A 法: 读谱 -> 双分析线净峰高 -> K -> w_a，与黄金基线闭环。"""

    def test_narrow_v50_matches_golden(self):
        pat = load_pattern(VIRTUAL / "v50.xy")
        ma = measure_peak(pat, ANATASE_2TH)
        mr = measure_peak(pat, RUTILE_2TH)
        assert ma.ok and mr.ok
        # 峰位应落在标准分析线 ±0.05° 内
        assert abs(ma.two_theta_at_max - 25.30) <= 0.05
        assert abs(mr.two_theta_at_max - 27.44) <= 0.05
        res = compute_ratio(ma.net_height, mr.net_height, K_GOLDEN)
        golden = _golden_a_wa(50.0)
        assert res.wa == pytest.approx(golden, abs=1e-3)
        assert res.wr == pytest.approx(100.0 - golden, abs=1e-3)

    def test_wide_v50_is_sane(self):
        """宽扫谱噪声实现不同，只做 ±0.1pp 合理性断言（基线源自窄窗谱）。"""
        pat = load_pattern(VIRTUAL / "v50_wide.xy")
        ma = measure_peak(pat, ANATASE_2TH)
        mr = measure_peak(pat, RUTILE_2TH)
        assert ma.ok and mr.ok
        res = compute_ratio(ma.net_height, mr.net_height, K_GOLDEN)
        assert abs(res.wa - 50.0) <= 0.1


# --------------------------------------------------------------------------- #
# R2.2 B 法端到端
# --------------------------------------------------------------------------- #
class TestMethodBE2E:
    """B 法: parse_cif -> refine(默认 RefineConfig) -> QPA vs 50% truth。"""

    def test_v50_roundtrip(self):
        pat = load_pattern(VIRTUAL_B / "v50_wide.xy")
        st_a = parse_cif(DATA_DIR / "anatase.cif")
        st_r = parse_cif(DATA_DIR / "rutile.cif")
        za, va, ma_ = qpa_inputs_from_cif(st_a, "O2 Ti")
        zr, vr, mr_ = qpa_inputs_from_cif(st_r, "O2 Ti")
        assert (za, zr) == (4, 2)  # QPA 的 Z 前提（★酸检）
        res = refine([st_a, st_r], pat, ProfileParams(integrated=False), RefineConfig())
        assert res.ycalc.shape == pat.intensity.shape  # ycalc 与谱等长
        assert res.rf.rwp <= 10.0  # 标准硬条款
        ws = qpa_weights([(st_a.name, res.scales[0], za, va, ma_),
                          (st_r.name, res.scales[1], zr, vr, mr_)])
        wa, wr = to_ratio(ws, 0, 1)
        assert abs(wa - 50.0) <= 0.5
        assert abs(wr - 50.0) <= 0.5


# --------------------------------------------------------------------------- #
# R2.3 CLI 与黄金基线一致性
# --------------------------------------------------------------------------- #
class TestCliGolden:
    """python -m rutana.cli.rutana a-method 的 JSON 输出须与基线逐位一致。"""

    def test_cli_v50_json_vs_golden(self, tmp_path):
        out = tmp_path / "qa_a50.json"
        proc = subprocess.run(
            [sys.executable, "-m", "rutana.cli.rutana", "a-method",
             "--sample", str(VIRTUAL / "v50.xy"),
             "--K", str(K_GOLDEN), "--json", str(out)],
            capture_output=True, text=True, cwd=str(ROOT), timeout=120)
        assert proc.returncode == 0, proc.stderr
        assert out.exists()
        payload = json.loads(out.read_text(encoding="utf-8"))
        assert payload["method"] == "A"
        assert payload["wa"] == pytest.approx(_golden_a_wa(50.0), abs=1e-6)
        assert payload["peak_anatase"]["ok"] and payload["peak_rutile"]["ok"]


# --------------------------------------------------------------------------- #
# R8 边界与异常路径
# --------------------------------------------------------------------------- #
class TestEdgePaths:
    """load_pattern 异常输入 / 纯背景测峰 / calibrate_k 点数不足。"""

    def test_load_pattern_empty_file(self, tmp_path):
        f = tmp_path / "empty.xy"
        f.write_text("", encoding="utf-8")
        with pytest.raises(ValueError):
            load_pattern(f)

    def test_load_pattern_single_column(self, tmp_path):
        f = tmp_path / "one_col.xy"
        f.write_text("10.0\n10.02\n10.04\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_pattern(f)

    def test_load_pattern_comment_only(self, tmp_path):
        f = tmp_path / "comments.xy"
        f.write_text("# only a comment\n# another\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_pattern(f)

    def test_load_pattern_non_ascending(self, tmp_path):
        f = tmp_path / "desc.xy"
        f.write_text("25.0 100\n24.0 90\n23.0 80\n", encoding="utf-8")
        with pytest.raises(ValueError):
            load_pattern(f)

    def test_load_pattern_unsupported_ext(self, tmp_path):
        f = tmp_path / "x.foo"
        f.write_text("1 2\n3 4\n", encoding="utf-8")
        with pytest.raises(NotImplementedError):
            load_pattern(f)

    def test_measure_peak_pure_background_ok_false(self):
        """纯背景谱（无峰）应给出 ok=False 而非崩溃。"""
        tt = np.arange(24.5, 28.5, 0.02)
        yy = 300.0 + 4.0 * tt + np.random.default_rng(0).normal(
            0, 5.0, tt.size)
        pat = Pattern(two_theta=tt, intensity=yy, meta={})
        m = measure_peak(pat, ANATASE_2TH)
        assert not m.ok
        assert m.message  # 应带可读原因
        assert not (m.net_height > 0 and m.snr >= 4.0)

    def test_calibrate_k_needs_three_points(self):
        pts = [CalibPoint(0.25, 0.1), CalibPoint(1.0, 0.4)]
        with pytest.raises(ValueError):
            calibrate_k(pts)

    def test_compute_ratio_invalid_inputs(self):
        with pytest.raises(ValueError):
            compute_ratio(0.0, 10.0, 2.8)
        with pytest.raises(ValueError):
            compute_ratio(100.0, -1.0, 2.8)
        with pytest.raises(ValueError):
            compute_ratio(100.0, 10.0, 0.0)
