"""K 标定向导用的表格控件（显示层）。

从 :mod:`rutana.gui.kwizard` 拆出（单文件 ≤400 行约束）。

列序固定为：谱图文件 / w(金红石型)% / m(A)/m(R) / I(A)/I(R) / 状态。
本控件只负责把 ``rows`` 数据渲染成表格并回传用户编辑的 w(R) 值，
业务逻辑（测量、拟合、存档）仍在向导对话框内。
"""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
    QWidget,
)

from rutana.i18n import tr

#: 表格列序号
COL_FILE, COL_WR, COL_MR, COL_IR, COL_STATUS = range(5)

#: 状态文本颜色
COLOR_OK = "#16A34A"
COLOR_FAIL = "#DC2626"
COLOR_PENDING = "#64748B"


class CalibTable(QTableWidget):
    """标准混合样表格：渲染 ``rows`` 并把配比编辑回传为信号。

    配比两种录入方式都支持（用户按手头数据任选其一）：

    - 直接填 ``w(金红石型) / %`` -> :attr:`wr_changed`；
    - 直接填 ``m(A)/m(R)``       -> :attr:`mr_changed`（由表格反算 w(R)）。
    """

    #: (行号, 新的 w(金红石型)%) —— 用户手工修改质量分数
    wr_changed = Signal(int, float)
    #: (行号, 新的 m(A)/m(R)) —— 用户手工修改质量比
    mr_changed = Signal(int, float)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(0, 5, parent)
        self._loading = False
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.AllEditTriggers)
        self.verticalHeader().setVisible(False)
        header = self.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.ResizeToContents)
        header.setSectionResizeMode(COL_FILE, QHeaderView.Stretch)
        self.itemChanged.connect(self._on_item_changed)
        self.retranslate()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """刷新表头（语言热切换）。"""
        self.setHorizontalHeaderLabels([
            tr("kwizard.col.file"), tr("kwizard.col.wr"), tr("kwizard.col.mr"),
            tr("kwizard.col.ir"), tr("kwizard.col.status")])

    def render_rows(self, rows: list[dict]) -> None:
        """按数据行重建表格（编辑回调期间静默，避免递归）。"""
        self._loading = True
        try:
            self.setRowCount(len(rows))
            for r, row in enumerate(rows):
                self._item(r, COL_FILE, Path(str(row.get("file", ""))).name,
                           tip=str(row.get("file", "")), editable=False)
                self._item(r, COL_WR, f"{float(row.get('wr', 0.0)):.2f}",
                           editable=True)
                rm = row.get("ratio_m")
                self._item(r, COL_MR, f"{rm:.4f}" if rm else tr("verdict.na"),
                           editable=True)
                ri = row.get("ratio_i")
                self._item(r, COL_IR, f"{ri:.4f}" if ri else tr("verdict.na"),
                           editable=False)
                status, color = self._status(row)
                item = self._item(r, COL_STATUS, status, editable=False)
                item.setToolTip(str(row.get("message", "")) or status)
                item.setForeground(QBrush(QColor(color)))
        finally:
            self._loading = False

    # ------------------------------------------------------------------ #
    @staticmethod
    def _status(row: dict) -> tuple[str, str]:
        """一行 -> (状态文案, 颜色)。"""
        if row.get("ok"):
            return tr("kwizard.status.ok"), COLOR_OK
        if row.get("message"):
            return tr("kwizard.status.fail"), COLOR_FAIL
        return tr("kwizard.status.pending"), COLOR_PENDING

    def _item(self, row: int, col: int, text: str, *, tip: str = "",
              editable: bool = True) -> QTableWidgetItem:
        """写入一个单元格（不可编辑项去掉编辑标志）。"""
        item = QTableWidgetItem(text)
        item.setToolTip(tip or text)
        if not editable:
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
        self.setItem(row, col, item)
        return item

    def _on_item_changed(self, item: QTableWidgetItem) -> None:
        """用户编辑配比单元格 -> 解析并发出对应信号。"""
        if self._loading or item.column() not in (COL_WR, COL_MR):
            return
        text = item.text().replace("，", ".").replace(",", ".")
        try:
            value = float(text)
        except ValueError:
            return
        if item.column() == COL_WR:
            self.wr_changed.emit(item.row(), value)
        else:
            self.mr_changed.emit(item.row(), value)
