"""A 法 round-trip 基准（T2.5）：虚拟样闭环，8 配比对照表。

流程：读 manifest -> 每个配比窄窗谱测两分析线净峰高 ->
用 25/50/75% 三个人造标定点标定 K -> 反算 w_a -> 与 truth 比对。

用法：
  python tools/bench.py --method a [--freeze]
  --freeze: （重新）冻结 golden 基线 tests/golden/method_a_roundtrip.json；
            缺省时若基线已存在则逐位比对，任何漂移都会以退出码 1 拦下。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rutana.core.method_a import CalibPoint, CalibResult, calibrate_k, \
    compute_ratio  # noqa: E402
from rutana.core.peakmeasure import ANATASE_2TH, RUTILE_2TH, \
    measure_peak  # noqa: E402
from rutana.core.patterns import load_pattern  # noqa: E402

VIRTUAL_DIR = ROOT / "tests/data/virtual"
GOLDEN = ROOT / "tests/golden/method_a_roundtrip.json"
REPORT_MD = ROOT / "bench_report.md"
CALIB_RATIOS = (25.0, 50.0, 75.0)  # 人造标定点配比
GOLDEN_TOL = 1e-6                  # 与冻结基线的一致性容差


def tolerance_pp(wa: float) -> float:
    """验收容差（百分点）：wa>=95 -> 0.30；其余 max(0.5, 2% 相对)。"""
    return 0.30 if wa >= 95.0 else max(0.5, 0.02 * wa)


def measure_all(vdir: Path, manifest: dict) -> dict:
    """对每个配比的窄窗谱测两分析线，返回 {wa_nominal: 测量结果}。"""
    out = {}
    for s in manifest["samples"]:
        pat = load_pattern(vdir / s["file"])
        ma = measure_peak(pat, ANATASE_2TH)
        mr = measure_peak(pat, RUTILE_2TH)
        out[s["wa_nominal"]] = {"ia": ma.net_height, "ir": mr.net_height,
                                "snr_a": ma.snr, "snr_r": mr.snr,
                                "pos_a": ma.two_theta_at_max,
                                "pos_r": mr.two_theta_at_max,
                                "ok": ma.ok and mr.ok}
    return out


def run_bench(vdir: Path) -> tuple[list[dict], CalibResult]:
    """跑全流程，返回 (逐配比结果行, 标定结果)。"""
    manifest = json.loads((vdir / "manifest.json").read_text(encoding="utf-8"))
    measured = measure_all(vdir, manifest)
    points = [CalibPoint(x / (100.0 - x),
                         measured[x]["ia"] / measured[x]["ir"])
              for x in CALIB_RATIOS]
    calib = calibrate_k(points)
    rows = []
    for s in manifest["samples"]:
        wa_n = s["wa_nominal"]
        d = measured[wa_n]
        ratio = compute_ratio(d["ia"], d["ir"], calib.K)
        delta = ratio.wa - wa_n
        tol = tolerance_pp(wa_n)
        limit_flag = (wa_n < 1.0 and not d["ok"])  # 仅 0.1% 允许检出限外标注
        within = abs(delta) <= tol or limit_flag
        rows.append({"wa_nominal": wa_n, "wa_measured": ratio.wa,
                     "delta": delta, "tol": tol,
                     "snr_a": d["snr_a"], "snr_r": d["snr_r"],
                     "ok": d["ok"], "limit_flag": limit_flag,
                     "within": within})
    return rows, calib


def render_table(rows: list[dict], calib: CalibResult) -> str:
    """渲染 Markdown 对照表。"""
    lines = [
        f"# A 法 round-trip 对照表（K={calib.K:.6f}, R2={calib.r2:.5f}, "
        f"n={calib.n_points}）", "",
        "| w_a 标称(%) | w_a 回复(%) | Δ(pp) | 容差(pp) | SNR_a | SNR_r | 判定 |",
        "|---:|---:|---:|---:|---:|---:|:--:|",
    ]
    for r in rows:
        verdict = "PASS" if r["within"] else "FAIL"
        if r["limit_flag"]:
            verdict += "(检出限外)"
        lines.append(
            f"| {r['wa_nominal']:.1f} | {r['wa_measured']:.3f} | "
            f"{r['delta']:+.3f} | {r['tol']:.2f} | {r['snr_a']:.1f} | "
            f"{r['snr_r']:.1f} | {verdict} |")
    return "\n".join(lines) + "\n"


def check_golden(rows: list[dict], calib: CalibResult, freeze: bool) -> int:
    """冻结或比对 golden 基线，返回退出码。"""
    payload = {"K": calib.K, "intercept": calib.intercept, "r2": calib.r2,
               "n_points": calib.n_points,
               "rows": [{"wa_nominal": r["wa_nominal"],
                         "wa_measured": r["wa_measured"],
                         "delta": r["delta"]} for r in rows]}
    if freeze or not GOLDEN.exists():
        GOLDEN.parent.mkdir(parents=True, exist_ok=True)
        GOLDEN.write_text(json.dumps(payload, ensure_ascii=False, indent=2)
                          + "\n", encoding="utf-8")
        print(f"[golden] 基线已冻结 -> {GOLDEN}")
        return 0
    old = json.loads(GOLDEN.read_text(encoding="utf-8"))
    for new, base in zip(payload["rows"], old["rows"]):
        if abs(new["wa_measured"] - base["wa_measured"]) > GOLDEN_TOL:
            print(f"[golden] 漂移超限: wa={new['wa_nominal']}% "
                  f"{base['wa_measured']:.6f} -> {new['wa_measured']:.6f}")
            return 1
    print("[golden] 与冻结基线逐位一致")
    return 0


def main(argv: list[str] | None = None) -> int:
    """bench 主入口。"""
    ap = argparse.ArgumentParser(description="PolyXRD-RutAna round-trip 基准")
    ap.add_argument("--method", default="a", choices=["a", "b"],
                    help="a=A 法（本卡）；b 留待 P4")
    ap.add_argument("--freeze", action="store_true", help="重新冻结 golden")
    ap.add_argument("--virtual-dir", default=str(VIRTUAL_DIR))
    args = ap.parse_args(argv)
    if args.method == "b":
        print("B 法 bench 尚未实现（P4 阶段 T4.6 开卡）")
        return 2
    rows, calib = run_bench(Path(args.virtual_dir))
    table = render_table(rows, calib)
    print(table)
    REPORT_MD.write_text(table, encoding="utf-8")
    n_pass = sum(1 for r in rows if r["within"])
    print(f"[bench] {n_pass}/{len(rows)} 配比达标")
    code = 0 if n_pass == len(rows) else 1
    return code or check_golden(rows, calib, args.freeze)


if __name__ == "__main__":
    sys.exit(main())
