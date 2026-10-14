"""MainWindow 的后台任务行为（A 法 / B 法 / K 标定测量）。

从 main_window 拆出以控制单文件规模。本 mixin 依赖宿主窗口提供：

- ``self.tabs.a_panel`` / ``self.tabs.b_panel``：参数面板；
- ``self._current_pattern()`` / ``self._current_path()`` / ``self._patterns``；
- ``self._msg(key, detail=None, error=False)``：统一弹窗；
- ``self.canvas``：结果叠加显示；
- ``self._last_a`` / ``self._last_b``：导出用的最近一次结果汇总。

所有 core 调用都在 :mod:`rutana.gui.workers` 的 QThread 内完成，
前台由 :class:`rutana.gui.busy.BusyDialog` 显示阶段进度与已用时；
core 抛错时忙窗关闭并由本模块给出中文提示（保留 CoreUnavailableError 语义）。
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable

import numpy as np

from rutana.gui import services
from rutana.gui.exports import a_rows
from rutana.gui.workers import run_busy_task
from rutana.i18n import tr


class TaskMixin:
    """主窗口的「跑后台任务」能力。"""

    # ------------------------------------------------------------------ #
    # 通用
    # ------------------------------------------------------------------ #
    def _run_core_task(self, target: Callable, *, args=(), kwargs=None,
                       title: str | None = None, cancellable: bool = False,
                       degraded: bool = False, error_key: str,
                       on_success: Callable[[object], None] | None = None):
        """起线程 + 弹忙窗 + 统一错误处理；返回 ComputeThread。"""
        return run_busy_task(
            self, target, args=args, kwargs=dict(kwargs or {}),
            title=title, cancellable=cancellable, degraded=degraded,
            on_success=on_success, on_error=lambda exc: self._task_error(exc, error_key))

    def _task_error(self, exc: Exception, error_key: str) -> None:
        """把后台异常翻译成中文弹窗（CoreUnavailableError / 取消 / 一般失败）。"""
        if isinstance(exc, services.CoreUnavailableError):
            self._msg("msg.core_unavailable", str(exc), error=True)
        elif isinstance(exc, services.TaskCanceled):
            self._msg("msg.busy_canceled")
        else:
            self._msg(error_key, str(exc), error=True)

    # ------------------------------------------------------------------ #
    # A 法
    # ------------------------------------------------------------------ #
    def run_task_a(self):
        """A 法：当前谱计算；已导入两份谱时自动做双平行合并。"""
        pat = self._current_pattern()
        if pat is None:
            self._msg("msg.need_pattern")
            return None
        params = self.tabs.a_panel.params()
        second = self._second_pattern(pat)
        return self._run_core_task(
            services.run_method_a,
            kwargs={"pat": pat, "win_a": params["win_a"], "win_r": params["win_r"],
                    "k": self.tabs.a_panel.current_k(), "second_pat": second},
            title=tr("busy.title"),
            cancellable=services.supports_cancel("a"),
            degraded=not services.supports_progress("a"),
            error_key="msg.compute_fail",
            on_success=self._apply_a_result)

    def _second_pattern(self, pat):
        """双平行用的第二份谱（不存在则返回 None）。"""
        pats = list(self._patterns.values())
        if len(pats) >= 2:
            return pats[1] if pats[0] is pat else pats[0]
        return None

    def _apply_a_result(self, data: dict) -> None:
        """A 法结果回填面板与导出汇总。"""
        result = data["result"]
        dup = data.get("dup")
        ref = self.tabs.a_panel.reference_value()
        self.tabs.a_panel.set_result_a(result, dup, self.tabs.a_panel.current_r2(), ref)
        self._last_a = {
            "sample": Path(self._current_path() or "").stem,
            "file": self._current_path() or "",
            "rows": a_rows(result, dup),
            "verdict": (tr("verdict.pass") if dup and dup["within_limit"]
                        else tr("verdict.fail") if dup else tr("verdict.na")),
        }

    # ------------------------------------------------------------------ #
    # B 法
    # ------------------------------------------------------------------ #
    def run_task_b(self):
        """B 法：Rietveld 精修，完成后画布叠加计算谱与差值线。"""
        pat = self._current_pattern()
        if pat is None:
            self._msg("msg.need_pattern")
            return None
        params = self.tabs.b_panel.params()
        self.tabs.b_panel.set_busy(True)
        thread = self._run_core_task(
            services.run_method_b, kwargs={"pat": pat, **params},
            title=tr("busy.title_refine"),
            cancellable=services.supports_cancel("b"),
            degraded=not (services.supports_progress("b")
                          or services.supports_iteration("b")),
            error_key="msg.refine_fail",
            on_success=self._apply_b_result)
        self.tabs.b_panel.set_busy(False)
        return thread

    def _apply_b_result(self, data: dict) -> None:
        """B 法结果回填面板、画布与导出汇总。"""
        rf = data["result"].rf
        self.tabs.b_panel.set_rfactors(rf.rwp, rf.rp, rf.chi2)
        self.canvas.show_fit(np.asarray(data["two_theta"]),
                             np.asarray(self._current_pattern().intensity),
                             np.asarray(data["ycalc"]),
                             np.asarray(data["diff"]))
        self._last_b = {
            "sample": Path(self._current_path() or "").stem,
            "file": self._current_path() or "",
            "rows": [
                (tr("result.rwp"), f"{rf.rwp:.2f}"),
                (tr("result.rp"), f"{rf.rp:.2f}"),
                (tr("result.chi2"), f"{rf.chi2:.3f}"),
                (tr("result.fit_verdict"),
                 tr("verdict.fit_good" if rf.rwp <= 10.0 else "verdict.fit_bad")),
            ],
            "verdict": tr("verdict.fit_good" if rf.rwp <= 10.0 else "verdict.fit_bad"),
        }

    # ------------------------------------------------------------------ #
    # K 标定（面板按钮 -> 向导）
    # ------------------------------------------------------------------ #
    def open_k_help(self) -> None:
        """打开「K 值说明」对话框。"""
        from rutana.gui.khelp import KHelpDialog

        KHelpDialog(self).exec()

    def open_k_wizard(self) -> None:
        """打开「K 标定向导」；采用后回填面板 K 与 R²。"""
        from rutana.gui.kwizard import KCalibWizardDialog

        params = self.tabs.a_panel.params()
        dlg = KCalibWizardDialog(self, win_a=params["win_a"], win_r=params["win_r"])
        dlg.k_adopted.connect(self._on_k_adopted)
        dlg.exec()

    def _on_k_adopted(self, k: float, _intercept: float, r2: float) -> None:
        """向导采用此 K -> 回填面板并提示用户。"""
        self.tabs.a_panel.set_k(float(k), float(r2))
        self._msg_box(tr("kwizard.adopted", k=float(k), r2=float(r2)))
