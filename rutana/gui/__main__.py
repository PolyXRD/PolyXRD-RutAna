"""GUI 入口：``python -m rutana.gui``。

启动流程：QSplashScreen（resources/splash-screen.png，1.2 s 后自动关闭）
→ 主窗口。资源缺失时优雅降级（不阻塞启动）。
"""

from __future__ import annotations

import sys

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QPixmap
from PySide6.QtWidgets import QApplication, QSplashScreen

from rutana.version import APP_NAME
from rutana.gui.resources import resource_path

#: 启动图展示时长（毫秒）
SPLASH_MS = 1200


def main() -> int:
    """创建应用、启动图与主窗口，进入事件循环。"""
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")

    icon_path = resource_path("app-icon.png")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    # 启动图（资源缺失时跳过）
    splash = None
    splash_path = resource_path("splash-screen.png")
    if splash_path.exists():
        pixmap = QPixmap(str(splash_path))
        if not pixmap.isNull():
            splash = QSplashScreen(pixmap)
            splash.setWindowFlag(Qt.WindowStaysOnTopHint, True)
            splash.show()
            app.processEvents()

    # 延迟导入主窗口，让启动图先出现
    from rutana.gui.main_window import MainWindow

    window = MainWindow()
    window.show()
    if splash is not None:
        QTimer.singleShot(SPLASH_MS, splash.close)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
