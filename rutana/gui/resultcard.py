"""结果卡：键值行 + 好/坏配色 + 运行时刷新。

从 panels 拆出以控制单文件规模；A 法与 B 法共用同一实现，
保证「结果好坏一眼可见」的视觉规则在全界面保持一致：

- ``good`` 绿色（#16A34A）：合格 / 拟合良好；
- ``bad`` 红色（#DC2626）：超差 / 拟合不佳；
- ``warn`` 黄色（#CA8A04）：提示性告警（如 R² 偏低）；
- ``None`` 默认深色：中性数值。
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtWidgets import QGroupBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from rutana.i18n import tr

COLOR_DEFAULT = "#0F172A"
COLOR_GOOD = "#16A34A"
COLOR_BAD = "#DC2626"
COLOR_WARN = "#CA8A04"
COLOR_MUTED = "#64748B"

#: 语义 level -> 颜色
LEVEL_COLORS = {
    None: COLOR_DEFAULT,
    "neutral": COLOR_DEFAULT,
    "good": COLOR_GOOD,
    "bad": COLOR_BAD,
    "warn": COLOR_WARN,
    "muted": COLOR_MUTED,
}


class ResultCard(QGroupBox):
    """一组「标签：值」行；行由 i18n 键直接驱动，``retranslate`` 热切换语言。"""

    def __init__(self, keys: Sequence[str], parent: QWidget | None = None,
                 *, title_key: str = "") -> None:
        super().__init__(parent)
        self._keys: list[str] = list(keys)
        self._title_key = title_key
        #: key -> (标签控件, 值控件)
        self.rows: dict[str, tuple[QLabel, QLabel]] = {}
        box = QVBoxLayout(self)
        for key in self._keys:
            lab = QLabel(key, self)
            lab.setToolTip(key)
            val = QLabel(tr("verdict.na"), self)
            val.setStyleSheet("font-weight:600;")
            row = QHBoxLayout()
            row.addWidget(lab)
            row.addStretch(1)
            row.addWidget(val)
            box.addLayout(row)
            self.rows[key] = (lab, val)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 数据写入
    # ------------------------------------------------------------------ #
    def keys(self) -> list[str]:
        """返回全部行键（顺序与构造时一致）。"""
        return list(self._keys)

    def has_row(self, key: str) -> bool:
        """是否存在指定行。"""
        return key in self.rows

    def set_value(self, key: str, text: str, level: str | None = None,
                  *, visible: bool = True) -> None:
        """写入一行：text 为显示文本，level 决定配色。"""
        if key not in self.rows:
            raise KeyError(f"结果卡无此行: {key}")
        _lab, val = self.rows[key]
        val.setText(str(text))
        color = LEVEL_COLORS.get(level, COLOR_DEFAULT)
        val.setStyleSheet(f"font-weight:600; color:{color};")
        val.setVisible(visible)
        self.rows[key][0].setVisible(visible)

    def value(self, key: str) -> str:
        """读取某行当前显示文本。"""
        return self.rows[key][1].text()

    def clear(self) -> None:
        """全部行复位为「—」。"""
        for key in self._keys:
            self.set_value(key, tr("verdict.na"))

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        if self._title_key:
            self.setTitle(tr(self._title_key))
        for key, (lab, _val) in self.rows.items():
            lab.setText(tr(key) + "：")
