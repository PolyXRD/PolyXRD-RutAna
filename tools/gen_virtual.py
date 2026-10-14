"""虚拟实验室：已知配比 -> 合成 XRD 谱 + truth（T1.2）。

★ 本脚本允许（且仅限本 tools 脚本）通过 sys.path 临时引用兄弟仓库
PolyXRD-SynthPattern 的合成引擎；rutana 包内严禁任何跨仓 import。

用法：
  python tools/gen_virtual.py --out tests/data/virtual
产出：8 个配比 × (窄窗 A 法 + 宽扫 B 法) 共 16 个 .xy + manifest.json
      + _preview.png（人眼复核用）。
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SYNTH_DIR = Path(r"D:/Project/XRD/PolyXRD-SynthPattern")
CIF_DIR = ROOT / "tests/data/virtual/cif"
SEED = 20260701
RATIOS = [0.1, 1.0, 5.0, 25.0, 50.0, 75.0, 95.0, 99.0]
NARROW_WINDOW = (24.5, 28.5)  # A 法两分析线所在窄窗
BG = (300.0, 4.0, 0.0)        # B(2θ) = a + b·2θ + c·2θ²（线性背景）

# 信噪比按标准 A 法仪器条款反推："0.1% 锐钛型信号 >= 4 倍噪声"。
# 0.1% 时锐钛型峰高约 23 counts @ Imax=50000，取 noise_rel=1e-4
# -> sigma = 5 counts -> SNR ≈ 4.6，恰好满足标准下限。
BASE_PROFILE = {
    "tmin": 5.0, "tmax": 90.0, "step": 0.02,
    "U": 0.0, "V": 0.0, "W": 0.0225,  # Caglioti 常数项: FWHM = sqrt(W) = 0.15°
    "eta": 0.5, "zero": 0.0, "anode": "Cu", "ka_ratio": 0.5,
    "po_hkl": [1, 0, 1], "po_r": 1.0, "size_nm": None,
    "noise_rel": 1.0e-4, "target_peak": 50000.0,
}

# 占位 CIF（T3.1 再换正式 COD 来源）：写满晶胞全部原子 + P1 等效操作，
# 确保 parse_cif 无需对称展开即可算对。晶胞/坐标为标准结构值。
ANATASE_CIF = """# 锐钛型 TiO2 占位 CIF —— I41/amd (141), a=3.7845 c=9.5143
# Ti 4a 与 O 8e 全部等价位置已手工列出（原点取 Ti 4a）。
data_anatase_placeholder
_cell_length_a 3.7845
_cell_length_b 3.7845
_cell_length_c 9.5143
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_symmetry_space_group_name_H-M 'I 41/a m d'
loop_
_symmetry_equiv_pos_as_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Ti1 Ti 0.0 0.0 0.0
Ti2 Ti 0.0 0.5 0.25
Ti3 Ti 0.5 0.5 0.5
Ti4 Ti 0.5 0.0 0.75
O1 O 0.0 0.0 0.2081
O2 O 0.0 0.0 0.7919
O3 O 0.0 0.5 0.4581
O4 O 0.0 0.5 0.0419
O5 O 0.5 0.5 0.7081
O6 O 0.5 0.5 0.2919
O7 O 0.5 0.0 0.9581
O8 O 0.5 0.0 0.5419
"""

RUTILE_CIF = """# 金红石型 TiO2 占位 CIF —— P42/mnm (136), a=4.5937 c=2.9587
# Ti 2a 与 O 4f 全部等价位置已手工列出。
data_rutile_placeholder
_cell_length_a 4.5937
_cell_length_b 4.5937
_cell_length_c 2.9587
_cell_angle_alpha 90.0
_cell_angle_beta 90.0
_cell_angle_gamma 90.0
_symmetry_space_group_name_H-M 'P 42/m n m'
loop_
_symmetry_equiv_pos_as_xyz
'x, y, z'
loop_
_atom_site_label
_atom_site_type_symbol
_atom_site_fract_x
_atom_site_fract_y
_atom_site_fract_z
Ti1 Ti 0.0 0.0 0.0
Ti2 Ti 0.5 0.5 0.5
O1 O 0.3053 0.3053 0.0
O2 O 0.6947 0.6947 0.0
O3 O 0.8053 0.1947 0.5
O4 O 0.1947 0.8053 0.5
"""

_STRUCTS_CACHE: list = []


def _write_cifs() -> None:
    """落盘占位 CIF（已存在则跳过）。"""
    CIF_DIR.mkdir(parents=True, exist_ok=True)
    pa = CIF_DIR / "anatase_placeholder.cif"
    pr = CIF_DIR / "rutile_placeholder.cif"
    if not pa.exists():
        pa.write_text(ANATASE_CIF, encoding="utf-8")
    if not pr.exists():
        pr.write_text(RUTILE_CIF, encoding="utf-8")


def _load_engine():
    """临时把兄弟仓库加入 sys.path 并返回合成引擎模块。"""
    if str(SYNTH_DIR) not in sys.path:
        sys.path.insert(0, str(SYNTH_DIR))
    import xrd_synth_engine as xse
    return xse


def _load_structs(xse) -> list:
    """解析两个占位 CIF（带缓存）。"""
    if not _STRUCTS_CACHE:
        _STRUCTS_CACHE.append(xse.parse_cif(CIF_DIR / "anatase_placeholder.cif"))
        _STRUCTS_CACHE.append(xse.parse_cif(CIF_DIR / "rutile_placeholder.cif"))
    return _STRUCTS_CACHE


def _label(wa: float) -> str:
    """配比 -> 文件名标签（0.1 -> '0p1'）。"""
    return "0p1" if abs(wa - 0.1) < 1e-9 else str(int(wa))


def generate_mixture(wa_percent: float, *, seed: int,
                     profile: dict) -> tuple["Pattern", dict]:
    """合成一份已知配比的两相混合谱。

    返回 (Pattern, truth)，truth = {"wa_nominal", "wr_nominal", "profile"}。
    """
    from rutana.core.dtypes import Pattern
    xse = _load_engine()
    anatase, rutile = _load_structs(xse)
    grid = xse.make_grid(profile["tmin"], profile["tmax"], profile["step"])
    fwhm = math.sqrt(profile["W"])
    y, _info = xse.synthesize_multi_phase(
        [(anatase, wa_percent), (rutile, 100.0 - wa_percent)],
        grid, wavelength=1.5406,
        fwhm_func=xse.constant_fwhm(fwhm), eta=profile["eta"],
        bg=BG, noise_strength=0.0, noise_rel=profile["noise_rel"],
        target_peak=profile["target_peak"], seed=seed,
        physics={"anode": profile["anode"], "ka_ratio": profile["ka_ratio"],
                 "size_nm": profile["size_nm"], "microstrain": None})
    pat = Pattern(two_theta=np.asarray(grid, dtype=np.float64),
                  intensity=np.asarray(y, dtype=np.float64),
                  meta={"source_format": "xy", "path": "",
                        "wavelength_anode": profile["anode"]})
    truth = {"wa_nominal": float(wa_percent),
             "wr_nominal": 100.0 - float(wa_percent),
             "profile": dict(profile)}
    return pat, truth


def write_xy(path: Path, pat, header: str) -> None:
    """写两列 .xy（'#' 注释头 + 2θ 强度）。"""
    lines = [f"# {header}"]
    lines += [f"{x:.4f} {y:.1f}"
              for x, y in zip(pat.two_theta, pat.intensity)]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _check_peak_positions(pat) -> tuple[float, float]:
    """检查 v50 窄窗谱上两分析线峰位（人眼复核的机器替代）。"""
    pos = []
    for _expected, span in ((25.30, (24.9, 25.7)), (27.44, (27.0, 27.9))):
        m = (pat.two_theta >= span[0]) & (pat.two_theta <= span[1])
        pos.append(float(pat.two_theta[m][int(np.argmax(pat.intensity[m]))]))
    return pos[0], pos[1]


def _make_preview(out: Path) -> None:
    """生成 v50 预览 PNG 并校验峰位误差 < 0.05°。"""
    from rutana.core.patterns import load_pattern
    from rutana.core.plot import plot_overlay
    p50 = load_pattern(out / "v50.xy")
    w50 = load_pattern(out / "v50_wide.xy")
    plot_overlay([("v50 窄窗 (A 法 24.5-28.5°)", p50),
                  ("v50 宽扫 (B 法 5-90°)", w50)],
                 "T1.2 虚拟实验室预览 · v50", out / "_preview.png")
    pos_a, pos_r = _check_peak_positions(p50)
    print(f"[check] 锐钛型峰位 {pos_a:.3f}° (期望 25.30±0.05) · "
          f"金红石峰位 {pos_r:.3f}° (期望 27.44±0.05)")
    if abs(pos_a - 25.30) > 0.05 or abs(pos_r - 27.44) > 0.05:
        raise SystemExit("峰位检查失败：占位 CIF 或合成参数有误")


def main(argv: list[str] | None = None) -> int:
    """生成全部虚拟样 + manifest + 预览图。"""
    ap = argparse.ArgumentParser(description="PolyXRD-RutAna 虚拟实验室")
    ap.add_argument("--out", default=str(ROOT / "tests/data/virtual"))
    args = ap.parse_args(argv)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    _write_cifs()
    samples = []
    for wa in RATIOS:
        prof_narrow = {**BASE_PROFILE, "tmin": NARROW_WINDOW[0],
                       "tmax": NARROW_WINDOW[1]}
        pat_n, truth = generate_mixture(wa, seed=SEED, profile=prof_narrow)
        pat_w, _ = generate_mixture(wa, seed=SEED, profile=dict(BASE_PROFILE))
        lbl = _label(wa)
        fn, fw = f"v{lbl}.xy", f"v{lbl}_wide.xy"
        write_xy(out / fn, pat_n,
                 f"PolyXRD-RutAna 虚拟样 wa={wa}% 窄窗A法 seed={SEED}")
        write_xy(out / fw, pat_w,
                 f"PolyXRD-RutAna 虚拟样 wa={wa}% 宽扫B法 seed={SEED}")
        samples.append({"file": fn, "file_wide": fw, **truth})
        print(f"[gen] {fn} + {fw}  wa={wa}%")
    manifest = {
        "seed": SEED, "profile": BASE_PROFILE, "background": list(BG),
        "narrow_window": list(NARROW_WINDOW),
        "cif": {"anatase": "cif/anatase_placeholder.cif",
                "rutile": "cif/rutile_placeholder.cif"},
        "samples": samples,
    }
    (out / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8")
    _make_preview(out)
    print(f"[done] {len(samples)} 配比 × 2 谱 + manifest.json -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
