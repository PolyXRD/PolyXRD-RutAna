"""模态「忙」对话框（BusyDialog）。

计算/拟合/标定期间弹出：动态阶段文案 + 百分比进度条（core 上报进度时）
+ 已用时 + 可选「第 N 代 / Rwp」实时行 + 可选取消按钮。

设计要点：

1. **模态但不停机**：对话框在 Qt 嵌套事件循环中运行，UI 持续刷新；
   真正的计算放在 :mod:`rutana.gui.workers` 的后台线程，主线程只更新 UI，
   因此不存在"冻屏"（这是用户最难接受的失败模式）。
2. **默认不可关闭**：隐藏标题栏关闭按钮并吞掉 Esc/关闭事件，
   避免用户在计算中途关掉窗口导致结果丢失；
   只有当后台任务声明支持取消（core 上报了 ``cancel_cb``）时才显示「取消」。
3. **降级友好**：core 未上报百分比时进度条自动切不确定模式（转圈），
   文案保持最后一阶段提示，并给出「进度未知」说明行。
"""

from __future__ import annotations

import time

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QCloseEvent, QKeyEvent
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rutana.i18n import tr

#: 已用时刷新间隔（毫秒）
TICK_MS = 500

#: 判定/警告配色（与家族视觉一致）
COLOR_GOOD = "#16A34A"
COLOR_BAD = "#DC2626"
COLOR_MUTED = "#64748B"


def fmt_elapsed(seconds: float) -> str:
    """把秒数格式化为「12 秒 / 1 分 05 秒」的人类可读文本。"""
    total = max(0, int(round(seconds)))
    if total < 60:
        return f"{total} 秒"
    minute, sec = divmod(total, 60)
    if minute < 60:
        return f"{minute} 分 {sec:02d} 秒"
    hour, minute = divmod(minute, 60)
    return f"{hour} 时 {minute:02d} 分 {sec:02d} 秒"


class BusyDialog(QDialog):
    """不可关闭式忙对话框（可选取消）。"""

    #: 用户点击「取消」
    canceled = Signal()

    def __init__(self, parent: QWidget | None = None, *, title: str | None = None,
                 cancellable: bool = False) -> None:
        super().__init__(parent)
        self._title_key_text = title or tr("busy.title")
        self._cancellable = bool(cancellable)
        self._finished = False
        self._t0 = time.monotonic()

        self.setModal(True)
        self.setWindowTitle(self._title_key_text)
        # 隐藏标题栏关闭按钮与帮助按钮
        self.setWindowFlag(Qt.WindowCloseButtonHint, False)
        self.setWindowFlag(Qt.WindowContextHelpButtonHint, False)
        self.setMinimumWidth(380)

        root = QVBoxLayout(self)
        self.lbl_msg = QLabel(tr("busy.load"), self)
        self.lbl_msg.setWordWrap(True)
        self.lbl_msg.setStyleSheet("font-size:14px; font-weight:600; color:#0F172A;")
        root.addWidget(self.lbl_msg)

        self.bar = QProgressBar(self)
        self.bar.setRange(0, 0)  # 默认不确定模式
        self.bar.setTextVisible(True)
        self.bar.setFormat("%p%")
        root.addWidget(self.bar)

        self.lbl_iter = QLabel("", self)
        self.lbl_iter.setWordWrap(True)
        self.lbl_iter.setStyleSheet(f"font-size:12px; color:{COLOR_MUTED};")
        self.lbl_iter.hide()
        root.addWidget(self.lbl_iter)

        self.lbl_elapsed = QLabel(tr("busy.elapsed", t=fmt_elapsed(0.0)), self)
        self.lbl_elapsed.setStyleSheet(f"font-size:12px; color:{COLOR_MUTED};")
        root.addWidget(self.lbl_elapsed)

        self.lbl_note = QLabel(tr("busy.degraded"), self)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"font-size:11px; color:{COLOR_MUTED};")
        self.lbl_note.hide()
        root.addWidget(self.lbl_note)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_cancel = QPushButton(tr("busy.cancel"), self)
        self.btn_cancel.clicked.connect(self._on_cancel)
        self.btn_cancel.setVisible(self._cancellable)
        btn_row.addWidget(self.btn_cancel)
        root.addLayout(btn_row)

        self._timer = QTimer(self)
        self._timer.setInterval(TICK_MS)
        self._timer.timeout.connect(self._tick)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 状态更新（由后台线程信号驱动，均在主线程执行）
    # ------------------------------------------------------------------ #
    def start_timer(self) -> None:
        """开始计时（run_busy_task 会在线程启动后调用）。"""
        self._t0 = time.monotonic()
        self._timer.start()

    def set_message(self, text: str, pct: int = -1) -> None:
        """更新阶段文案；pct>=0 切确定百分比，否则保持不确定模式。"""
        self.lbl_msg.setText(str(text))
        p = -1 if pct is None else int(pct)
        if p >= 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(max(0, min(100, p)))
        else:
            self.bar.setRange(0, 0)
        QApplication.processEvents()

    def set_iteration(self, gen: int, rwp: float) -> None:
        """实时显示「第 N 代 / Rwp=x.xx%」行（B 法）。"""
        self.lbl_iter.setText(tr("busy.refine", gen=int(gen), rwp=float(rwp)))
        self.lbl_iter.show()
        QApplication.processEvents()

    def set_degraded(self, degraded: bool) -> None:
        """core 不上报细粒度进度时显示说明行。"""
        self.lbl_note.setVisible(bool(degraded))
        QApplication.processEvents()

    def set_indeterminate_message(self, text: str) -> None:
        """只换文案并保持不确定模式（降级路径使用）。"""
        self.set_message(str(text), -1)

    def finish(self) -> None:
        """收尾气：停表并关闭对话框（幂等，可重复调用）。"""
        if self._finished:
            return
        self._finished = True
        self._timer.stop()
        self.accept()

    def elapsed_seconds(self) -> float:
        """返回自 start_timer 以来的秒数。"""
        return time.monotonic() - self._t0

    def elapsed_text(self) -> str:
        """返回「已用时 …」的本地化显示文案。"""
        return tr("busy.elapsed", t=fmt_elapsed(self.elapsed_seconds()))

    # ------------------------------------------------------------------ #
    # 取消
    # ------------------------------------------------------------------ #
    def cancellable(self) -> bool:
        """是否允许用户取消（取决于 core 是否支持取消回调）。"""
        return self._cancellable

    def mark_canceling(self) -> None:
        """点击取消后立即给出反馈并禁用按钮（防重复触发）。"""
        self.btn_cancel.setEnabled(False)
        self.btn_cancel.setText(tr("busy.canceling"))
        QApplication.processEvents()

    # ------------------------------------------------------------------ #
    # 多语言 / 事件覆写
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.setWindowTitle(self._title_key_text)
        self.btn_cancel.setText(
            tr("busy.canceling") if not self.btn_cancel.isEnabled()
            and self._cancellable else tr("busy.cancel"))
        self.lbl_note.setText(tr("busy.degraded"))
        self._tick()

    def _tick(self) -> None:
        self.lbl_elapsed.setText(self.elapsed_text())

    def _on_cancel(self) -> None:
        self.mark_canceling()
        self.canceled.emit()

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802 - Qt 命名约定
        """屏蔽 Esc（不可关闭式）；支持取消时 Esc 等价于点「取消」。"""
        if event.key() == Qt.Key_Escape:
            if self._cancellable and self.btn_cancel.isEnabled():
                self._on_cancel()
            event.ignore()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802 - Qt 命名约定
        """非收尾气路径的关闭请求一律忽略（防中途关闭丢失结果）。"""
        if self._finished:
            super().closeEvent(event)
            return
        event.ignore()
