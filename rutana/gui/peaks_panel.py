"""主峰参数面板：谱图下方常驻的两相主峰表。

列序固定：物相 / 2θ / d / (hkl) / 强度 / 半峰宽 / 晶粒度（谢乐）。

设计约束（家族约定）
--------------------
- 本控件**只做展示**：数值由 :func:`rutana.gui.services.main_peaks` 计算
  （core 的 :mod:`rutana.core.phasepeak`），控件不碰任何算法；
- 表格只读、整行选中，避免误改；语言热切换靠 ``retranslate`` 重设表头 +
  缓存行的物相名（不重新计算，切换语言是零成本的）；
- 空态用一行合并单元格给出提示，不让用户面对一张空表猜「是不是坏了」。
"""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rutana.i18n import tr

#: 表格列序
(COL_PHASE, COL_TWO_THETA, COL_D, COL_HKL, COL_INTENSITY, COL_FWHM,
 COL_SIZE) = range(7)

#: 列标题的 i18n 键（顺序即列序）
COLUMN_KEYS = (
    "peaks.col.phase", "peaks.col.two_theta", "peaks.col.d", "peaks.col.hkl",
    "peaks.col.intensity", "peaks.col.fwhm", "peaks.col.size",
)

#: 内置两相的显示名键（core 的 CifStructure.name -> 文案键）
PHASE_NAME_KEYS = {"anatase": "phase.anatase", "rutile": "phase.rutile"}

COLOR_MUTED = "#64748B"


def _cell(text: str, *, align: str = "left",
          color: str | None = None) -> QTableWidgetItem:
    """构造只读单元格（align: left / center / right）。"""
    item = QTableWidgetItem(text)
    item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
    if align == "right":
        item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    elif align == "center":
        item.setTextAlignment(Qt.AlignHCenter | Qt.AlignVCenter)
    if color:
        item.setForeground(QBrush(QColor(color)))
    return item


class MainPeaksPanel(QGroupBox):
    """两相主峰参数表（含谢乐晶粒度）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._rows: list = []          # 缓存最近一次的行数据（语言切换重绘用）
        self._wavelength: float | None = None
        box = QVBoxLayout(self)
        box.setContentsMargins(6, 6, 6, 4)
        box.setSpacing(2)

        self.table = QTableWidget(0, len(COLUMN_KEYS), self)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setShowGrid(False)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(22)
        self.table.setStyleSheet("QTableWidget { font-size:12px; }")
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Stretch)
        header.setHighlightSections(False)
        box.addWidget(self.table)

        self.lbl_note = QLabel(self)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"font-size:11px; color:{COLOR_MUTED};")
        box.addWidget(self.lbl_note)
        self.retranslate()
        self.clear()

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def set_rows(self, rows, wavelength: float | None = None) -> None:
        """按 core 的 MainPeak 列表重建表格。"""
        self._rows = list(rows or [])
        self._wavelength = wavelength
        self._render()
        self._refresh_note()
        self._sync_splitter()

    def clear(self) -> None:
        """回到空态：一行合并单元格的提示文字。"""
        self._rows = []
        self._render()
        self._sync_splitter()

    def row_count(self) -> int:
        """当前数据行数（空态为 0）——供测试与状态判断。"""
        return len(self._rows)

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def _render(self) -> None:
        table = self.table
        table.clearSpans()
        if not self._rows:
            table.setRowCount(1)
            table.setSpan(0, 0, 1, len(COLUMN_KEYS))
            table.setItem(0, 0, _cell(tr("peaks.empty")))
            table.item(0, 0).setTextAlignment(Qt.AlignCenter)
            table.item(0, 0).setForeground(QBrush(QColor(COLOR_MUTED)))
            self._sync_height()
            return
        table.setRowCount(len(self._rows))
        for i, row in enumerate(self._rows):
            muted = not getattr(row, "ok", True)
            color = COLOR_MUTED if muted else None
            table.setItem(i, COL_PHASE, _cell(self._phase_name(row.phase),
                                              color=color))
            table.setItem(i, COL_TWO_THETA,
                          _cell(f"{row.two_theta:.2f}", align="center",
                                color=color))
            table.setItem(i, COL_D, _cell(f"{row.d:.4f}", align="center",
                                          color=color))
            h, k, l = row.hkl
            table.setItem(i, COL_HKL, _cell(f"({h} {k} {l})", align="center",
                                            color=color))
            table.setItem(i, COL_INTENSITY,
                          _cell(self._fmt(row.intensity, "{:.0f}"),
                                align="center", color=color))
            table.setItem(i, COL_FWHM,
                          _cell(self._fmt(row.fwhm, "{:.3f}"),
                                align="center", color=color))
            size = row.size_nm
            table.setItem(i, COL_SIZE,
                          _cell(tr("verdict.na") if size is None
                                else f"{size:.1f}",
                                align="center", color=color))
            rel = getattr(row, "rel_intensity", float("nan"))
            tip = (f"{self._phase_name(row.phase)} ({h} {k} {l})\n"
                   f"2θ = {row.two_theta:.3f}°   d = {row.d:.4f} Å\n"
                   f"相对强度 = {rel:.1f} %（本相最强峰 = 100%）")
            for col in range(len(COLUMN_KEYS)):
                table.item(i, col).setToolTip(tip)
        self._sync_height()

    def _sync_height(self) -> None:
        """按行数给表格一个够用的最小高度，避免 10 行数据要滚动才看得全。

        QTableWidget 的 sizeHint 与行数无关（固定 256×192），只靠布局算不出
        内容高度，所以在数据变化时手动把最小高度设为「表头 + 行 × 行高」。
        """
        rows = max(1, self.table.rowCount())
        header = self.table.horizontalHeader().height() or 26
        table_h = header + 22 * rows + 4
        self.table.setMinimumHeight(table_h)
        # 空态把整块压到「一行提示 + 脚注」的高度，别让空表白占半屏；
        # 有数据时解除上限，由竖向分割条分配（见 _sync_splitter）。
        self.setMaximumHeight(16777215 if self._rows else table_h + 80)

    def _sync_splitter(self) -> None:
        """把竖向分割条调到合理位置：空态压扁本区、有数据时按内容撑开。

        只在内容状态切换（空 <-> 有数据）时动分割条，用户手动拖动过的尺寸
        不会被下一次刷新覆盖；有数据时只在当前高度不够放完所有行时才加高。
        """
        split = self.parentWidget()
        if not isinstance(split, QSplitter):
            return
        sizes = split.sizes()
        total = sum(sizes)
        if total <= 0:
            return
        if not self._rows:
            split.setSizes([max(160, total - 120), 120])
            return
        want = min(total - 200, self.table.minimumHeight() + 72)
        if want > sizes[-1]:
            split.setSizes([total - want, want])

    @staticmethod
    def _fmt(value: float, spec: str) -> str:
        """浮点格式化：缺失值（nan/inf）统一显示「—」。"""
        try:
            v = float(value)
        except (TypeError, ValueError):
            return tr("verdict.na")
        if not math.isfinite(v):
            return tr("verdict.na")
        return spec.format(v)

    def _phase_name(self, phase: str) -> str:
        """物相显示名（内置两相走 i18n；附加相直接用 CIF 名）。"""
        key = PHASE_NAME_KEYS.get(str(phase))
        return tr(key) if key else str(phase)

    def _refresh_note(self) -> None:
        """刷新脚注（波长随谱图变化时同步）。"""
        from rutana.core.phasepeak import DEFAULT_WAVELENGTH

        lam = self._wavelength or DEFAULT_WAVELENGTH
        self.lbl_note.setText(tr("peaks.note", lam=f"{lam:.4f}"))

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """语言热切换：标题 / 表头 / 缓存行 / 脚注（不重算数值）。"""
        self.setTitle(tr("peaks.title"))
        self.table.setHorizontalHeaderLabels([tr(k) for k in COLUMN_KEYS])
        self._render()
        self._refresh_note()
