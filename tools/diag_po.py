"""v1.4.0 · 择优取向（March–Dollase）精修真实数据实证。

对 tests/data/real 下 4 个 pd 全谱样（与 tools/verify_realdata_b.py 同清单）
分别以 realdata 推荐配置跑两遍：

1. PO 关（preset 默认，refine_po=False）——v1.3.0 基线口径；
2. PO 开（real_config(refine_po=True)）——择优取向 r 参与精修。

打印对照表：Rwp、wr 定量值与相对误差、精修出的 r(锐钛)/r(金红石)、
单样本耗时，供 preset 默认值决策（判据：Rwp 不劣化超过 0.3pp 且定量
|相对误差| 仍 ≤3%，4 样全部满足则 preset 默认开，否则保持默认关）。

用法:
    D:/Project/XRD/python310/python.exe tools/diag_po.py
只读数据源: tests/data/real/（岛津原始数据的测试副本）。
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from verify_realdata_b import M_TIO2, SAMPLES, REAL, load_any  # noqa: E402

from rutana.core.profile.cif import parse_cif  # noqa: E402
from rutana.core.refine.nonlinear import refine  # noqa: E402
from rutana.core.refine.qpa import qpa_weights, to_ratio  # noqa: E402
from rutana.core.refine.realdata import real_config, real_params  # noqa: E402


def _quant(phases, res) -> tuple[float, float, float]:
    """(w_rutile%, r_anatase, r_rutile)。"""
    st_a, st_r = phases
    (fa_a, fc_a), (fa_r, fc_r) = res.cell_scales
    va = (st_a.cell[0] * fa_a) ** 2 * (st_a.cell[2] * fc_a)
    vr = (st_r.cell[0] * fa_r) ** 2 * (st_r.cell[2] * fc_r)
    ws = qpa_weights([(st_a.name, float(res.scales[0]), 4, va, M_TIO2),
                      (st_r.name, float(res.scales[1]), 2, vr, M_TIO2)])
    _wa, wr = to_ratio(ws, 0, 1)
    po_r = res.po_r or {}
    ra = po_r.get("anatase")
    rr = po_r.get("rutile")
    return wr, (float(ra[3]) if ra else float("nan")), \
        (float(rr[3]) if rr else float("nan"))


def main() -> int:
    st_a = parse_cif(ROOT / "rutana" / "data" / "anatase.cif")
    st_r = parse_cif(ROOT / "rutana" / "data" / "rutile.cif")
    phases = [st_a, st_r]
    prm0 = real_params()

    print("| 样品 | 配置 | Rwp% | 金红石实测% | 相对误差% | r(锐钛) | r(金红石) | 用时 s |")
    print("|---|---|---|---|---|---|---|---|")
    worst_rel_po = 0.0
    worst_rwp_delta = 0.0
    for tag, rel, truth in SAMPLES:
        pat = load_any(REAL / rel)
        row = {"tag": tag, "truth": truth}
        for label, cfg in (("PO 关", real_config(refine_po=False)),
                           ("PO 开", real_config(refine_po=True))):
            t0 = time.time()
            res = refine(phases, pat, prm0, cfg)
            dt = time.time() - t0
            wr, ra, rr = _quant(phases, res)
            err_rel = 100.0 * (wr - truth) / truth
            print(f"| {tag} | {label} | {res.rf.rwp:.2f} | {wr:.2f} | "
                  f"{err_rel:+.2f} | {ra:.3f} | {rr:.3f} | {dt:.0f} |")
            row[label] = {"rwp": res.rf.rwp, "wr": wr, "err_rel": err_rel,
                          "ra": ra, "rr": rr, "sec": dt}
        d_rwp = row["PO 开"]["rwp"] - row["PO 关"]["rwp"]
        worst_rel_po = max(worst_rel_po, abs(row["PO 开"]["err_rel"]))
        worst_rwp_delta = max(worst_rwp_delta, d_rwp)
        row["d_rwp"] = d_rwp
    print(f"\nPO 开 vs PO 关：Rwp 最大劣化 {worst_rwp_delta:+.2f}pp"
          f"（判据 ≤ +0.3pp）；PO 开定量最差 |相对误差| "
          f"{worst_rel_po:.2f}%（判据 ≤3%）")
    ok = worst_rwp_delta <= 0.3 and worst_rel_po <= 3.0
    print(f"preset 决策：{'默认开启 refine_po' if ok else '保持默认关闭'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
