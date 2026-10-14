"""B 法真实数据验证（v1.0.0）—— 岛津 XRD-019 数据集逐样验证。

对 4 份真实全谱（8/18/36% pd 谱 + 50% 岛津导出全谱）跑 realdata 推荐配置的
Rietveld 精修，输出 R 因子与定量结果对照表。

用法:
    D:/Project/XRD/python310/python.exe tools/verify_realdata_b.py
只读数据源: tests/data/real/（岛津原始数据的测试副本）。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from rutana.core.dtypes import Pattern  # noqa: E402
from rutana.core.profile.cif import parse_cif  # noqa: E402
from rutana.core.refine.nonlinear import refine  # noqa: E402
from rutana.core.refine.qpa import qpa_weights, to_ratio  # noqa: E402
from rutana.core.refine.realdata import real_config, real_params  # noqa: E402

REAL = ROOT / "tests" / "data" / "real"
M_TIO2 = 79.865

SAMPLES = [
    # (标签, 谱文件相对 REAL 的路径, 真值 金红石 wt%)
    ("8%  pd全谱", "pd/8%测试谱.txt", 8.0),
    ("18% pd全谱", "pd/18%实测谱.txt", 18.0),
    ("36% pd全谱", "pd/36%实测谱.txt", 36.0),
    ("50% 岛津全谱", "50percent.txt", 50.0),
]


def load_any(path: Path) -> Pattern:
    """两列文本 / FullProf pd 格式统一读取（跳过非数值行）。"""
    rows: list[tuple[float, float]] = []
    started = False
    for ln in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        s = ln.strip()
        if s.startswith("loop_"):
            started = True
            continue
        p = s.split()
        if len(p) != 2:
            continue
        try:
            rows.append((float(p[0]), float(p[1])))
        except ValueError:
            continue
    if not rows:
        raise ValueError(f"无法解析: {path}")
    xs = np.array([r[0] for r in rows])
    ys = np.array([r[1] for r in rows])
    order = np.argsort(xs)
    return Pattern(two_theta=xs[order], intensity=ys[order], meta={"path": str(path)})


def main() -> int:
    st_a = parse_cif(ROOT / "rutana" / "data" / "anatase.cif")
    st_r = parse_cif(ROOT / "rutana" / "data" / "rutile.cif")
    print("| 样品 | 真值 金红石% | 实测 金红石% | 绝对差 pp | 相对误差% | Rwp% | Rp% | χ² | 用时 s |")
    print("|---|---|---|---|---|---|---|---|---|")
    out = []
    worst = 0.0
    for tag, rel, truth in SAMPLES:
        pat = load_any(REAL / rel)
        t0 = time.time()
        res = refine([st_a, st_r], pat, real_params(), real_config())
        dt = time.time() - t0
        (fa_a, fc_a), (fa_r, fc_r) = res.cell_scales
        va = (st_a.cell[0] * fa_a) ** 2 * (st_a.cell[2] * fc_a)
        vr = (st_r.cell[0] * fa_r) ** 2 * (st_r.cell[2] * fc_r)
        ws = qpa_weights([(st_a.name, float(res.scales[0]), 4, va, M_TIO2),
                          (st_r.name, float(res.scales[1]), 2, vr, M_TIO2)])
        _wa, wr = to_ratio(ws, 0, 1)
        err_abs = wr - truth
        err_rel = 100.0 * err_abs / truth
        worst = max(worst, abs(err_rel))
        print(f"| {tag} | {truth:.0f} | {wr:.2f} | {err_abs:+.2f} | "
              f"{err_rel:+.2f} | {res.rf.rwp:.2f} | {res.rf.rp:.2f} | "
              f"{res.rf.chi2:.2f} | {dt:.0f} |")
        out.append({"tag": tag, "truth": truth, "wr": round(wr, 3),
                    "rwp": round(res.rf.rwp, 3), "rp": round(res.rf.rp, 3),
                    "chi2": round(res.rf.chi2, 3), "sec": round(dt)})
    print(f"\n最差相对误差 = {worst:.2f}%（判据 ≤3%，岛津 Rietveld 参考 "
          f"+7.5/−2.2/−3.9%，其 Rwp 10.16–10.99%）")
    dst = ROOT / "tests" / "golden" / "method_b_realdata.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=1),
                   encoding="utf-8")
    print(f"结果已存 {dst.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
