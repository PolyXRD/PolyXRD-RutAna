"""matplotlib 谱图画布。

- 空态显示提示文字；
- ``show_pattern``：单谱显示（导入后）；
- ``show_fit``：拟合叠加显示（2:1 子图，上 obs/calc，下差值线）。

家族视觉：实测线深色 #0F172A、计算线品牌蓝 #0284C7、差值线青色 #22D3EE。
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

# 家族色
INK = "#0F172A"      # 深色（实测）
BRAND = "#0284C7"    # 品牌蓝（计算）
CYAN = "#22D3EE"     # 青色（差值）
GRID = "#CBD5E1"     # 浅灰网格


class PatternCanvas(FigureCanvasQTAgg):
    """谱图显示画布（QWidget）。"""

    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(5.2, 4.2), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self._has_data = False
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
        """拟合叠加：上 2/3 obs+calc，下 1/3 差值线（共用 x 轴）。"""
        self._reset_axes()
        gs = self.figure.add_gridspec(2, 1, height_ratios=[2, 1], hspace=0.08)
        self.ax_main = self.figure.add_subplot(gs[0])
        self.ax_diff = self.figure.add_subplot(gs[1], sharex=self.ax_main)
        self.ax_main.plot(two_theta, yobs, color=INK, lw=0.8, label=tr("canvas.legend.obs"))
        self.ax_main.plot(two_theta, ycalc, color=BRAND, lw=1.0, label=tr("canvas.legend.calc"))
        self.ax_diff.plot(two_theta, diff, color=CYAN, lw=0.8)
        self.ax_diff.axhline(0.0, color=GRID, lw=0.6)
        self._style_main(with_legend=True)
        self.ax_diff.set_xlabel(tr("canvas.x_label"))
        self.ax_diff.set_ylabel(tr("canvas.legend.diff"))
        self.ax_diff.grid(True, color=GRID, lw=0.4, alpha=0.5)
        # x 轴刻度标签由主图统一显示
        self.ax_diff.tick_params(labelbottom=False)
        self.ax_main.tick_params(labelbottom=False)
        self._has_data = True
        self.figure.tight_layout()
        self.draw_idle()

    def clear(self) -> None:
        """清空回空态。"""
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
        """语言切换后刷新轴标签/图例/空态文案。"""
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
        self.figure.clf()
        self.ax_main = self.figure.add_subplot(111)
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
        if with_legend:
            self.ax_main.legend(loc="upper right", fontsize=8, frameon=False)
