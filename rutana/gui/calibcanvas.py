"""K 标定曲线画布：标准混合样散点 + 拟合直线。

横轴 m(A)/m(R)（已知质量比），纵轴 I(A)/I(R)（实测净强度比），
直线即标定曲线，斜率即 K。图上直接标注 K / 截距 / R²，便于判断好坏。
"""

from __future__ import annotations

from typing import Sequence

import matplotlib
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure

matplotlib.rcParams["font.sans-serif"] = [
    "Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "DejaVu Sans"]
matplotlib.rcParams["axes.unicode_minus"] = False

from rutana.i18n import tr  # noqa: E402 - matplotlib 设置须先行

POINT_COLOR = "#0284C7"
FIT_COLOR = "#DC2626"
GRID = "#CBD5E1"


class CalibCanvas(FigureCanvasQTAgg):
    """K 标定曲线（I(A)/I(R) vs m(A)/m(R)）。"""

    def __init__(self, parent=None) -> None:
        self.figure = Figure(figsize=(4.6, 3.4), dpi=100)
        super().__init__(self.figure)
        self.setParent(parent)
        self.ax_main = self.figure.add_subplot(111)
        self.clear_view()
        self.figure.tight_layout()

    # ------------------------------------------------------------------ #
    def plot(self, xs: Sequence[float], ys: Sequence[float], *, k: float,
             intercept: float, r2: float, n: int) -> None:
        """绘制散点与拟合直线，并标注 K / 截距 / R²。"""
        self._reset()
        x = np.asarray(list(xs), dtype=np.float64)
        y = np.asarray(list(ys), dtype=np.float64)
        if x.size == 0:
            self.clear_view()
            return
        self.ax_main.scatter(x, y, s=46, color=POINT_COLOR,
                             label=tr("kwizard.curve_points"), zorder=3)
        x_line = np.linspace(0.0, float(np.max(x)) * 1.05, 100) if x.size else np.zeros(1)
        self.ax_main.plot(x_line, k * x_line + intercept, color=FIT_COLOR, lw=1.4,
                          label=tr("kwizard.curve_fit"), zorder=2)
        self.ax_main.set_title(tr("kwizard.curve_title"), fontsize=10)
        self.ax_main.set_xlabel(tr("kwizard.col.mr"))
        self.ax_main.set_ylabel(tr("kwizard.col.ir"))
        self.ax_main.grid(True, color=GRID, lw=0.4, alpha=0.5)
        self.ax_main.legend(loc="upper left", fontsize=8, frameon=False)
        self.ax_main.text(
            0.98, 0.04, tr("kwizard.result", k=k, b=intercept, r2=r2, n=n),
            transform=self.ax_main.transAxes, ha="right", va="bottom", fontsize=8,
            color="#0F172A")
        self.figure.tight_layout()
        self.draw_idle()

    def clear_view(self) -> None:
        """回到空态提示（尚未有标定点时）。"""
        self._reset()
        self.ax_main.set_facecolor("white")
        self.ax_main.text(0.5, 0.5, tr("canvas.empty"), ha="center", va="center",
                          fontsize=10, color="#64748B",
                          transform=self.ax_main.transAxes)
        self.ax_main.set_xticks([])
        self.ax_main.set_yticks([])
        self.figure.tight_layout()
        self.draw_idle()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """语言切换后的轻量刷新（空态文案）。"""
        self.figure.tight_layout()
        self.draw_idle()

    def _reset(self) -> None:
        self.figure.clf()
        self.ax_main = self.figure.add_subplot(111)
