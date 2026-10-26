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
v1.2.0 新增：A/B 两法的**批量**任务（见 :mod:`rutana.gui.batch`）。
批量走同一套忙窗 + 后台线程；取消时**已完成文件的结果照常落盘**
（batch 层在取消处 `break` 并原样返回已算行，不抛 TaskCanceled）。
"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Callable

import numpy as np

from rutana.gui import batch, services
from rutana.gui.exports import a_rows
from rutana.gui.verdict import rwp_verdict
from rutana.gui.workers import run_busy_task
from rutana.i18n import tr


def _po_pair(po_r) -> tuple[float | None, float | None]:
    """从 po_r dict 取内置两相的 (r_锐钛, r_金红石)；缺失返回 (None, None)。

    相名即 CIF 名 "anatase"/"rutile"；附加相不显示。po_r 为 None
    （未开启择优取向精修）或两相都缺时返回 (None, None)。
    """
    if not po_r:
        return None, None
    ra = po_r.get("anatase")
    rr = po_r.get("rutile")
    fa = float(ra[3]) if ra else None
    fr = float(rr[3]) if rr else None
    return fa, fr


def _po_text(po_r) -> str:
    """内置两相 r 的展示文本（「ra / rr」；缺失显示「—」）。"""
    fa, fr = _po_pair(po_r)
    if fa is None or fr is None:
        return tr("verdict.na")
    return f"{fa:.2f} / {fr:.2f}"


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
                    "k": self.tabs.a_panel.current_k(), "second_pat": second,
                    "quantity": self.tabs.a_panel.current_quantity()},
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

    def run_task_a_batch(self):
        """A 法批量：对已导入的全部谱图逐个计算，结果按来源文件夹写 CSV。"""
        items = self._batch_items()
        if not items:
            self._msg("msg.need_pattern")
            return None
        k = self.tabs.a_panel.current_k()
        if not k or k <= 0:
            self._msg("msg.need_k")
            return None
        params = self.tabs.a_panel.params()
        return self._run_core_task(
            self._batch_runner(batch.run_method_a_batch,
                               items=items, win_a=params["win_a"],
                               win_r=params["win_r"], k=k,
                               quantity=self.tabs.a_panel.current_quantity()),
            title=tr("busy.title_batch_a"),
            cancellable=True,
            degraded=not services.supports_progress("a"),
            error_key="msg.batch_fail",
            on_success=lambda data: self._finish_batch(data, "a"))

    def _batch_items(self) -> list[tuple[str, object]]:
        """批量输入：当前已导入的全部谱图（保持导入顺序）。"""
        return list(self._patterns.items())

    def _batch_runner(self, fn: Callable, **kwargs) -> Callable:
        """把批量函数包成线程目标：顺带把「是否被取消」随结果一起回传。

        :mod:`rutana.gui.workers` 会把 ``cancel_cb`` 注入**本闭包**（签名里有
        这三个形参），因此跑完后直接问它就能知道用户是否点过取消——
        取消时 batch 层返回的是**已完成部分**，照样要落盘。
        """
        def runner(*, progress_cb=None, on_iter=None, cancel_cb=None) -> dict:
            extra = {"progress_cb": progress_cb, "cancel_cb": cancel_cb}
            # A 法批量没有迭代回调，不支持就别传（core 能力探测沿用同款约定）
            if on_iter is not None and services.supports_param(fn, "on_iter"):
                extra["on_iter"] = on_iter
            rows = fn(**kwargs, **extra)
            return {"rows": rows, "canceled": bool(
                callable(cancel_cb) and cancel_cb())}

        return runner

    def _finish_batch(self, data: dict, method: str) -> None:
        """批量收尾：落盘 CSV（+ B 法逐文件 PNG）→ 回填结果卡/画布 → 弹汇总。

        取消时 batch 层已把完成部分返回，因此这里照常落盘，只用
        ``msg.batch_canceled`` 文案告知用户这是一份**部分结果**。
        """
        rows = list(data.get("rows") or [])
        canceled = bool(data.get("canceled"))
        if not rows:  # 开局即取消：一个文件都没算完，无结果可落盘
            self._msg("msg.busy_canceled")
            return
        paths: list[str] = []
        for dest, group in batch.batch_save_plan(rows):
            paths.append(batch.export_batch_csv(group, dest, method=method))
        ok_rows = [r for r in rows if r.get("ok")]
        failed = len(rows) - len(ok_rows)
        if ok_rows:
            self._apply_batch_result(ok_rows[0], method)
            if method == "b":
                self._export_batch_pngs(ok_rows)
        key = "msg.batch_canceled" if canceled else "msg.batch_done"
        self._msg_box(tr(key, ok=len(ok_rows), fail=failed, paths="\n".join(paths)))

    def _export_batch_pngs(self, rows: list[dict]) -> None:
        """B 法批量：每个成功文件导出一张与数据同名的精修谱图 PNG。"""
        for row in rows:
            if not row.get("fit"):
                continue
            try:
                batch.export_fit_png(row["fit"], batch.fit_png_path(row["path"]))
            except Exception:  # noqa: BLE001 —— 单张图失败不影响整批结果
                continue

    def _apply_batch_result(self, row: dict, method: str) -> None:
        """把批量首个成功结果回填到结果卡/画布（B 法同时画该文件的拟合谱）。"""
        if method == "a":
            self.tabs.a_panel.set_result_a(
                SimpleNamespace(wa=row["wa"], wr=row["wr"], K=row["K"],
                                ia=row["ia"], ir=row["ir"]),
                None, self.tabs.a_panel.current_r2(),
                self.tabs.a_panel.reference_value())
            self._last_a = {
                "sample": row["sample"], "file": row["path"],
                "rows": [(tr("result.wa"), f"{row['wa']:.2f}"),
                         (tr("result.wr"), f"{row['wr']:.2f}"),
                         (tr("result.k"), f"{row['K']:.4f}"),
                         (tr("result.ia"), f"{row['ia']:.1f}"),
                         (tr("result.ir"), f"{row['ir']:.1f}")],
                "verdict": tr("verdict.na"),
            }
            return
        self.tabs.b_panel.set_rfactors(row["rwp"], row["rp"], row["chi2"])
        self.tabs.b_panel.set_quantities(row["wa"], row["wr"])
        self.tabs.b_panel.set_po(*_po_pair(row.get("po_r")))
        fit = row.get("fit")
        if fit:
            self.canvas.show_fit(np.asarray(fit["two_theta"]),
                                 np.asarray(fit["yobs"]),
                                 np.asarray(fit["ycalc"]),
                                 np.asarray(fit["diff"]))
        verdict = tr(rwp_verdict(row["rwp"])[0])   # v1.6.2 四档口径
        self._last_b = {
            "sample": row["sample"], "file": row["path"],
            "rows": [(tr("result.b_wa"),
                      tr("verdict.na") if row["wa"] is None else f"{row['wa']:.2f}"),
                     (tr("result.b_wr"),
                      tr("verdict.na") if row["wr"] is None else f"{row['wr']:.2f}"),
                     (tr("result.rwp"), f"{row['rwp']:.2f}"),
                     (tr("result.rp"), f"{row['rp']:.2f}"),
                     (tr("result.chi2"), f"{row['chi2']:.3f}"),
                     (tr("result.fit_verdict"), verdict),
                     (tr("result.b_po"), _po_text(row.get("po_r")))],
            "verdict": verdict,
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
        verdict_key = rwp_verdict(rf.rwp)[0]   # v1.6.2 四档口径
        self.tabs.b_panel.set_rfactors(rf.rwp, rf.rp, rf.chi2)
        wa, wr = data.get("wa"), data.get("wr")
        self.tabs.b_panel.set_quantities(
            None if wa is None else float(wa), None if wr is None else float(wr))
        self.tabs.b_panel.set_po(*_po_pair(data.get("po_r")))
        self.canvas.show_fit(np.asarray(data["two_theta"]),
                             np.asarray(self._current_pattern().intensity),
                             np.asarray(data["ycalc"]),
                             np.asarray(data["diff"]))
        self._last_b = {
            "sample": Path(self._current_path() or "").stem,
            "file": self._current_path() or "",
            "rows": [
                (tr("result.b_wa"),
                 tr("verdict.na") if wa is None else f"{float(wa):.2f}"),
                (tr("result.b_wr"),
                 tr("verdict.na") if wr is None else f"{float(wr):.2f}"),
                (tr("result.rwp"), f"{rf.rwp:.2f}"),
                (tr("result.rp"), f"{rf.rp:.2f}"),
                (tr("result.chi2"), f"{rf.chi2:.3f}"),
                (tr("result.fit_verdict"), tr(verdict_key)),
                (tr("result.b_po"), _po_text(data.get("po_r"))),
            ],
            "verdict": tr(verdict_key),
        }

    def run_task_b_batch(self):
        """B 法批量：对已导入的全部谱图逐个精修，CSV 按来源文件夹、PNG 逐文件。"""
        items = self._batch_items()
        if not items:
            self._msg("msg.need_pattern")
            return None
        params = self.tabs.b_panel.params()
        self.tabs.b_panel.set_busy(True)
        thread = self._run_core_task(
            self._batch_runner(
                batch.run_method_b_batch, items=items,
                refine_zero=params["refine_zero"], refine_uvw=params["refine_uvw"],
                refine_eta=params["refine_eta"], n_bg=params["n_bg"],
                refine_po=params["refine_po"],
                extra_cifs=params["extra_cifs"]),
            title=tr("busy.title_batch_b"),
            cancellable=True,
            degraded=not (services.supports_progress("b")
                          or services.supports_iteration("b")),
            error_key="msg.batch_fail",
            on_success=lambda data: self._finish_batch(data, "b"))
        self.tabs.b_panel.set_busy(False)
        return thread

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

    def _on_k_adopted(self, k: float, _intercept: float, r2: float,
                      quantity: str = "area") -> None:
        """向导采用此 K -> 回填面板（K/R²/峰强口径）并提示用户。"""
        self.tabs.a_panel.set_k(float(k), float(r2))
        self.tabs.a_panel.set_quantity(quantity)
        self._msg_box(tr("kwizard.adopted", k=float(k), r2=float(r2)))
