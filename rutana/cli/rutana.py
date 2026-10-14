"""rutana 命令行入口（T2.6 / v1.0.0）。

用法：
  python -m rutana.cli.rutana a-method --sample S.xy (--K 1.0 |
      --calib c1.xy:0.25 c2.xy:1.0 c3.xy:4.0 | --calib-wr c1.xy:50 ...)
      [--repeat S2.xy] [--protocol legacy|v1] [--quantity area|height]
      [--kalpha2] [--smooth-window 0] [--json out.json] [--png out.png]
      [--progress]

--K 与 --calib/--calib-wr 互斥且必须给其一；标定谱必须同时含两条分析线。

v1.0.0 新增：
* ``--protocol v1``：启用真实数据优化的 v1.0.0 测峰协议（净峰面积、
  Cu Kα 复合峰重心 25.34/27.47°、锐钛 ±0.25° / 金红石 ±1.05° 积分窗、
  背景边缘 +0.18°、linear_edges edge_frac=0.14、不平滑、不剥离 Kα2）。
  默认仍为 ``legacy``（v0.1.0 峰高口径），以兼容 tests/golden 黄金基线。
* ``--quantity``/``--kalpha2``/``--bg-*``：协议细项覆盖（写入 JSON 存档）。
* ``--progress``：把阶段进度打到 stderr。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Callable

from rutana.core.background import BgConfig
from rutana.core.dtypes import PeakMeasure
from rutana.core.kalpha2 import KAlpha2Config
from rutana.core.method_a import (DEFAULT_ABS_LIMIT, CalibPoint, CalibResult,
                                  calibrate_k, combine_duplicates,
                                  compute_ratio, invert_ratio)
from rutana.core.peakmeasure import APeakProtocol, get_protocol, measure_pair
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
    pa.add_argument("--sample", required=True, help="样品谱图 (.xy/.txt/.dat/.csv)")
    pa.add_argument("--K", type=float, default=None,
                    help="已知 K 值（与 --calib 互斥）")
    pa.add_argument("--calib", nargs="+", default=None, metavar="XY:RATIO",
                    help="标定文件:质量比 ma/mr，至少 3 个，如 c1.xy:0.25")
    pa.add_argument("--calib-wr", nargs="+", default=None, metavar="XY:WR",
                    help="标定文件:金红石质量分数%%，如 c1.xy:50（v1.0.0 新增）")
    pa.add_argument("--repeat", default=None, help="第二次平行测定谱图")
    pa.add_argument("--protocol", default="legacy", choices=("legacy", "v1"),
                    help="测峰协议：legacy=v0.1.0 峰高口径(默认，兼容黄金基线)；"
                         "v1=v1.0.0 真实数据优化协议(净峰面积)")
    pa.add_argument("--quantity", default=None, choices=("area", "height"),
                    help="覆盖协议的峰强口径")
    pa.add_argument("--kalpha2", action="store_true",
                    help="开启 Rachinger Kα2 剥离（默认关闭）")
    pa.add_argument("--smooth-window", type=int, default=None,
                    help="SG 平滑窗口（0/缺省=跟随协议；标定与样品须同参）")
    pa.add_argument("--bg-margin", type=float, default=None,
                    help="背景边缘外扩量（度），覆盖协议值")
    pa.add_argument("--bg-edge-frac", type=float, default=None,
                    help="背景边缘点比例，覆盖协议值")
    pa.add_argument("--bg-mode", default=None,
                    choices=("linear_edges", "poly", "chebyshev"),
                    help="背景模型，覆盖协议值")
    pa.add_argument("--bg-deg", type=int, default=None,
                    help="背景多项式阶数（poly/chebyshev 模式），覆盖协议值")
    pa.add_argument("--use-intercept", action="store_true",
                    help="反算时扣除校准截距（仅在截距显著不为 0 时使用）")
    pa.add_argument("--json", dest="json_out", default=None,
                    help="工程存档 JSON 输出路径")
    pa.add_argument("--png", default=None, help="谱图 PNG 输出路径")
    pa.add_argument("--progress", action="store_true",
                    help="把阶段进度打到 stderr")
    return parser


def make_protocol(args: argparse.Namespace) -> APeakProtocol:
    """按命令行参数构造测峰协议（未指定的项沿用协议默认值）。"""
    base = get_protocol(args.protocol)
    quantity = args.quantity or base.quantity
    window = base.smooth.window
    enabled = base.smooth.enabled
    if args.smooth_window is not None:
        enabled = args.smooth_window > 0
        window = max(args.smooth_window, 5)
    ka2 = KAlpha2Config(enabled=bool(args.kalpha2) or base.kalpha2.enabled,
                        ratio=base.kalpha2.ratio, anode=base.kalpha2.anode,
                        iters=base.kalpha2.iters)
    return APeakProtocol(
        name=base.name,
        anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th,
        anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win,
        bg_margin=base.bg_margin if args.bg_margin is None else args.bg_margin,
        bg=BgConfig(mode=args.bg_mode or base.bg.mode,
                    edge_frac=base.bg.edge_frac if args.bg_edge_frac is None
                    else args.bg_edge_frac,
                    poly_deg=base.bg.poly_deg if args.bg_deg is None
                    else args.bg_deg),
        smooth=SmoothConfig(enabled=enabled, window=window,
                            polyorder=base.smooth.polyorder),
        kalpha2=ka2, quantity=quantity)


def make_progress_cb(enabled: bool) -> Callable[[str, float | None], None] | None:
    """构造进度回调（--progress 时打到 stderr，否则返回 None 保持静默）。"""
    if not enabled:
        return None

    def _cb(text: str, pct: float | None) -> None:
        tail = "" if pct is None else f" {pct * 100:.0f}%"
        print(f"[rutana] {text}{tail}", file=sys.stderr)

    return _cb


def _emit(cb: Callable[[str, float | None], None] | None, text: str,
          pct: float | None) -> None:
    """安全推送一条进度。"""
    if cb is not None:
        cb(text, pct)


def _parse_calib(specs: list[str], protocol: APeakProtocol,
                 mass_ratio: bool,
                 progress_cb: Callable[[str, float | None], None] | None = None
                 ) -> tuple[list[CalibPoint], CalibResult]:
    """解析标定参数列表，逐一测峰并做 K 标定。

    mass_ratio=True  : 参数形如 路径:ma/mr；
    mass_ratio=False : 参数形如 路径:金红石质量分数%（内部换算成 ma/mr）。
    """
    points: list[CalibPoint] = []
    total = len(specs)
    for idx, spec in enumerate(specs, start=1):
        if ":" not in spec:
            raise ValueError(f"标定参数格式应为 路径:数值，收到: {spec}")
        path, value = spec.rsplit(":", 1)
        _emit(progress_cb, f"正在读取标定谱 {idx}/{total}",
              (idx - 1) / max(1, total))
        pat = load_pattern(path)
        ia, ir, _, _ = measure_pair(pat, protocol)
        if ir <= 0:
            raise ValueError(f"标定谱 {path} 的金红石型峰强非正（{ir:.3f}）")
        v = float(value)
        ratio = v if mass_ratio else (100.0 - v) / v
        if ratio <= 0:
            raise ValueError(f"标定谱 {path} 的质量比必须为正，收到 {spec}")
        points.append(CalibPoint(ma_over_mr=ratio, ia_over_ir=ia / ir))
    return points, calibrate_k(points)


def _print_report(sample: str, ma: PeakMeasure, mr: PeakMeasure,
                  calib: CalibResult, r, dup: dict | None,
                  protocol: APeakProtocol) -> None:
    """输出人类可读的测定报告。"""
    print(f"== {APP_NAME} · A 法（GB/T 30793—2014 强度比值法）==")
    print(f"样品            : {sample}")
    print(f"测峰协议        : {protocol.name}（口径={protocol.quantity}）")
    print(f"锐钛型 {protocol.anatase_2th:.2f}°  : I_a={ma.net_area:.1f}(面积) "
          f"{ma.net_height:.1f}(净高)  SNR={ma.snr:.1f}  "
          f"{'OK' if ma.ok else ma.message}")
    print(f"金红石 {protocol.rutile_2th:.2f}°  : I_r={mr.net_area:.1f}(面积) "
          f"{mr.net_height:.1f}(净高)  SNR={mr.snr:.1f}  "
          f"{'OK' if mr.ok else mr.message}")
    print(f"K = {calib.K:.6f}   (n={calib.n_points}, R2={calib.r2:.5f}, "
          f"截距={calib.intercept:+.4f}, K_过原点={calib.K_forced0:.6f})")
    for w in calib.warnings:
        print(f"  ⚠ {w}")
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
    protocol = make_protocol(args)
    progress_cb = make_progress_cb(bool(args.progress))
    _emit(progress_cb, "正在读取谱图", 0.0)
    sample = load_pattern(args.sample)
    ia, ir, ma, mr = measure_pair(sample, protocol, progress_cb=progress_cb)
    calib = CalibResult(K=1.0, intercept=0.0, r2=1.0, n_points=0, K_forced0=0.0)
    points: list[CalibPoint] = []
    if args.K is not None:
        calib = CalibResult(K=float(args.K), intercept=0.0, r2=1.0,
                            n_points=0, K_forced0=float(args.K))
    elif args.calib or args.calib_wr:
        specs = args.calib if args.calib else args.calib_wr
        points, calib = _parse_calib(specs, protocol,
                                     mass_ratio=bool(args.calib),
                                     progress_cb=progress_cb)
    else:
        raise SystemExit("错误：--K 与 --calib/--calib-wr 必须提供其一")
    _emit(progress_cb, "正在计算比率", 0.95)
    if args.use_intercept:
        result = invert_ratio(ia / ir, calib, use_intercept=True)
    else:
        result = compute_ratio(ia, ir, calib.K)
    dup = None
    if args.repeat:
        pat2 = load_pattern(args.repeat)
        ia2, ir2, _, _ = measure_pair(pat2, protocol, progress_cb=progress_cb)
        if args.use_intercept:
            result2 = invert_ratio(ia2 / ir2, calib, use_intercept=True)
        else:
            result2 = compute_ratio(ia2, ir2, calib.K)
        dup = combine_duplicates(result, result2)
    _emit(progress_cb, "完成", 1.0)
    _print_report(args.sample, ma, mr, calib, result, dup, protocol)
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
                             "net_area": ma.net_area,
                             "net_height": ma.net_height,
                             "snr": ma.snr, "ok": ma.ok,
                             "message": ma.message},
            "peak_rutile": {"two_theta": mr.two_theta_at_max,
                            "net_area": mr.net_area,
                            "net_height": mr.net_height,
                            "snr": mr.snr, "ok": mr.ok,
                            "message": mr.message},
            "calibration": {"n_points": calib.n_points,
                            "intercept": calib.intercept,
                            "r2": calib.r2,
                            "K_forced0": calib.K_forced0,
                            "r2_ok": calib.r2_ok,
                            "warnings": calib.warnings,
                            "use_intercept": bool(args.use_intercept),
                            "points": [{"ma_over_mr": p.ma_over_mr,
                                        "ia_over_ir": p.ia_over_ir}
                                       for p in points]},
            "duplicates": dup,
            "protocol": protocol.as_dict(),
            "abs_limit": DEFAULT_ABS_LIMIT,
        }
        _write_json(args.json_out, payload)
        print(f"JSON 已写入: {args.json_out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI 主入口。"""
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "a-method":
        given = [args.K is not None, bool(args.calib), bool(args.calib_wr)]
        if sum(1 for g in given if g) != 1:
            parser.error("--K / --calib / --calib-wr 三者互斥且必须提供其一")
        return run_a_method(args)
    parser.error(f"未知子命令: {args.command}")
    return 2


if __name__ == "__main__":
    sys.exit(main())
