"""右侧「A 法 / B 法」选项卡容器。

两个面板本体分别在 :mod:`rutana.gui.panels`（A 法）与
:mod:`rutana.gui.panels_b`（B 法，v1.2.0 按单文件 ≤400 行约束拆出）；
本模块只做容器与语言热切换转发。
"""

from __future__ import annotations

from PySide6.QtWidgets import QTabWidget, QWidget

from rutana.gui.panels import APanel
from rutana.gui.panels_b import BPanel
from rutana.i18n import tr


class MethodTabs(QTabWidget):
    """右侧参数/结果选项卡容器（A 法 / B 法）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.a_panel = APanel(self)
        self.b_panel = BPanel(self)
        self.addTab(self.a_panel, "")
        self.addTab(self.b_panel, "")
        self.retranslate()

    def retranslate(self) -> None:
        """语言切换后刷新选项卡标题与两个面板。"""
        self.setTabText(0, tr("tab.a"))
        self.setTabText(1, tr("tab.b"))
        self.a_panel.retranslate()
        self.b_panel.retranslate()
