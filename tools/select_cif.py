"""T3.1 · 内置 CIF 选取：从 COD 库打分择优，落盘 rutana/data/{anatase,rutile}.cif。

候选: 锐钛型 I41/amd -> 5000223 / 7206075 / 1530151
      金红石型 P42/mnm -> 4102355 / 9001681 / 1530150
打分: 用 vendor 的 compute_peaks 算最强 5 线 d 值，与 PDF2-2004 卡片
      (21-1272 锐钛型 / 21-1276 金红石型) 的最强 5 线比 RMS 相对偏差。
      PDF2 查询失败时回退到内置参考表（容差 0.5%）。
运行: D:/Project/XRD/python310/python.exe tools/select_cif.py
"""
from __future__ import annotations

import gzip
import json
import re
import sqlite3
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from rutana.core.profile.cif import parse_cif  # noqa: E402
from rutana.core.profile.shape import resolve_wavelengths  # noqa: E402
from rutana.core.profile.struct import compute_peaks  # noqa: E402

COD_DB = Path(r"D:/Project/XRD/PolyXRD/cod_data/COD_inorganics.sqlite")
PDF2_DB = Path(r"D:/Project/XRD/PolyXRD/cod_data/PDF2_2004.sqlite")

# 回退参考表 (PDF 卡 21-1272 / 21-1276，最强 5 线 d 值，容差 0.5%)
REFERENCE = {
    "anatase": [3.520, 2.378, 1.892, 1.700, 1.667],
    "rutile": [3.247, 2.487, 1.687, 2.188, 1.452],
}
CANDIDATES = {
    "anatase": [5000223, 7206075, 1530151],
    "rutile": [4102355, 9001681, 1530150],
}
PDF_CARD = {"anatase": "PDF2-211272", "rutile": "PDF2-211276"}


def load_cif_from_cod(cod_id: int) -> str:
    """从 COD 库取出 gzip 内联 CIF 并解压为文本。"""
    con = sqlite3.connect(str(COD_DB))
    try:
        row = con.execute(
            "SELECT cif_gz FROM phases WHERE cod_id=?", (cod_id,)).fetchone()
    finally:
        con.close()
    if row is None or row[0] is None:
        raise ValueError(f"COD {cod_id}: 无 CIF")
    # COD 库实际存的是 gzip 格式 (魔数 1f 8b)
    return gzip.decompress(row[0]).decode("utf-8", errors="replace")


def strip_esd(text: str) -> str:
    """去掉 COD CIF 数值里的标准不确定度后缀，如 3.7892(4) -> 3.7892。

    vendor 的 parse_cif 对 esd 后缀不宽容（_to_float 失败会静默保留缺省晶胞），
    故在选取阶段先做规范化，不改动 vendor 本身。
    """
    return "\n".join(re.sub(r"(\d)\(\d+\)", r"\1", ln)
                     for ln in text.splitlines())


def load_pdf2_reference(card: str) -> list[float] | None:
    """从 PDF2-2004 库取卡片最强 5 线 d 值（按强度降序、同强按 d 降序稳定排序）。"""
    if not PDF2_DB.exists():
        return None
    con = sqlite3.connect(str(PDF2_DB))
    try:
        row = con.execute(
            "SELECT peaks_d, peaks_i FROM phases WHERE display_id=?",
            (card,)).fetchone()
    finally:
        con.close()
    if row is None:
        return None
    d = [float(x) for x in row[0].split(",") if x.strip()]
    i = [float(x) for x in row[1].split(",") if x.strip()]
    pairs = sorted(zip(d, i), key=lambda t: (-t[1], -t[0]))[:5]
    return [p[0] for p in pairs]


def top_lines(struct, tmin: float = 5.0, tmax: float = 90.0,
              n: int = 5) -> list[tuple[float, float]]:
    """compute_peaks -> 最强 n 线 [(d, 相对强度)]（按强度降序、同强按 d 降序）。"""
    comps = resolve_wavelengths(1.5406, None)
    peaks, _skipped = compute_peaks(struct, 1.5406, tmin, tmax,
                                    wavelengths=comps)
    pairs = sorted(((d, h) for _p, h, d in peaks),
                   key=lambda t: (-t[1], -t[0]))
    hmax = pairs[0][1] if pairs else 1.0
    return [(d, 100.0 * h / hmax) for d, h in pairs[:n]]


def all_d_values(struct, tmin: float = 5.0, tmax: float = 90.0) -> list[float]:
    """全部计算谱线 d 值（供参考线最近邻匹配）。"""
    comps = resolve_wavelengths(1.5406, None)
    peaks, _skipped = compute_peaks(struct, 1.5406, tmin, tmax,
                                    wavelengths=comps)
    return [d for _p, _h, d in peaks]


def score_candidate(calc_d: list[float], ref_d: list[float]) -> tuple[float, list[float]]:
    """RMS 相对偏差 (%)：对每条参考 d 取计算谱线最近邻（0.5% 容差外记罚 1%）。"""
    devs = []
    for rd in ref_d:
        best = min(abs(cd - rd) / rd for cd in calc_d) if calc_d else 1.0
        devs.append(min(best, 0.005) * 100.0 if best <= 0.005 else 1.0)
    return float(np.sqrt(np.mean(np.square(devs)))), devs


def main() -> int:
    report = ["# T3.1 内置 CIF 打分表\n"]
    picks = {}
    for phase in ("anatase", "rutile"):
        ref = load_pdf2_reference(PDF_CARD[phase])
        ref_src = PDF_CARD[phase]
        if ref is None:
            ref = REFERENCE[phase]
            ref_src = "内置参考表 (回退)"
        report.append(f"## {phase} 参考 ({ref_src}): "
                      + ", ".join(f"{d:.4f}" for d in ref) + "\n")
        report.append("| COD ID | a (Å) | c (Å) | 最强5线 RMS 偏差 (%) | 各线偏差 (%) |")
        report.append("|---|---|---|---|---|")
        best = None
        for cod_id in CANDIDATES[phase]:
            text = strip_esd(load_cif_from_cod(cod_id))
            tmp = ROOT / "tests" / "out" / f"_cand_{cod_id}.cif"
            tmp.parent.mkdir(parents=True, exist_ok=True)
            tmp.write_text(text, encoding="utf-8")
            st = parse_cif(tmp)
            top = top_lines(st)
            rms, devs = score_candidate(all_d_values(st), ref)
            top_fmt = "; ".join(f"{d:.3f}({i:.0f})" for d, i in top)
            report.append(f"| {cod_id} | {st.cell[0]:.4f} | {st.cell[2]:.4f} "
                          f"| {rms:.4f} | " + ", ".join(f"{d:.3f}" for d in devs)
                          + " |")
            report.append(f"| ^ 计算 5 强线 | | | | {top_fmt} |")
            if best is None or rms < best[1]:
                best = (cod_id, rms, st, text, top)
        cod_id, rms, st, text, top = best
        out = ROOT / "rutana" / "data" / f"{phase}.cif"
        out.write_text(text, encoding="utf-8")
        picks[phase] = {"cod_id": cod_id, "rms": rms,
                        "cell": list(st.cell), "top5_d_i": top,
                        "n_atoms": len(st.atoms),
                        "n_asym": st.n_asym, "n_sym_ops": st.n_sym_ops}
        report.append(f"\n**选中**: COD {cod_id} (RMS {rms:.4f}%) -> "
                      f"`rutana/data/{phase}.cif`，全晶胞原子数 {len(st.atoms)}，"
                      f"不对称单位 {st.n_asym} 原子 × {st.n_sym_ops} 对称操作\n")
    (ROOT / "tests" / "out" / "cif_score.json").write_text(
        json.dumps(picks, indent=2, ensure_ascii=False), encoding="utf-8")
    print("\n".join(report))
    (ROOT / "tests" / "out" / "cif_score_report.md").write_text(
        "\n".join(report), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
