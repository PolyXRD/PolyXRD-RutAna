"""A 法真实数据验证脚本（v1.0.0）—— 只用 A 法部分。

数据源：岛津应用数据集 XRD-019（TiO2），副本位于 tests/data/real/a/
（9 个局部扫描 24–29° + 50% 全谱 20–120° + 3 个 FullProf pd 全谱实测谱）。

流程：
  1) 用 6 个标样（金红石 5/10/15/20/30/50%）按 v1.0.0 协议测峰并标定 K；
  2) 逐个输出 9 个真实谱的 Markdown 结果表（真值 / 实测 wa / 实测 wr / 相对误差）；
  3) 追加「独立交叉验证」：用局部扫描标定的 K，去预测 8/18/36% 的
     FullProf pd 全谱实测谱（20–120°，不同扫描范围与强度标度）；
  4) 与岛津公布结果（强度比值法 8→7.41、18→16.56、36→33.26）对比；
  5) 判据：8/18/36% 三个待测样相对误差 ≤3%（力求 ≤2%）。

用法：
  D:/Project/XRD/python310/python.exe tools/verify_realdata.py
  D:/Project/XRD/python310/python.exe tools/verify_realdata.py --markdown out.md
  D:/Project/XRD/python310/python.exe tools/verify_realdata.py --compare-height \
      --compare-kalpha2 --compare-smooth
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from rutana.core.background import BgConfig  # noqa: E402
from rutana.core.kalpha2 import KAlpha2Config  # noqa: E402
from rutana.core.method_a import CalibPoint, calibrate_k  # noqa: E402
from rutana.core.peakmeasure import (APeakProtocol, PROTOCOL_LEGACY,  # noqa: E402
                                     PROTOCOL_V100, measure_pair)
from rutana.core.patterns import load_pattern  # noqa: E402
from rutana.core.smooth import SmoothConfig  # noqa: E402

REAL = ROOT / "tests" / "data" / "real" / "a"

# 文件名百分比 = 金红石（rutile）质量分数
STANDARDS = (5, 10, 15, 20, 30, 50)   # 建立校准曲线用
UNKNOWN = (8, 18, 36)                 # 待测样
ALL9 = (5, 8, 10, 15, 18, 20, 30, 36, 50)

# 岛津公布结果（Application_News_AP_XRD-019）
SHIMADZU_RATIO = {8: 7.41, 18: 16.56, 36: 33.26}       # 强度比值法
SHIMADZU_RIETVELD = {8: 8.6, 18: 17.6, 36: 34.6}       # Rietveld 法

# 岛津公布的 6 组标样峰面积口径 Ia/Ir（钛白粉数据.xlsx sheet1）
SHIMADZU_IA = {5: 373777, 10: 351437, 15: 354070,
               20: 318774, 30: 282108, 50: 209713}
SHIMADZU_IR = {5: 15814, 10: 31892, 15: 47123,
               20: 59175, 30: 87638, 50: 149133}
# 岛津公布的 6 组标样峰高口径 Ia/Ir（sheet2）
SHIMADZU_IA_H = {5: 29055, 10: 26744, 15: 30137,
                 20: 27210, 30: 20089, 50: 16937}
SHIMADZU_IR_H = {5: 1430, 10: 3165, 15: 4396,
                 20: 5746, 30: 8348, 50: 13908}

# pd 格式全谱实测谱（独立交叉验证用）
PD_FILES = {8: "pd/8%测试谱.txt", 18: "pd/18%实测谱.txt",
            36: "pd/36%实测谱.txt"}

PASS_LIMIT = 3.0    # 判定合格线（相对误差 %）
GOOD_LIMIT = 2.0    # 力争线


def local_path(wr: int) -> Path:
    """局部扫描谱（24–29°）路径。"""
    return REAL / f"{wr}percent24-29.txt"


def measure_ratio(path: Path, protocol: APeakProtocol) -> tuple[float, float]:
    """测量一条谱的 (Ia, Ir)。"""
    pat = load_pattern(path)
    ia, ir, _, _ = measure_pair(pat, protocol)
    return float(ia), float(ir)


def fit_k(protocol: APeakProtocol) -> tuple[object, dict[int, float]]:
    """用 6 个标样标定 K，返回 (CalibResult, {wr: Ia/Ir})。"""
    pts: list[CalibPoint] = []
    ratios: dict[int, float] = {}
    for wr in STANDARDS:
        ia, ir = measure_ratio(local_path(wr), protocol)
        if ir <= 0:
            raise SystemExit(f"标样 {wr}% 的金红石峰强非正：{ir}")
        ratios[wr] = ia / ir
        pts.append(CalibPoint(ma_over_mr=(100.0 - wr) / wr,
                              ia_over_ir=ia / ir))
    return calibrate_k(pts), ratios


def predict(ia_over_ir: float, k: float) -> tuple[float, float]:
    """标准公式：w_r = 100/(1 + (Ia/Ir)/K)。"""
    wr = 100.0 / (1.0 + ia_over_ir / k)
    return 100.0 - wr, wr


def shimadzu_k(area: bool = True) -> tuple[float, float, float]:
    """用岛津公布的 Ia/Ir 反算 K —— 应复现公布值 1.2234。"""
    ia = SHIMADZU_IA if area else SHIMADZU_IA_H
    ir = SHIMADZU_IR if area else SHIMADZU_IR_H
    pts = [CalibPoint(ma_over_mr=(100.0 - w) / w, ia_over_ir=ia[w] / ir[w])
           for w in STANDARDS]
    return calibrate_k(pts), 0.0, 0.0


def md_table(headers: list[str], rows: list[list[str]]) -> str:
    """生成 Markdown 表格。"""
    out = ["| " + " | ".join(headers) + " |",
           "|" + "|".join(["---"] * len(headers)) + "|"]
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out)


def run(protocol: APeakProtocol, with_pd: bool = True) -> dict:
    """跑一遍完整验证，返回结构化结果。"""
    calib, std_ratios = fit_k(protocol)
    k = calib.K
    rows = []
    for wr in ALL9:
        ia, ir = measure_ratio(local_path(wr), protocol)
        wa, wr_meas = predict(ia / ir, k)
        rel = (wr_meas - wr) / wr * 100.0
        rows.append(dict(wr_true=wr, ia=ia, ir=ir, ratio=ia / ir,
                         wa=wa, wr=wr_meas, rel=rel))
    pd_rows = []
    if with_pd:
        for wr in UNKNOWN:
            p = REAL / PD_FILES[wr]
            if not p.exists():
                continue
            ia, ir = measure_ratio(p, protocol)
            wa, wr_meas = predict(ia / ir, k)
            pd_rows.append(dict(wr_true=wr, ia=ia, ir=ir, ratio=ia / ir,
                                wa=wa, wr=wr_meas,
                                rel=(wr_meas - wr) / wr * 100.0))
    return {"calib": calib, "std_ratios": std_ratios, "rows": rows,
            "pd_rows": pd_rows, "protocol": protocol, "K": k}


def variants() -> list[tuple[str, APeakProtocol]]:
    """口径/平滑/Kα2 的对照协议清单（用于实证对比表）。"""
    base = PROTOCOL_V100
    out = [("v1.0.0 默认（净峰面积 / 不平滑 / 不剥 Kα2）", base)]
    out.append(("改为净峰高口径", APeakProtocol(
        name="v1.0.0-height", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=base.bg, smooth=base.smooth, kalpha2=base.kalpha2,
        quantity="height")))
    out.append(("开启 SG(5,2) 平滑", APeakProtocol(
        name="v1.0.0-sg5", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=base.bg, smooth=SmoothConfig(True, 5, 2), kalpha2=base.kalpha2,
        quantity=base.quantity)))
    out.append(("开启 SG(9,2) 平滑", APeakProtocol(
        name="v1.0.0-sg9", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=base.bg, smooth=SmoothConfig(True, 9, 2), kalpha2=base.kalpha2,
        quantity=base.quantity)))
    out.append(("开启 Rachinger Kα2 剥离 (r=0.5)", APeakProtocol(
        name="v1.0.0-ka2", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=base.bg, smooth=base.smooth,
        kalpha2=KAlpha2Config(enabled=True, ratio=0.5),
        quantity=base.quantity)))
    out.append(("背景改 poly(deg=2)", APeakProtocol(
        name="v1.0.0-poly2", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=BgConfig("poly", base.bg.edge_frac, 2), smooth=base.smooth,
        kalpha2=base.kalpha2, quantity=base.quantity)))
    out.append(("背景改 chebyshev(deg=2)", APeakProtocol(
        name="v1.0.0-cheb2", anatase_2th=base.anatase_2th,
        rutile_2th=base.rutile_2th, anatase_half_win=base.anatase_half_win,
        rutile_half_win=base.rutile_half_win, bg_margin=base.bg_margin,
        bg=BgConfig("chebyshev", base.bg.edge_frac, 2), smooth=base.smooth,
        kalpha2=base.kalpha2, quantity=base.quantity)))
    out.append(("v0.1.0 legacy（峰高 / 25.30-27.44 / ±0.4°）", PROTOCOL_LEGACY))
    return out


def main(argv: list[str] | None = None) -> int:
    """执行验证，返回 0=通过 / 1=未达标。"""
    ap = argparse.ArgumentParser(description="A 法真实数据验证（岛津 XRD-019）")
    ap.add_argument("--markdown", default=None, help="把 Markdown 报告写到文件")
    ap.add_argument("--variants", action="store_true",
                    help="额外输出口径/平滑/Kα2 的对照表")
    ap.add_argument("--no-pd", action="store_true", help="跳过 pd 全谱交叉验证")
    args = ap.parse_args(argv)

    if not local_path(50).exists():
        print(f"错误：真实数据缺失 {local_path(50)}", file=sys.stderr)
        return 2

    res = run(PROTOCOL_V100, with_pd=not args.no_pd)
    calib = res["calib"]
    lines: list[str] = []
    lines.append("# A 法真实数据验证（岛津 XRD-019 · TiO2）\n")
    lines.append(f"测峰协议：`{PROTOCOL_V100.name}`，峰强口径="
                 f"`{PROTOCOL_V100.quantity}`，K 标定=`带截距 OLS 斜率`\n")

    lines.append("\n## 1. K 标定（6 个标样，局部扫描 24–29°）\n")
    lines.append(md_table(
        ["金红石真值 %", "ma/mr", "Ia", "Ir", "Ia/Ir"],
        [[f"{w}", f"{(100 - w) / w:.4f}", f"{res['rows'][ALL9.index(w)]['ia']:.1f}",
          f"{res['rows'][ALL9.index(w)]['ir']:.1f}",
          f"{res['std_ratios'][w]:.4f}"]
         for w in STANDARDS]))
    lines.append("")
    lines.append(f"- **K = {calib.K:.4f}**（带截距 OLS 斜率）")
    lines.append(f"- 截距 = {calib.intercept:+.4f}")
    lines.append(f"- R² = {calib.r2:.5f}（{'达标' if calib.r2_ok else '★低于 0.995'}）")
    lines.append(f"- 过原点口径 K₀ = {calib.K_forced0:.4f}（仅作对照，非默认）")
    lines.append(f"- 标定点数 n = {calib.n_points}")

    lines.append("\n## 2. 九个真实谱的测定结果（局部扫描 24–29°）\n")
    lines.append(md_table(
        ["样品", "真值 金红石%", "实测 wa%", "实测 wr%", "相对误差%", "判定"],
        [[("标样" if r["wr_true"] in STANDARDS else "**待测**"),
          f"{r['wr_true']}", f"{r['wa']:.2f}", f"{r['wr']:.2f}",
          f"{r['rel']:+.2f}",
          "—" if r["wr_true"] in STANDARDS
          else ("合格" if abs(r["rel"]) <= PASS_LIMIT else "超差")]
         for r in res["rows"]]))

    unk = [r for r in res["rows"] if r["wr_true"] in UNKNOWN]
    worst = max(abs(r["rel"]) for r in unk)
    lines.append("")
    lines.append(f"- 三个待测样最大相对误差 = **{worst:.2f}%**"
                 f"（判据 ≤{PASS_LIMIT}%，力争 ≤{GOOD_LIMIT}%）")

    if res["pd_rows"]:
        lines.append("\n## 3. 独立交叉验证：pd 全谱（20–120°）实测谱\n")
        lines.append("用上面「局部扫描」标定的 K，直接预测 FullProf pd 格式的"
                     "全谱实测谱（不同扫描范围、不同强度标度、不同文件格式）。\n")
        lines.append(md_table(
            ["样品", "真值 金红石%", "实测 wa%", "实测 wr%", "相对误差%", "判定"],
            [[f"**{r['wr_true']}**", f"{r['wr_true']}", f"{r['wa']:.2f}",
              f"{r['wr']:.2f}", f"{r['rel']:+.2f}",
              "合格" if abs(r["rel"]) <= PASS_LIMIT else "超差"]
             for r in res["pd_rows"]]))
        pw = max(abs(r["rel"]) for r in res["pd_rows"])
        lines.append("")
        lines.append(f"- 交叉验证最大相对误差 = **{pw:.2f}%**")
        worst = max(worst, pw)

    lines.append("\n## 4. 与岛津公布结果对比\n")
    cmp_rows = []
    for w in UNKNOWN:
        mine = next(r for r in res["rows"] if r["wr_true"] == w)
        sh = SHIMADZU_RATIO[w]
        cmp_rows.append([f"{w}%", f"{mine['wr']:.2f}", f"{mine['rel']:+.2f}",
                         f"{sh:.2f}", f"{(sh - w) / w * 100:+.2f}",
                         f"{SHIMADZU_RIETVELD[w]:.2f}"])
    lines.append(md_table(
        ["样品", "PolyXRD A 法 wr%", "相对误差%", "岛津强度比值法 wr%",
         "岛津相对误差%", "岛津 Rietveld wr%"], cmp_rows))
    lines.append("")
    lines.append("- 岛津强度比值法三个待测样相对误差约 −7.5%（系统性负偏）。")

    if args.variants:
        lines.append("\n## 5. 口径 / 平滑 / Kα2 实证对照\n")
        vrows = []
        for label, proto in variants():
            r = run(proto, with_pd=not args.no_pd)
            lu = max(abs(x["rel"]) for x in r["rows"]
                     if x["wr_true"] in UNKNOWN)
            lp = max(abs(x["rel"]) for x in r["pd_rows"]) if r["pd_rows"] else 0.0
            vrows.append([label, f"{r['calib'].K:.4f}",
                          f"{r['calib'].intercept:+.4f}",
                          f"{r['calib'].r2:.5f}", f"{lu:.2f}",
                          f"{lp:.2f}" if r["pd_rows"] else "—",
                          f"{max(lu, lp):.2f}"])
        lines.append(md_table(
            ["配置", "K", "截距", "R²", "局部 8/18/36 最大误差%",
             "pd 全谱最大误差%", "总 worst%"], vrows))

    text = "\n".join(lines) + "\n"
    print(text)
    if args.markdown:
        Path(args.markdown).write_text(text, encoding="utf-8")
        print(f"Markdown 已写入: {args.markdown}")
    print(f"判据：待测样最大相对误差 {worst:.2f}% "
          f"{'<= 3% → 通过' if worst <= PASS_LIMIT else '> 3% → 未通过'}")
    return 0 if worst <= PASS_LIMIT else 1


if __name__ == "__main__":
    sys.exit(main())
