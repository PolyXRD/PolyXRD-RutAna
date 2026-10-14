"""GUI 冒烟测试。

用 ``unittest.mock.patch`` 桩掉 ``rutana.gui.services`` 的 core 依赖，
保证 core 算法未就绪时本测试也能全绿。运行环境强制
``QT_QPA_PLATFORM=offscreen``（必须在导入 PySide6 之前设置）。
"""

from __future__ import annotations

import os
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 不可用，跳过 GUI 冒烟测试")

from PySide6.QtWidgets import QApplication  # noqa: E402

from rutana.gui import services  # noqa: E402
from rutana.gui.dialogs import AboutDialog, CopyrightDialog  # noqa: E402
from rutana.gui.main_window import MainWindow  # noqa: E402
from rutana.i18n import current_language, set_language, tr  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    """模块级 QApplication（复用实例，offscreen 平台）。"""
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def stub_core():
    """桩掉 services 的全部 core 依赖——core 未就绪也能构造/操作主窗口。"""
    with mock.patch.object(services, "load_pattern", mock.MagicMock(name="load_pattern")), \
         mock.patch.object(services, "run_method_a", mock.MagicMock(name="run_method_a")), \
         mock.patch.object(services, "run_method_b", mock.MagicMock(name="run_method_b")), \
         mock.patch.object(services, "calibrate_from_points",
                           mock.MagicMock(name="calibrate_from_points")), \
         mock.patch.object(services, "measure_peak", mock.MagicMock(name="measure_peak")), \
         mock.patch.object(services, "compute_ratio", mock.MagicMock(name="compute_ratio")):
        yield


def test_services_module_lazy():
    """services 模块可独立导入（顶层不触碰 rutana.core）。"""
    assert callable(services.load_pattern)
    assert callable(services.run_method_a)
    assert callable(services.run_method_b)
    assert issubclass(services.CoreUnavailableError, RuntimeError)


def test_main_window_construct(qapp, stub_core):
    """主窗口可构造（含菜单/三栏布局/状态栏），并可正常关闭。"""
    w = MainWindow()
    assert w.windowTitle()
    assert w.menuBar().actions(), "应有三条菜单"
    assert w.tabs.a_panel is not None and w.tabs.b_panel is not None
    w.close()


def test_language_switch_updates_ui(qapp, stub_core):
    """语言切换后 retranslateUi 立即生效（按钮/窗口标题随语言变化）。"""
    w = MainWindow()
    try:
        set_language("zh_CN")
        w.retranslateUi()
        zh_btn = w.tabs.a_panel.btn_compute.text()
        zh_title = w.windowTitle()
        assert zh_btn == tr("a.compute")

        set_language("en_US")
        w.retranslateUi()
        en_btn = w.tabs.a_panel.btn_compute.text()
        assert en_btn == tr("a.compute")
        assert en_btn != zh_btn, "切换语言后按钮文案应变化"
        assert w.windowTitle() != zh_title, "切换语言后窗口标题应变化"

        set_language("ja_JP")
        w.retranslateUi()
        assert w.tabs.a_panel.btn_compute.text() == tr("a.compute")
    finally:
        set_language("zh_CN")
        w.close()


def test_copyright_dialog_content(qapp):
    """版权对话框（双语要点）包含联系方式与 Academic 关键词。"""
    set_language("zh_CN")
    dlg = CopyrightDialog()
    text = dlg.toPlainText()
    assert "sshztx@outlook.com" in text
    assert "Academic" in text
    assert "双许可" in text, "中文要点应包含『双许可』"


def test_about_dialog_content(qapp):
    """关于对话框包含版本与三个特性 chip。"""
    set_language("zh_CN")
    dlg = AboutDialog()
    texts = [c.text() for c in dlg.findChildren(type(dlg))]
    joined = " ".join(t for t in texts if t) if texts else ""
    # 关于对话框自身标签
    from PySide6.QtWidgets import QLabel

    labels = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert "v0.1.0" in labels or "v0.1.0" in joined
    for chip in ("chip_a", "chip_b", "chip_std"):
        assert tr(f"dialog.about.{chip}") in labels
    dlg.close()
    assert current_language() == "zh_CN"
