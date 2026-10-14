"""谱图绘制工具（T1.3）—— 调试 / 肉眼验收用。

强制 matplotlib Agg 后端，避免 GUI 依赖；CLI 与测试环境均可直接出 PNG。
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

# 中文标签字体回退（缺失字形时退回 DejaVu Sans，仅影响预览图美观）
matplotlib.rcParams["font.sans-serif"] = ["Microsoft YaHei", "SimHei",
                                          "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from rutana.core.dtypes import Pattern  # noqa: E402


def plot_overlay(pairs: list[tuple[str, Pattern]], title: str,
                 out_png: str | Path) -> None:
    """多条谱图叠加在同一坐标系，保存为 PNG。"""
    fig, ax = plt.subplots(figsize=(8.0, 5.0), dpi=120)
    for label, pat in pairs:
        ax.plot(pat.two_theta, pat.intensity, label=label, lw=0.9)
    ax.set_xlabel("2θ (°)")
    ax.set_ylabel("Intensity (counts)")
    ax.set_title(title)
    ax.legend(loc="best", fontsize=8)
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)


def plot_fit(obs: Pattern, calc: Pattern, diff: Pattern,
             out_png: str | Path) -> None:
    """Rietveld 风格拟合图：上 2 下 1（上 obs/calc，下 diff）。"""
    fig, (ax1, ax2) = plt.subplots(
        2, 1, figsize=(8.0, 6.0), dpi=120, sharex=True,
        gridspec_kw={"height_ratios": [2, 1]})
    ax1.plot(obs.two_theta, obs.intensity, color="black", lw=0.8,
             label="Obs")
    ax1.plot(calc.two_theta, calc.intensity, color="red", lw=0.8,
             label="Calc")
    ax1.set_ylabel("Intensity (counts)")
    ax1.legend(loc="best", fontsize=8)
    ax1.set_title("Fit")
    ax2.plot(diff.two_theta, diff.intensity, color="gray", lw=0.8)
    ax2.axhline(0.0, color="black", lw=0.5)
    ax2.set_xlabel("2θ (°)")
    ax2.set_ylabel("Diff")
    fig.tight_layout()
    fig.savefig(out_png)
    plt.close(fig)
