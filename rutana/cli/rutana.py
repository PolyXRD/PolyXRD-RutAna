"""rutana 命令行入口（T2.6）。

用法：
  python -m rutana.cli.rutana a-method --sample S.xy (--K 1.0 |
      --calib c1.xy:0.25 c2.xy:1.0 c3.xy:4.0) [--repeat S2.xy]
      [--json out.json] [--png out.png] [--smooth-window 0]

--K 与 --calib 互斥且必须给其一；--calib 的标定 xy 必须同时含两条分析线。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from rutana.core.background import BgConfig
from rutana.core.dtypes import Pattern, PeakMeasure
from rutana.core.method_a import (DEFAULT_ABS_LIMIT, CalibPoint, CalibResult,
                                  calibrate_k, combine_duplicates,
                                  compute_ratio)
from rutana.core.peakmeasure import (ANATASE_2TH, RUTILE_2TH, measure_peak)
from rutana.core.patterns import load_pattern
from rutana.core.plot import plot_overlay
from rutana.core.smooth import SmoothConfig
from rutana.version import APP_NAME, __version__


def build_parser() -> argparse.ArgumentParser:
    """构造 a-method 子命令的 argparse 解析器。"""
    parser = argparse.ArgumentParser(
        prog="rutana",
        description=f"{APP_NAME} v{__version__} · "
                    "GB/T 30793—2014 锐钛型/金红石型比率测定")
    sub = parser.add_subparsers(dest="command", required=True)
    pa = sub.add_parser("a-method", help="A 法：强度比值法")
    pa.add_argument("--sample", required=True, help="样品谱图 (.xy 等)")
    pa.add_argument("--K", type=float, default=None,
                    help="已知 K 值（与 --calib 互斥）")
    pa.add_argument("--calib", nargs="+", default=None, metavar="XY:RATIO",
                    help="标定文件:质量比，至少 3 个，如 c1.xy:0.25 c2.xy:1.0")
    pa.add_argument("--repeat", default=None, help="第二次平行测定谱图")
    pa.add_argument("--json", dest="json_out", default=None,
                    help="工程存档 JSON 输出路径")
    pa.add_argument("--png", default=None, help="谱图 PNG 输出路径")
    pa.add_argument("--smooth-window", type=int, default=0,
                    help="SG 平滑窗口（0=关闭，默认；标定与样品须同参）")
    return parser


def measure_pair(pat: Pattern, smooth: SmoothConfig
                 ) -> tuple[float, float, PeakMeasure, PeakMeasure]:
    """测量一条谱上的锐钛型/金红石型分析线净峰高，返回 (ia, ir, ma, mr)。"""
    ma = measure_peak(pat, ANATASE_2TH, cfg=BgConfig(), smooth=smooth)
    mr = measure_peak(pat, RUTILE_2TH, cfg=BgConfig(), smooth=smooth)
    return ma.net_height, mr.net_height, ma, mr


def _parse_calib(specs: list[str], smooth: SmoothConfig
                 ) -> tuple[list[CalibPoint], CalibResult]:
    """解析 --calib 的 path:ratio 列表，逐一测峰并做 K 标定。"""
    points: list[CalibPoint] = []
    for spec in specs:
        if ":" not in spec:
            raise ValueError(f"--calib 参数格式应为 路径:质量比，收到: {spec}")
        path, ratio = spec.rsplit(":", 1)
        pat = load_pattern(path)
        ia, ir, _, _ = measure_pair(pat, smooth)
        points.append(CalibPoint(ma_over_mr=float(ratio),
                                 ia_over_ir=ia / ir))
    return points, calibrate_k(points)


def _print_report(sample: str, ma: PeakMeasure, mr: PeakMeasure,
                  calib: CalibResult, r, dup: dict | None) -> None:
    """输出人类可读的测定报告。"""
    print(f"== {APP_NAME} · A 法（GB/T 30793—2014 强度比值法）==")
    print(f"样品            : {sample}")
    print(f"锐钛型 {ANATASE_2TH:.2f}°  : I_a={ma.net_height:.1f}  "
          f"SNR={ma.snr:.1f}  {'OK' if ma.ok else ma.message}")
    print(f"金红石 {RUTILE_2TH:.2f}°  : I_r={mr.net_height:.1f}  "
          f"SNR={mr.snr:.1f}  {'OK' if mr.ok else mr.message}")
    print(f"K = {calib.K:.6f}   (n={calib.n_points}, "
          f"R2={calib.r2:.5f}"
          + ("" if calib.r2 >= 0.995 else "  ⚠ R2 < 0.995 请复核标定") + ")")
    print(f"w_a = {r.wa:.2f} %    w_r = {r.wr:.2f} %")
    if dup is not None:
        verdict = "合格" if dup["within_limit"] else "超差"
        print(f"双平行: 均值 {dup['wa_mean']:.2f} %, "
              f"|Δ| = {dup['abs_diff']:.2f} pp "
              f"(限 {dup['limit']:.2f}) → {verdict}")


def _write_json(path: str, payload: dict) -> None:
    """写工程存档 JSON（含全部方法参数，保证可复现）。"""
    Path(path).write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")


def run_a_method(args: argparse.Namespace) -> int:
    """执行 a-method 子命令，返回进程退出码。"""
    smooth = SmoothConfig(enabled=args.smooth_window > 0,
                          window=max(args.smooth_window, 5))
    sample = load_pattern(args.sample)
    ia, ir, ma, mr = measure_pair(sample, smooth)
    calib = CalibResult(K=1.0, intercept=0.0, r2=1.0, n_points=0, K_forced0=0.0)
    if args.K is not None:
        calib = CalibResult(K=float(args.K), intercept=0.0, r2=1.0,
                            n_points=0, K_forced0=float(args.K))
    elif args.calib:
        points, calib = _parse_calib(args.calib, smooth)
    else:
        raise SystemExit("错误：--K 与 --calib 必须提供其一")
    result = compute_ratio(ia, ir, calib.K)
    dup = None
    if args.repeat:
        pat2 = load_pattern(args.repeat)
        ia2, ir2, _, _ = measure_pair(pat2, smooth)
        dup = combine_duplicates(result, compute_ratio(ia2, ir2, calib.K))
    _print_report(args.sample, ma, mr, calib, result, dup)
    if args.png:
        plot_overlay([(f"样品 {Path(args.sample).name}", sample)],
                     f"A 法谱图 · w_a={result.wa:.2f}%", args.png)
    if args.json_out:
        payload = {
            "method": "A", "app": APP_NAME, "version": __version__,
            "sample": str(args.sample),
            "wa": result.wa, "wr": result.wr, "K": calib.K,
            "ia": result.ia, "ir": result.ir,
            "ia_over_ir": result.ia / result.ir,
            "peak_anatase": {"two_theta": ma.two_theta_at_max,
                             "snr": ma.snr, "ok": ma.ok,
                             "message": ma.message},
            "peak_rutile": {"two_theta": mr.two_theta_at_max,
                            "snr": mr.snr, "ok": mr.ok,
                            "message": mr.message},
            "calibration": {"n_points": calib.n_points,
                            "intercept": calib.intercept,
                            "r2": calib.r2,
                            "K_forced0": calib.K_forced0},
            "duplicates": dup,
            "smooth": {"enabled": smooth.enabled, "window": smooth.window,
                       "polyorder": smooth.polyorder},
            "bg_config": {"mode": BgConfig().mode,
                          "edge_frac": BgConfig().edge_frac,
                          "poly_deg": BgConfig().poly_deg},
        }
        _write_json(args.json_out, payload)
        print(f"JSON 已写入: {args.json_out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "a-method":
        if (args.K is None) == (args.calib is None):
            parser.error("--K 与 --calib 互斥且必须提供其一")
        return run_a_method(args)
    parser.error(f"未知子命令: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
