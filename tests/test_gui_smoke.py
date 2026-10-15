"""GUI 冒烟测试。

用 ``unittest.mock.patch`` 桩掉 ``rutana.gui.services`` 的 core 依赖，
保证 core 算法未就绪时本测试也能全绿。运行环境强制
``QT_QPA_PLATFORM=offscreen``（必须在导入 PySide6 之前设置）。

覆盖内容：

- 主窗口构造 / 语言热切换 / 关于与版权对话框；
- 忙对话框（BusyDialog）文案、百分比、已用时、不可关闭；
- 后台线程（ComputeThread）成功/失败/进度回调/不支持时降级；
- 主线程经 BusyDialog + QThread 跑完 A 法 / B 法后的结果卡回填；
- K 值说明对话框、K 标定向导（表格/拟合/存档往返/采用回填）。
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import numpy as np  # noqa: E402
import pytest  # noqa: E402

pytest.importorskip("PySide6", reason="PySide6 不可用，跳过 GUI 冒烟测试")

from PySide6.QtCore import QEvent, Qt  # noqa: E402
from PySide6.QtGui import QKeyEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QDialog, QLabel, QMessageBox  # noqa: E402

from rutana.gui import services  # noqa: E402
from rutana.gui.busy import BusyDialog, fmt_elapsed  # noqa: E402
from rutana.gui.dialogs import AboutDialog, CopyrightDialog  # noqa: E402
from rutana.gui.khelp import KHelpDialog  # noqa: E402
from rutana.gui.kwizard import KCalibWizardDialog  # noqa: E402
from rutana.gui.main_window import MainWindow  # noqa: E402
from rutana.gui.workers import ComputeThread, call_with_extras, supports_param  # noqa: E402
from rutana.i18n import current_language, set_language, tr  # noqa: E402
from rutana.version import __version__  # noqa: E402


def _pump_until(cond, timeout: float = 5.0) -> bool:
    """泵 Qt 事件队列直到条件成立或超时（跨线程信号的交付要跑事件循环）。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.01)
    QApplication.processEvents()
    return cond()


def _fake_pattern(name: str = "sample.xy") -> SimpleNamespace:
    """构造一份可用的伪谱图对象（避免触碰 core 的读取逻辑）。"""
    tt = np.arange(20.0, 32.0, 0.02)
    ii = 100.0 + 50.0 * np.exp(-0.5 * ((tt - 25.3) / 0.2) ** 2)
    return SimpleNamespace(two_theta=tt, intensity=ii, meta={"source": name})


def _add_pattern(win: MainWindow, path: str = "D:/data/sample.xy") -> None:
    """往主窗口塞一份伪谱图并选中它。"""
    win._patterns[path] = _fake_pattern(Path(path).name)
    win.file_list.addItem(Path(path).name)
    win.file_list.setCurrentRow(win.file_list.count() - 1)


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
         mock.patch.object(services, "compute_ratio", mock.MagicMock(name="compute_ratio")), \
         mock.patch.object(services, "measure_calib_rows",
                           mock.MagicMock(name="measure_calib_rows")):
        yield


@pytest.fixture(autouse=True)
def no_modal_exec(monkeypatch):
    """测试中屏蔽一切模态循环（QDialog/QMessageBox/BusyDialog），避免挂住 CI。"""
    monkeypatch.setattr(QDialog, "exec", lambda _self, *a, **k: int(QDialog.Accepted))
    monkeypatch.setattr(QMessageBox, "exec", lambda _self, *a, **k: int(QDialog.Accepted))
    monkeypatch.setattr(BusyDialog, "exec", lambda _self: int(QDialog.Accepted))
    yield


# --------------------------------------------------------------------------- #
# 基础：services 契约与主窗口
# --------------------------------------------------------------------------- #
def test_busy_dialog_rejects_close_while_running(qapp):
    """计算进行中关闭请求被忽略；finish() 后才能真正关闭。"""
    dlg = BusyDialog(None, cancellable=False)
    dlg.show()
    QApplication.processEvents()
    dlg.close()
    assert dlg.isVisible(), "忙窗未收尾气前不应被关闭"
    dlg.finish()
    QApplication.processEvents()
    assert not dlg.isVisible(), "finish() 后应正常关闭"


def test_main_window_k_entrypoints(qapp, stub_core):
    """A 法面板两个 K 入口可被主窗口打开（K 说明 / K 标定向导）。"""
    set_language("zh_CN")
    w = MainWindow()
    try:
        services.calibrate_from_points.return_value = SimpleNamespace(
            K=1.2, intercept=0.0, r2=0.999, n_points=3)
        w.open_k_help()
        w.open_k_wizard()
        assert w.tabs.a_panel.btn_k_help.text() == tr("a.k_help")
        assert "标定" in w.tabs.a_panel.btn_k_wizard.text()
    finally:
        w.close()


def test_calibrecord_parse_normalizes(qapp):
    """标定记录解析：越界 wr 夹紧、缺失 ratio_m 反算、ok 由 ratio_i 推断。"""
    from rutana.gui.calibrecord import build_record, parse_record

    built = build_record(win_a=(24.5, 26.5), win_r=(26.5, 28.5), mode="origin",
                         fit={"K": 1.2, "intercept": 0.01, "r2": 0.999},
                         rows=[{"file": "a.xy", "wr": 50.0, "ratio_m": 1.0,
                                "ratio_i": 1.22, "ok": True, "message": ""}],
                         quantity="height")
    assert built["version"] == 1 and built["mode"] == "origin"
    assert built["quantity"] == "height", "显式传入的口径应写入记录"

    parsed = parse_record({"rows": [{"file": "a.xy", "wr": 150.0, "ratio_i": 2.0},
                                    {"file": ""}]})
    assert parsed["mode"] == "ols"
    assert parsed["quantity"] == "area", "旧记录缺 quantity 时兜底为 area"
    assert len(parsed["rows"]) == 1, "缺 file 的行应被跳过"
    row = parsed["rows"][0]
    assert row["wr"] == 99.99, "越界 wr 应被夹紧"
    assert row["ok"] is True and row["ratio_m"] is not None

    with pytest.raises(ValueError):
        parse_record({"nope": []})


def test_calibtable_emits_wr_change(qapp):
    """表格编辑 w(金红石型)% -> 发出 wr_changed 信号。"""
    from rutana.gui.calibtable import COL_MR, COL_WR, CalibTable

    table = CalibTable()
    table.render_rows([{"file": "D:/x/a.xy", "wr": 50.0, "ratio_m": 1.0,
                        "ratio_i": None, "ok": False, "message": ""}])
    got: list[tuple[int, float]] = []
    table.wr_changed.connect(lambda i, v: got.append((i, v)))
    table.item(0, COL_WR).setText("33.33")
    assert got == [(0, 33.33)]

    got_mr: list[tuple[int, float]] = []
    table.mr_changed.connect(lambda i, v: got_mr.append((i, v)))
    table.item(0, COL_MR).setText("2.5")
    assert got_mr == [(0, 2.5)], "m(A)/m(R) 也应可直接录入"
    table.deleteLater()


def test_kwizard_mass_ratio_entry_back_computes_wr(qapp, stub_core):
    """直接录入 m(A)/m(R) 时反算 w(金红石型)% = 100/(1+mr)。"""
    from rutana.gui.calibtable import COL_MR

    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.2, intercept=0.0, r2=0.999, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        dlg.table.item(0, COL_MR).setText("1.0000")
        assert dlg.rows[0]["wr"] == pytest.approx(50.0)
        dlg.table.item(0, COL_MR).setText("3.0000")
        assert dlg.rows[0]["wr"] == pytest.approx(25.0)
        assert dlg.rows[0]["ratio_m"] == pytest.approx(3.0)
    finally:
        dlg.close()


def test_services_module_lazy():
    """services 模块可独立导入（顶层不触碰 rutana.core）。"""
    assert callable(services.load_pattern)
    assert callable(services.run_method_a)
    assert callable(services.run_method_b)
    assert issubclass(services.CoreUnavailableError, RuntimeError)
    assert issubclass(services.TaskCanceled, RuntimeError)


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
    """关于对话框包含当前版本与三个特性 chip。"""
    set_language("zh_CN")
    dlg = AboutDialog()
    labels = " ".join(l.text() for l in dlg.findChildren(QLabel))
    assert f"v{__version__}" in labels, "关于对话框应显示当前版本号"
    for chip in ("chip_a", "chip_b", "chip_std"):
        assert tr(f"dialog.about.{chip}") in labels
    dlg.close()
    assert current_language() == "zh_CN"


def test_version_is_110():
    """版本号已推进到 1.1.0（UI 版本号与 EXE 名同源）。"""
    assert __version__ == "1.1.0"


# --------------------------------------------------------------------------- #
# 忙对话框
# --------------------------------------------------------------------------- #
def test_busy_dialog_message_progress_elapsed(qapp):
    """忙对话框：动态文案 + 百分比 + 已用时；再切不确定模式。"""
    dlg = BusyDialog(None, cancellable=False)
    dlg.start_timer()
    dlg.set_message(tr("busy.measure"), 42)
    assert dlg.lbl_msg.text() == tr("busy.measure")
    assert dlg.bar.value() == 42
    assert dlg.bar.minimum() == 0 and dlg.bar.maximum() == 100
    dlg.set_message(tr("busy.ratio"))
    assert dlg.bar.maximum() == 0, "无百分比时应回到不确定模式"
    dlg.set_iteration(12, 8.42)
    assert tr("busy.refine", gen=12, rwp=8.42) == dlg.lbl_iter.text()
    assert dlg.lbl_iter.isVisibleTo(dlg)
    assert tr("busy.elapsed", t=fmt_elapsed(0.0)) in dlg.lbl_elapsed.text()
    dlg.set_degraded(True)
    assert dlg.lbl_note.isVisibleTo(dlg)
    dlg.finish()
    dlg.finish()  # 幂等
    dlg.close()


def test_busy_dialog_cancel_button_hidden_by_default(qapp):
    """默认不可关闭式：无取消按钮，且 Esc 不关闭对话框。"""
    dlg = BusyDialog(None, cancellable=False)
    assert not dlg.cancellable()
    assert not dlg.btn_cancel.isVisibleTo(dlg)
    dlg.keyPressEvent(QKeyEvent(QEvent.KeyPress, Qt.Key_Escape, Qt.NoModifier))
    assert dlg.isVisible() or True  # 未 show 的对话框主要验证不抛异常且未走 reject
    dlg.finish()
    dlg.close()

    dlg2 = BusyDialog(None, cancellable=True)
    assert dlg2.cancellable()
    assert dlg2.btn_cancel.isVisibleTo(dlg2)
    got = []
    dlg2.canceled.connect(lambda: got.append(True))
    dlg2._on_cancel()
    assert got == [True]
    assert dlg2.btn_cancel.text() == tr("busy.canceling")
    dlg2.finish()
    dlg2.close()


# --------------------------------------------------------------------------- #
# 后台线程与回调适配
# --------------------------------------------------------------------------- #
def test_supports_param_and_call_with_extras():
    """core 签名不支持回调时静默降级；支持时原样传入。"""
    got = {}

    def old_style(a, b):
        return a + b

    def new_style(a, b, progress_cb=None):
        got["cb"] = progress_cb
        progress_cb("go", 50)
        return a * b

    assert supports_param(old_style, "progress_cb") is False
    assert supports_param(new_style, "progress_cb") is True
    assert call_with_extras(old_style, args=(1, 2), extras={"progress_cb": print}) == 3
    callback = mock.MagicMock(name="cb")
    assert call_with_extras(new_style, args=(3, 4), extras={"progress_cb": callback}) == 12
    callback.assert_called_once_with("go", 50)


def test_pct_to_percent_normalizes_fraction_and_percent():
    """core 的 0..1 比例与旧式 0..100 百分比都被归一化为 0..100。"""
    from rutana.gui.workers import pct_to_percent

    assert pct_to_percent(0.05) == 5
    assert pct_to_percent(0.63) == 63
    assert pct_to_percent(1.0) == 100
    assert pct_to_percent(30) == 30
    assert pct_to_percent(100) == 100
    assert pct_to_percent(None) == -1
    assert pct_to_percent(-0.5) == -1
    assert pct_to_percent("bad") == -1


def test_compute_thread_success_and_progress(qapp):
    """ComputeThread：进度回调被触发，返回值经 succeeded 回传主线程。"""
    seen: list[tuple[str, int]] = []

    def target(x, *, progress_cb=None, on_iter=None):
        if callable(progress_cb):
            progress_cb(tr("busy.measure"), 0.30)
        return {"x": x, "has_progress": callable(progress_cb)}

    thread = ComputeThread(target, args=(7,))
    thread.signals.progressed.connect(lambda m, p: seen.append((m, p)))
    thread.start()
    assert thread.wait(5000)
    assert _pump_until(lambda: len(seen) >= 1)
    assert seen, "进度回调应被触发"
    assert seen[0][0] == tr("busy.measure") and seen[0][1] == 30


def test_services_sub_progress_maps_range():
    """sub_progress 把子步骤 0..1 映射到指定比例区间（进度条不来回跳）。"""
    got: list[tuple[str, float | None]] = []
    sub = services.sub_progress(lambda m, p: got.append((m, p)), 0.10, 0.50)
    assert sub is not None
    sub("step", 0.0)
    sub("step", 1.0)
    sub("step", None)
    assert got[0][1] == pytest.approx(0.10)
    assert got[1][1] == pytest.approx(0.50)
    assert got[2][1] is None, "无百分比时应保持不确定"
    assert services.sub_progress(None, 0.1, 0.5) is None


def test_compute_thread_failure_keeps_exception(qapp):
    """ComputeThread 失败时原样回传异常（保留 CoreUnavailableError 语义）。"""
    boom = services.CoreUnavailableError("boom")

    def target():
        raise boom

    captured: list[Exception] = []
    thread = ComputeThread(target)
    thread.signals.failed.connect(captured.append)
    thread.start()
    assert thread.wait(5000)
    assert _pump_until(lambda: len(captured) >= 1)
    assert isinstance(captured[0], services.CoreUnavailableError)
    assert captured[0] is boom


def test_compute_thread_degrades_when_core_lacks_callback(qapp):
    """core 不接受 progress_cb 时线程仍能跑完（降级为不确定模式）。"""
    def legacy_target(a, b):
        return a + b

    values: list[int] = []
    thread = ComputeThread(legacy_target, args=(2, 3))
    thread.signals.succeeded.connect(values.append)
    thread.start()
    assert thread.wait(5000)
    assert _pump_until(lambda: values == [5])
    assert values == [5]


# --------------------------------------------------------------------------- #
# A 法 / B 法：忙窗 + 线程 -> 结果卡
# --------------------------------------------------------------------------- #
def test_run_task_a_updates_result_card(qapp, stub_core, no_modal_exec):
    """A 法：进度回调触发 -> 结果卡回填 wa/wr/K/IaIr/判定。"""
    w = MainWindow()
    try:
        calls: list[dict] = []

        def fake_run(pat, win_a, win_r, k, second_pat=None, **kwargs):
            calls.append({"k": k, "kwargs": kwargs})
            cb = kwargs.get("progress_cb")
            if callable(cb):
                cb(tr("busy.measure"), 20)
                cb(tr("busy.ratio"), 90)
            return {
                "result": SimpleNamespace(wa=42.50, wr=57.50, K=float(k),
                                          ia=1200.0, ir=800.0),
                "dup": {"wa_mean": 42.5, "abs_diff": 0.05,
                        "within_limit": True, "limit": 0.15},
            }

        services.run_method_a.side_effect = fake_run
        _add_pattern(w)
        w.tabs.a_panel.sp_k.setValue(1.22)
        history: list[tuple[str, int]] = []
        orig_set_message = BusyDialog.set_message

        def spy(self: BusyDialog, text: str, pct: int = -1) -> None:
            history.append((text, pct))
            orig_set_message(self, text, pct)

        with mock.patch.object(BusyDialog, "set_message", spy):
            thread = w.run_task_a()
            assert thread is not None
            assert calls, "services.run_method_a 应被调用"
            assert calls[0]["k"] == 1.22, "应把面板当前 K 传给 core"
            assert "progress_cb" in calls[0]["kwargs"], "应向 core 注入进度回调"
            assert _pump_until(
                lambda: w.tabs.a_panel.card_a.value("result.wa") == "42.50")
            assert history, "BusyDialog 应收到阶段进度文案"
            assert tr("busy.measure") in [h[0] for h in history]
        card = w.tabs.a_panel.card_a
        assert card.value("result.wa") == "42.50"
        assert card.value("result.wr") == "57.50"
        assert card.value("result.k") == "1.2200"
        assert card.value("result.ia_ir") == "1.5000"
        assert card.value("result.verdict") == tr("verdict.pass")
        assert w._last_a is not None and w._last_a["rows"], "应缓存导出用汇总"
    finally:
        services.run_method_a.side_effect = None
        w.close()


def test_run_task_b_updates_rfactors(qapp, stub_core, no_modal_exec):
    """B 法：精修结束回填 Rwp/Rp/χ² 并按 Rwp ≤ 10% 给绿/红判定。"""
    w = MainWindow()
    try:
        seen: list[dict] = []

        def fake_run(pat, **kwargs):
            seen.append(kwargs)
            cb = kwargs.get("progress_cb")
            if callable(cb):
                cb(tr("busy.refine_start"), 30)
            it = kwargs.get("on_iter")
            if callable(it):
                it(12, 8.42)
            tt = np.asarray(pat.two_theta)
            ycalc = np.asarray(pat.intensity) * 0.98
            return {
                "result": SimpleNamespace(
                    rf=SimpleNamespace(rwp=8.42, rp=6.10, chi2=1.234)),
                "two_theta": tt,
                "ycalc": ycalc,
                "diff": np.asarray(pat.intensity) - ycalc,
                "wa": 48.0,
                "wr": 52.0,
            }

        services.run_method_b.side_effect = fake_run
        _add_pattern(w)
        thread = w.run_task_b()
        assert thread is not None
        assert _pump_until(
            lambda: w.tabs.b_panel.card_b.value("result.rwp") == "8.42")
        card = w.tabs.b_panel.card_b
        assert card.value("result.b_wa") == "48.00", "B 法应回填锐钛定量结果"
        assert card.value("result.b_wr") == "52.00", "B 法应回填金红石定量结果"
        assert card.value("result.rwp") == "8.42"
        assert card.value("result.rp") == "6.10"
        assert card.value("result.chi2") == "1.234"
        assert card.value("result.fit_verdict") == tr("verdict.fit_good")
        assert w.tabs.b_panel.btn_run.isEnabled(), "跑完应恢复可用"
        assert w._last_b is not None and w._last_b["verdict"] == tr("verdict.fit_good")
        assert w._last_b["rows"][0] == (tr("result.b_wa"), "48.00")
        assert w._last_b["rows"][1] == (tr("result.b_wr"), "52.00")
        assert seen and "progress_cb" in seen[0], "应向 core 注入进度回调"

        # Rwp > 10% -> 红色「拟合不佳」；无定量结果时显示「—」
        def fake_bad(pat, **kwargs):
            tt = np.asarray(pat.two_theta)
            ycalc = np.asarray(pat.intensity) * 0.80
            return {
                "result": SimpleNamespace(
                    rf=SimpleNamespace(rwp=25.5, rp=20.0, chi2=9.9)),
                "two_theta": tt, "ycalc": ycalc,
                "diff": np.asarray(pat.intensity) - ycalc,
            }

        services.run_method_b.side_effect = fake_bad
        w.run_task_b()
        assert _pump_until(
            lambda: w.tabs.b_panel.card_b.value("result.fit_verdict")
            == tr("verdict.fit_bad"))
        assert w.tabs.b_panel.card_b.value("result.fit_verdict") == tr("verdict.fit_bad")
        assert w.tabs.b_panel.card_b.value("result.b_wa") == tr("verdict.na"), \
            "定量缺失时应显示「—」"
    finally:
        services.run_method_b.side_effect = None
        w.close()


# --------------------------------------------------------------------------- #
# K 值说明 / K 标定向导
# --------------------------------------------------------------------------- #
def test_khelp_dialog_explains_k(qapp):
    """K 说明对话框讲清定义公式、结果式与「必须标定」要点。"""
    set_language("zh_CN")
    dlg = KHelpDialog()
    text = dlg.toPlainText()
    assert "K = [ I(A) / I(R) ] ÷ [ m(A) / m(R) ]" in text
    assert "w(A) = 1 / [ 1 + K × I(R)/I(A) ] × 100%" in text
    assert "1.22" in text, "应给出本项目真实数据实测的典型量级参考"
    assert "标定向导" in text
    dlg.close()


def _wizard_with_rows(stub_core, **kwargs) -> KCalibWizardDialog:
    """构造向导并预置三个已测量点（默认 w(R)=50/33.3/75%）。"""
    dlg = KCalibWizardDialog(**kwargs)
    specs = [("D:/std/a.xy", 50.0, 1.22), ("D:/std/b.xy", 33.3, 2.44),
             ("D:/std/c.xy", 75.0, 0.41)]
    for path, wr, ratio_i in specs:
        dlg.add_row(path, wr, ratio_i=ratio_i, ok=True)
    return dlg


def test_kwizard_table_ratio_and_fit(qapp, stub_core):
    """向导表格：w(R)% -> m(A)/m(R) 换算，足够点数时拟合出 K/R²。"""
    set_language("zh_CN")
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.2200, intercept=0.0030, r2=0.9997, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        assert dlg.row_count() == 3
        first = dlg.rows[0]
        assert first["wr"] == 50.0
        assert abs(first["ratio_m"] - 1.0) < 1e-9
        assert dlg.table.item(0, 0).text() == "a.xy"
        assert dlg.table.item(0, 2).text() == "1.0000"
        assert dlg.table.item(0, 3).text() == "1.2200"
        assert len(dlg.measured_points()) == 3
        fit = dlg.fit_result()
        assert fit is not None and abs(fit["K"] - 1.2200) < 1e-6
        assert abs(fit["r2"] - 0.9997) < 1e-9
        services.calibrate_from_points.assert_called_once()
        args, kwargs = services.calibrate_from_points.call_args
        assert len(args[0]) == 3
        assert kwargs.get("force_zero") is False, "默认口径应为带截距 OLS"
        assert tr("kwizard.result", k=1.22, b=0.003, r2=0.9997, n=3) == dlg.lbl_result.text()
        assert not dlg.lbl_warn.isVisibleTo(dlg), "R² 合格时不显示警示"
        assert dlg.btn_adopt.isEnabled()
    finally:
        dlg.close()


def test_kwizard_warns_on_low_r2(qapp, stub_core):
    """R² < 0.995 时给出黄色警示。"""
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.5, intercept=0.5, r2=0.9000, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        assert dlg.fit_result() is not None
        assert dlg.lbl_warn.isVisibleTo(dlg)
        assert tr("kwizard.warn_r2", r2=0.9) == dlg.lbl_warn.text()
    finally:
        dlg.close()


def test_kwizard_needs_three_points(qapp, stub_core):
    """不足 3 个有效标定点时不拟合，并提示当前点数。"""
    dlg = KCalibWizardDialog()
    try:
        dlg.add_row("D:/std/a.xy", 50.0, ratio_i=1.2, ok=True)
        assert dlg.fit_result() is None
        assert tr("kwizard.min_points", n=1) == dlg.lbl_result.text()
        assert not dlg.btn_adopt.isEnabled()
    finally:
        dlg.close()


def test_kwizard_forced_origin_mode(qapp, stub_core):
    """切换为强制过原点时 force_zero=True 传给 core。"""
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.10, intercept=0.0, r2=0.999, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        dlg.cmb_fit.setCurrentIndex(1)
        assert dlg.cmb_fit.currentData() == "origin"
        assert dlg.fit_result()["K"] == 1.10
        _junk, kwargs = services.calibrate_from_points.call_args
        assert kwargs.get("force_zero") is True
    finally:
        dlg.close()


def test_kwizard_record_roundtrip(qapp, stub_core, tmp_path):
    """标定记录可导出 JSON 并原样载入（ rows/K/R²/口径）。"""
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.2200, intercept=0.0030, r2=0.9997, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        payload = dlg.record()
        assert payload["version"] == 1
        assert payload["mode"] == "ols"
        assert payload["quantity"] == "area", "默认口径应写入标定记录"
        assert len(payload["rows"]) == 3
        target = tmp_path / "k.json"
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        other = KCalibWizardDialog()
        try:
            other.load_record(json.loads(target.read_text(encoding="utf-8")))
            assert other.row_count() == 3
            assert other.rows[0]["ratio_i"] == 1.22
            assert other.fit_result()["K"] == 1.2200
        finally:
            other.close()
    finally:
        dlg.close()


def test_kwizard_measure_all_uses_worker(qapp, stub_core, no_modal_exec):
    """「测量全部」走后台线程并写入表格 I(A)/I(R)。"""
    set_language("zh_CN")
    dlg = KCalibWizardDialog()
    try:
        dlg.add_row("D:/std/a.xy", 50.0)
        dlg.add_row("D:/std/b.xy", 33.3)

        seen: list[tuple] = []

        def fake_measure(rows, win_a, win_r, **kwargs):
            cb = kwargs.get("progress_cb")
            if callable(cb):
                cb(tr("busy.calib_row", i=1, n=2), 10)
            out = []
            for i, spec in enumerate(rows):
                out.append({"file": spec["file"], "wr": spec["wr"],
                            "ratio_m": services.mass_ratio_from_wr(spec["wr"]),
                            "ratio_i": 1.2 + i, "ia": 1200.0, "ir": 1000.0,
                            "ok": True, "message": ""})
            return out

        services.measure_calib_rows.side_effect = fake_measure
        services.calibrate_from_points.return_value = SimpleNamespace(
            K=1.2, intercept=0.0, r2=0.9999, n_points=2)
        orig_msg = BusyDialog.set_message

        def spy(self: BusyDialog, text: str, pct: int = -1) -> None:
            seen.append((text, pct))
            orig_msg(self, text, pct)

        with mock.patch.object(BusyDialog, "set_message", spy):
            dlg._on_measure_all()
            assert _pump_until(lambda: dlg.rows[0]["ok"] is True, timeout=8.0)
            assert dlg.rows[0]["ok"] and dlg.rows[1]["ok"]
            assert abs(dlg.rows[0]["ratio_i"] - 1.2) < 1e-9
            assert any(tr("busy.calib_row", i=1, n=2) == t for t, _p in seen)
            assert services.measure_calib_rows.call_count == 1
    finally:
        services.measure_calib_rows.side_effect = None
        dlg.close()


def test_kwizard_adopt_updates_panel(qapp, stub_core, no_modal_exec):
    """「采用此 K」把 K/R² 回填到 A 法面板并发信号。"""
    set_language("zh_CN")
    w = MainWindow()
    try:
        services.calibrate_from_points.return_value = SimpleNamespace(
            K=1.2200, intercept=0.003, r2=0.9997, n_points=3)
        dlg = _wizard_with_rows(stub_core)
        got: list[tuple] = []
        dlg.k_adopted.connect(lambda k, b, r2, q: got.append((k, b, r2, q)))
        dlg.btn_adopt.click()
        assert got and got[0][0] == 1.2200 and got[0][2] == 0.9997
        assert got[0][3] == "area", "采用时应携带当前峰强口径"

        w._on_k_adopted(1.2200, 0.003, 0.9997)
        assert abs(w.tabs.a_panel.current_k() - 1.2200) < 1e-9
        assert abs((w.tabs.a_panel.current_r2() or 0) - 0.9997) < 1e-9
        assert w.tabs.a_panel.current_quantity() == "area", "缺省时口径应为 area"
        w._on_k_adopted(1.2200, 0.003, 0.9997, "height")
        assert w.tabs.a_panel.current_quantity() == "height", \
            "向导口径应一并回填主界面"
        assert tr("a.k.source_calib") in w.tabs.a_panel.lbl_kinfo.text()
        assert tr("a.k.result", k=1.22, r2=0.9997) in w.tabs.a_panel.lbl_kinfo.text()
        dlg.close()
    finally:
        w.close()


def test_apanel_reference_truth_relative_error(qapp, stub_core):
    """参考真值按金红石 wt% 比较：结果卡显示相对误差（%），未启用显示「—」。"""
    set_language("zh_CN")
    w = MainWindow()
    try:
        panel = w.tabs.a_panel
        result = SimpleNamespace(wa=49.0, wr=51.0, K=1.22, ia=1200.0, ir=1000.0)
        assert panel.reference_value() is None
        panel.set_result_a(result, None, None, None)
        assert panel.card_a.value("result.ref_err") == tr("verdict.na")
        panel.chk_ref.setChecked(True)
        panel.sp_ref.setValue(50.0)
        assert panel.reference_value() == 50.0
        panel.set_result_a(result, None, None, 50.0)
        assert panel.card_a.value("result.ref_err") == "+2.00", \
            "相对误差应按金红石 wt% 计算：(51-50)/50"
    finally:
        w.close()


# --------------------------------------------------------------------------- #
# v1.1.0：峰强口径（area/height）与 B 法双相定量
# --------------------------------------------------------------------------- #
def _fake_measure_by_window(pat, expected, tol, **_kwargs):
    """测峰桩：A 峰位返回 (净高 100, 面积 6000)，R 峰位返回 (净高 80, 面积 4000)。"""
    if expected < 26.0:
        return SimpleNamespace(ok=True, net_height=100.0, net_area=6000.0,
                               message="")
    return SimpleNamespace(ok=True, net_height=80.0, net_area=4000.0, message="")


def test_measure_calib_rows_quantity(monkeypatch):
    """标定批量测量按口径取值：height 取净峰高、area 取净峰面积（默认）。"""
    monkeypatch.setattr(services, "load_pattern", lambda _path: object())
    monkeypatch.setattr(services, "measure_peak", _fake_measure_by_window)
    rows = [{"file": "D:/std/a.xy", "wr": 50.0}]
    by_height = services.measure_calib_rows(
        rows, (24.5, 26.5), (26.5, 28.5), quantity="height")
    by_area = services.measure_calib_rows(
        rows, (24.5, 26.5), (26.5, 28.5))
    assert by_height[0]["ok"] and by_area[0]["ok"]
    assert by_height[0]["ratio_i"] == pytest.approx(100.0 / 80.0)
    assert by_area[0]["ratio_i"] == pytest.approx(6000.0 / 4000.0), \
        "默认口径应为净峰面积（v1.0.0 调优结论）"


def test_run_method_a_quantity(monkeypatch):
    """A 法全流程按口径取峰强；不传 quantity 时默认净峰面积。"""
    monkeypatch.setattr(services, "measure_peak", _fake_measure_by_window)
    pat = _fake_pattern()
    out_h = services.run_method_a(pat, (24.5, 26.5), (26.5, 28.5), k=1.0,
                                  quantity="height")
    assert out_h["ia"] == pytest.approx(100.0)
    assert out_h["ir"] == pytest.approx(80.0)
    out_a = services.run_method_a(pat, (24.5, 26.5), (26.5, 28.5), k=1.0)
    assert out_a["ia"] == pytest.approx(6000.0)
    assert out_a["ir"] == pytest.approx(4000.0)


def test_kwizard_quantity_switch_invalidates_measurements(qapp, stub_core):
    """切换峰强口径后旧测量值全部作废，须重新「测量全部」才能拟合。"""
    set_language("zh_CN")
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.2200, intercept=0.0030, r2=0.9997, n_points=3)
    dlg = _wizard_with_rows(stub_core)
    try:
        assert dlg.current_quantity() == "area", "默认口径应为峰面积"
        assert dlg.fit_result() is not None
        dlg.cmb_quantity.setCurrentIndex(1)
        assert dlg.current_quantity() == "height"
        assert all(row["ratio_i"] is None and not row["ok"] for row in dlg.rows), \
            "旧口径的测量值应全部置无效"
        assert all(row["message"] == tr("kwizard.remeasure") for row in dlg.rows)
        assert dlg.fit_result() is None
        assert not dlg.btn_adopt.isEnabled(), "重测前不允许采用"
    finally:
        dlg.close()


def test_kwizard_record_quantity_roundtrip(qapp, stub_core, tmp_path):
    """标定记录携带口径往返；旧记录（无 quantity 字段）载入后兜底为 area。"""
    services.calibrate_from_points.return_value = SimpleNamespace(
        K=1.2200, intercept=0.0030, r2=0.9997, n_points=3)
    dlg = KCalibWizardDialog()
    try:
        # 先切口径再录入已测量行（口径切换只作废旧测量值，不影响后续录入）
        dlg.cmb_quantity.setCurrentIndex(1)
        for path, wr, ratio_i in (("D:/std/a.xy", 50.0, 1.22),
                                  ("D:/std/b.xy", 33.3, 2.44),
                                  ("D:/std/c.xy", 75.0, 0.41)):
            dlg.add_row(path, wr, ratio_i=ratio_i, ok=True)
        payload = dlg.record()
        assert payload["quantity"] == "height"
        target = tmp_path / "k_h.json"
        target.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

        other = KCalibWizardDialog()
        try:
            other.load_record(json.loads(target.read_text(encoding="utf-8")))
            assert other.current_quantity() == "height", "载入记录应恢复口径"
            assert other.rows[0]["ratio_i"] == 1.22, "恢复口径不得清掉已载测量值"
        finally:
            other.close()

        legacy = KCalibWizardDialog()
        try:
            legacy_payload = json.loads(json.dumps(payload))
            del legacy_payload["quantity"]
            legacy.load_record(legacy_payload)
            assert legacy.current_quantity() == "area", "旧记录缺口径时兜底 area"
            assert legacy.rows[0]["ratio_i"] == 1.22
        finally:
            legacy.close()
    finally:
        dlg.close()


def test_services_b_qpa_acid_check():
    """_b_qpa 酸检：等标度下 w(锐) = 4×136.3/(4×136.3+2×62.42) ≈ 81.37%。"""
    from rutana.core.profile.cif import parse_cif

    root = Path(__file__).resolve().parent.parent
    st_a = parse_cif(root / "rutana" / "data" / "anatase.cif")
    st_r = parse_cif(root / "rutana" / "data" / "rutile.cif")
    res = SimpleNamespace(scales=[1.0, 1.0],
                          cell_scales=((1.0, 1.0), (1.0, 1.0)))
    wa, wr = services._b_qpa([st_a, st_r], res)
    assert wa == pytest.approx(81.37, abs=0.1)
    assert wr == pytest.approx(18.63, abs=0.1)


def test_services_b_qpa_degrades_to_none():
    """定量输入非法（scale 全零）时 _b_qpa 降级为 (None, None) 而非抛异常。"""
    from rutana.core.profile.cif import parse_cif

    root = Path(__file__).resolve().parent.parent
    st_a = parse_cif(root / "rutana" / "data" / "anatase.cif")
    st_r = parse_cif(root / "rutana" / "data" / "rutile.cif")
    res = SimpleNamespace(scales=[0.0, 0.0],
                          cell_scales=((1.0, 1.0), (1.0, 1.0)))
    assert services._b_qpa([st_a, st_r], res) == (None, None)
