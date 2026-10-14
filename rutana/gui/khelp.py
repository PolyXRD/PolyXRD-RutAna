"""「K 值说明」对话框。

用户实机反馈的核心痛点之一是「不知道 K 是什么、不知道怎么设」。
本对话框用中文 + 公式 + 使用要点把 K 讲清楚：

- K 的定义（标定曲线斜率）：``K = [I(A)/I(R)] ÷ [m(A)/m(R)]``；
- 结果换算式：``w(A) = 1/[1 + K·I(R)/I(A)] × 100%``；
- K 与仪器条件强相关、必须同条件标定；
- 典型量级参考（本项目真实数据实测 ≈ 1.22）；
- 获取途径：本界面的「K 标定向导…」，或打开完整说明文档 docs/UI_GUIDE.md。
"""

from __future__ import annotations

import html as html_mod
from pathlib import Path

from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from rutana.gui.resources import app_root
from rutana.i18n import tr

#: 本地说明文档相对路径
GUIDE_RELATIVE = Path("docs") / "UI_GUIDE.md"

#: 公式块样式（等宽 + 灰底，突出显示）
_FORMULA_CSS = (
    "background:#F8FAFC; border:1px solid #E2E8F0; border-radius:6px;"
    "padding:6px 10px; font-family:Consolas,'Courier New',monospace;"
    "font-size:13px; color:#0F172A;"
)


def guide_path() -> Path:
    """返回 docs/UI_GUIDE.md 的绝对路径。"""
    return app_root() / GUIDE_RELATIVE


class KHelpDialog(QDialog):
    """K 值说明对话框（正文走 i18n，支持三语与运行时热切换）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.resize(620, 520)
        root = QVBoxLayout(self)

        self.browser = QTextBrowser(self)
        self.browser.setOpenExternalLinks(True)
        root.addWidget(self.browser, 1)

        row = QHBoxLayout()
        self.btn_doc = QPushButton(self)
        self.btn_doc.clicked.connect(self._open_guide)
        self.btn_close = QPushButton(self)
        self.btn_close.clicked.connect(self.accept)
        row.addWidget(self.btn_doc)
        row.addStretch(1)
        row.addWidget(self.btn_close)
        root.addLayout(row)
        self.retranslate()

    # ------------------------------------------------------------------ #
    def open_guide(self) -> bool:
        """尝试用系统默认程序打开 docs/UI_GUIDE.md；不存在返回 False。"""
        path = guide_path()
        if not path.exists():
            return False
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(path)))
        return True

    def toPlainText(self) -> str:  # noqa: N802 - 与 Qt 命名一致，测试断言用
        """返回正文纯文本（供冒烟测试断言关键内容）。"""
        return self.browser.toPlainText()

    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """语言切换后刷新标题、按钮与正文。"""
        self.setWindowTitle(tr("khelp.title"))
        self.btn_doc.setText(tr("khelp.open_doc"))
        self.btn_close.setText(tr("dialog.close"))
        self.browser.setHtml(self._html())

    def _open_guide(self) -> None:
        path = guide_path()
        if not path.exists():
            QMessageBox.information(self, tr("msg.info"),
                                    tr("khelp.doc_missing", path=str(path)))

    # ------------------------------------------------------------------ #
    # 内部：富文本拼装
    # ------------------------------------------------------------------ #
    def _html(self) -> str:
        def esc(text: str) -> str:
            return html_mod.escape(text, quote=False)

        def h(text: str) -> str:
            return f"<h3 style='color:#0284C7; font-size:14px; margin:12px 0 4px;'>{esc(text)}</h3>"

        def p(text: str) -> str:
            return f"<p style='margin:4px 0; line-height:1.7;'>{esc(text)}</p>"

        def formula(text: str) -> str:
            return f"<p style='{_FORMULA_CSS}'>{esc(text)}</p>"

        return (
            f"{h(tr('khelp.h1'))}{p(tr('khelp.p1'))}{formula(tr('khelp.formula_k'))}"
            f"{h(tr('khelp.h2'))}{p(tr('khelp.p2'))}{formula(tr('khelp.formula_wa'))}"
            f"{h(tr('khelp.h3'))}{p(tr('khelp.p3'))}"
            f"<p style='margin:6px 0; line-height:1.7; color:#B45309;'>{esc(tr('khelp.typical'))}</p>"
            f"{h(tr('khelp.h4'))}{p(tr('khelp.p4'))}"
        )
