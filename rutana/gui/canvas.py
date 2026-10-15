"""matplotlib 谱图画布。

- 空态显示提示文字；
- ``show_pattern``：单谱显示（导入后）；
- ``show_fit``：拟合叠加显示（2:1 子图，上 obs/calc，下差值线）。

v1.2.0 拟合谱样式（按用户给定样式，家族色让位）：

- 实测谱：蓝色 ``×`` 散点（无连线）；
- 理论谱：黑色实线；
- 误差线（差值）：红色实线，画在下方面板；
- 图例三项：实测谱 / 理论谱 / 误差线；
- 轴标签：x = ``2Theta(deg)``、y = ``Intensity(counts)``（见 i18n）。

绘制逻辑集中在 :func:`draw_fit`，主画布与离屏 PNG 导出共用，保证两处样式一致。
"""

from __future__ import annotations

import numpy as np
import matplotlib
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

# 让画布文案（中文/日文）正确渲染：优先 CJK 字体，关闭负号替换
matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from rutana.i18n import tr

# v1.2.0 拟合谱色板（用户指定样式）
INK = "#0F172A"      # 深色（单谱显示）
OBS = "#0284C7"      # 蓝色（实测谱散点）
CALC = "#0F172A"     # 黑色（理论谱实线）
DIFF = "#DC2626"     # 红色（误差线）
GRID = "#CBD5E1"     # 浅灰网格


def draw_fit(ax_main, ax_diff, two_theta, yobs, ycalc, diff) -> None:
    """在上下双轴上按 v1.2.0 样式绘制拟合谱（画布与离屏 PNG 共用）。

    ax_main：实测谱（蓝 × 散点）+ 理论谱（黑实线）与图例；
    ax_diff：误差线（红）与零基线，x 轴标签只在此处标注一次。
    """
    tt = np.asarray(two_theta)
    h_obs, = ax_main.plot(tt, np.asarray(yobs), linestyle="none", marker="x",
                          color=OBS, markersize=3.0, markeredgewidth=0.6,
                          label=tr("canvas.legend.obs"))
    h_calc, = ax_main.plot(tt, np.asarray(ycalc), color=CALC, lw=1.0,
                           label=tr("canvas.legend.calc"))
    ax_main.set_ylabel(tr("canvas.y_label"))
    ax_main.grid(True, color=GRID, lw=0.4, alpha=0.5)

    h_diff, = ax_diff.plot(tt, np.asarray(diff), color=DIFF, lw=0.8,
                           label=tr("canvas.legend.err"))
    ax_diff.axhline(0.0, color=GRID, lw=0.6)
    ax_diff.set_xlabel(tr("canvas.x_label"))
    ax_diff.set_ylabel(tr("canvas.y_diff"))
    ax_diff.grid(True, color=GRID, lw=0.4, alpha=0.5)
    # x 轴刻度标签只在下方差值图上显示一次（共用 x 轴，避免重复标注）
    ax_diff.tick_params(labelbottom=True)
    ax_main.tick_params(labelbottom=False)
    # 图例三项（含误差线）统一挂在主面板右上角
    ax_main.legend([h_obs, h_calc, h_diff],
                   [tr("canvas.legend.obs"), tr("canvas.legend.calc"),
                    tr("canvas.legend.err")],
                   loc="upper right", fontsize=8, frameon=False)


class PatternCanvas(FigureCanvasQTAgg):
    """谱图显示画布（QWidget）。"""

    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(5.2, 4.2), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self._has_data = False
        self._fit: tuple | None = None     # 最近一次拟合数据（语言切换时重绘）
        self.ax_main = self.figure.add_subplot(111)
        self.ax_diff = None
        self._show_empty()
        self.figure.tight_layout()

    # ------------------------------------------------------------------ #
    # 显示
    # ------------------------------------------------------------------ #
    def show_pattern(self, two_theta: np.ndarray, intensity: np.ndarray) -> None:
        """显示单条谱图（导入后）。"""
        self._reset_axes()
        self.ax_main.plot(two_theta, intensity, color=INK, lw=0.9)
        self._style_main()
        self._has_data = True
        self.figure.tight_layout()
        self.draw_idle()

    def show_fit(self, two_theta: np.ndarray, yobs: np.ndarray,
                 ycalc: np.ndarray, diff: np.ndarray) -> None:
        """拟合叠加：上 2/3 实测谱+理论谱，下 1/3 误差线（共用 x 轴）。

        注意：这里必须彻底清空 figure（不能复用 ``_reset_axes``）——
        后者会保留一个 111 主轴，若在其上再叠加 two-row 子图，
        会残留一个 0..1 归一化坐标的空坐标框，导致刻度标签重影。
        也不要用 ``add_gridspec`` + 自定义 hspace：tight_layout 与之不兼容
        （告警并放弃重排，x 轴标题会被裁掉），故改用 ``Figure.subplots``。
        """
        self._fit = (two_theta, yobs, ycalc, diff)
        self._clear_figure()
        self.ax_main, self.ax_diff = self.figure.subplots(
            2, 1, height_ratios=[2, 1], sharex=True)
        draw_fit(self.ax_main, self.ax_diff, two_theta, yobs, ycalc, diff)
        self._has_data = True
        self.figure.tight_layout()
        self.draw_idle()

    def clear(self) -> None:
        """清空回空态。"""
        self._fit = None
        self._reset_axes()
        self._show_empty()
        self.figure.tight_layout()
        self.draw_idle()

    def save_png(self, path: str) -> None:
        """导出当前画布为 PNG。"""
        self.figure.savefig(path, dpi=150, facecolor="white")

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """语言切换后刷新轴标签/图例/空态文案。

        拟合态直接按缓存数据重绘（图例与两个轴标签一并换新语言），
        单谱态与空态只改标签，避免为刷新文案而缓存整条谱。
        """
        if self._fit is not None:
            self.show_fit(*self._fit)
            return
        if not self._has_data:
            self.clear()
            return
        self.ax_main.set_ylabel(tr("canvas.y_label"))
        self.figure.tight_layout()
        self.draw_idle()

    # ------------------------------------------------------------------ #
    # 内部工具
    # ------------------------------------------------------------------ #
    def _reset_axes(self) -> None:
        """清空画布并重建单个主轴（单谱显示模式使用）。"""
        self.figure.clf()
        self.ax_main = self.figure.add_subplot(111)
        self.ax_diff = None

    def _clear_figure(self) -> None:
        """彻底清空 figure（不留任何 axes），供多子图模式重新布局前调用。"""
        self.figure.clf()
        self.ax_main = None
        self.ax_diff = None

    def _show_empty(self) -> None:
        self.ax_main.set_facecolor("white")
        self.ax_main.text(0.5, 0.5, tr("canvas.empty"),
                          ha="center", va="center", fontsize=11,
                          color="#64748B", transform=self.ax_main.transAxes)
        self.ax_main.set_xticks([])
        self.ax_main.set_yticks([])

    def _style_main(self, with_legend: bool = False) -> None:
        self.ax_main.set_ylabel(tr("canvas.y_label"))
        self.ax_main.grid(True, color=GRID, lw=0.4, alpha=0.5)
