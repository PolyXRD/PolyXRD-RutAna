"""「K 标定向导」对话框。

把「K 怎么来的」变成**一条可走完的路**：

1. 表格录入标准混合样（每行 = 一个已知配比的谱图文件 + 金红石型质量分数%）；
2. 一键「测量全部」——后台线程逐行读取谱图并在 A 法两个窗口上测峰，
   表格实时回填 I(A)/I(R)，进度走 :mod:`rutana.gui.workers` 的忙对话框；
3. 实时绘制标定曲线（散点 + 拟合直线），显示 K / 截距 / R²，
   R² < 0.995 给黄色警示；
4. 拟合口径可切换：默认带截距 OLS，或强制过原点；
5. 「采用此 K」把结果回填主界面；标定记录可导出 JSON 存档、下次载入复用。

依赖拆分（控制单文件规模）：

- 表格显示层 -> :mod:`rutana.gui.calibtable`；
- 记录序列化   -> :mod:`rutana.gui.calibrecord`。

对 core 的依赖全部经 ``rutana.gui.services``（可被 mock 桩掉），
因此本对话框在无 core 环境下也能跑通表格/拟合逻辑的单测。
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rutana.gui import services
from rutana.gui.calibcanvas import CalibCanvas
from rutana.gui.calibrecord import build_record, mass_ratio_from_wr, parse_record
from rutana.gui.calibtable import CalibTable
from rutana.gui.workers import run_busy_task
from rutana.i18n import tr

#: R² 告警阈值
R2_WARN_LIMIT = 0.995

#: 新增行的默认 w(金红石型) / %
DEFAULT_WR = 50.0


class KCalibWizardDialog(QDialog):
    """K 标定向导：录入 → 测量 → 看曲线 → 采用此 K → 可存档。"""

    #: 采用此 K：(K, intercept, r2, quantity) —— quantity 为峰强口径
    k_adopted = Signal(float, float, float, str)

    def __init__(self, parent: QWidget | None = None, *,
                 win_a: tuple[float, float] = (24.5, 26.5),
                 win_r: tuple[float, float] = (26.5, 28.5)) -> None:
        super().__init__(parent)
        self._win_a = (float(win_a[0]), float(win_a[1]))
        self._win_r = (float(win_r[0]), float(win_r[1]))
        #: 每行: {"file","wr","ratio_m","ratio_i","ok","message"}
        self.rows: list[dict] = []
        self._fit: dict[str, Any] | None = None

        self.resize(760, 640)
        root = QVBoxLayout(self)

        self.lbl_intro = QLabel(self)
        self.lbl_intro.setWordWrap(True)
        root.addWidget(self.lbl_intro)

        self.table = CalibTable(self)
        self.table.wr_changed.connect(self._on_wr_changed)
        self.table.mr_changed.connect(self._on_mr_changed)
        root.addWidget(self.table, 2)

        bar = QHBoxLayout()
        self.btn_add = QPushButton(self)
        self.btn_add.clicked.connect(self._on_add)
        self.btn_remove = QPushButton(self)
        self.btn_remove.clicked.connect(self._on_remove)
        self.btn_clear = QPushButton(self)
        self.btn_clear.clicked.connect(self._on_clear)
        self.btn_measure = QPushButton(self)
        self.btn_measure.clicked.connect(self._on_measure_all)
        for w in (self.btn_add, self.btn_remove, self.btn_clear, self.btn_measure):
            bar.addWidget(w)
        bar.addStretch(1)
        root.addLayout(bar)

        opt = QHBoxLayout()
        self.lbl_fit_mode = QLabel(self)
        self.cmb_fit = QComboBox(self)
        self.cmb_fit.addItem(tr("kwizard.fit.ols"), "ols")
        self.cmb_fit.addItem(tr("kwizard.fit.origin"), "origin")
        self.cmb_fit.setCurrentIndex(0)
        self.cmb_fit.currentIndexChanged.connect(lambda _i: self._refit())
        opt.addWidget(self.lbl_fit_mode)
        opt.addWidget(self.cmb_fit)
        self.lbl_quantity = QLabel(self)
        self.cmb_quantity = QComboBox(self)
        self.cmb_quantity.addItem(tr("kwizard.quantity.area"), "area")
        self.cmb_quantity.addItem(tr("kwizard.quantity.height"), "height")
        self.cmb_quantity.setCurrentIndex(0)
        self.cmb_quantity.currentIndexChanged.connect(self._on_quantity_changed)
        opt.addWidget(self.lbl_quantity)
        opt.addWidget(self.cmb_quantity)
        opt.addStretch(1)
        root.addLayout(opt)

        self.lbl_result = QLabel(tr("verdict.na"), self)
        self.lbl_result.setStyleSheet("font-weight:600; font-size:13px; color:#0F172A;")
        root.addWidget(self.lbl_result)
        self.lbl_warn = QLabel(tr("verdict.na"), self)
        self.lbl_warn.setWordWrap(True)
        self.lbl_warn.setStyleSheet("font-size:12px; font-weight:600; color:#B45309;")
        self.lbl_warn.hide()
        root.addWidget(self.lbl_warn)

        self.canvas = CalibCanvas(self)
        root.addWidget(self.canvas, 3)

        foot = QHBoxLayout()
        self.btn_load = QPushButton(self)
        self.btn_load.clicked.connect(self._on_load)
        self.btn_save = QPushButton(self)
        self.btn_save.clicked.connect(self._on_save)
        self.btn_adopt = QPushButton(self)
        self.btn_adopt.setEnabled(False)
        self.btn_adopt.clicked.connect(self._on_adopt)
        self.btn_close = QPushButton(self)
        self.btn_close.clicked.connect(self.reject)
        for w in (self.btn_load, self.btn_save, self.btn_adopt, self.btn_close):
            foot.addWidget(w)
        foot.addStretch(1)
        root.addLayout(foot)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def row_count(self) -> int:
        """表格行数。"""
        return len(self.rows)

    def add_row(self, file_path: str, wr: float = DEFAULT_WR, *,
                ratio_i: float | None = None, ok: bool = False,
                message: str = "") -> None:
        """追加一行标准混合样（随后自动重拟合）。"""
        self.rows.append({
            "file": str(file_path),
            "wr": float(wr),
            "ratio_m": mass_ratio_from_wr(wr),
            "ratio_i": None if ratio_i is None else float(ratio_i),
            "ok": bool(ok),
            "message": str(message),
        })
        self._refresh()

    def measured_points(self) -> list[tuple[float, float]]:
        """已成功测量的 (m(A)/m(R), I(A)/I(R)) 点列表。"""
        pts: list[tuple[float, float]] = []
        for row in self.rows:
            ratio_m, ratio_i = row.get("ratio_m"), row.get("ratio_i")
            if row.get("ok") and ratio_m is not None and ratio_i is not None and ratio_m > 0:
                pts.append((float(ratio_m), float(ratio_i)))
        return pts

    def fit_result(self) -> dict[str, Any] | None:
        """最近一次拟合结果 {"K","intercept","r2","n"}；未拟合为 None。"""
        return self._fit

    def current_quantity(self) -> str:
        """当前峰强口径（``"area"`` 净峰面积 / ``"height"`` 净峰高）。"""
        return str(self.cmb_quantity.currentData() or "area")

    def record(self) -> dict:
        """导出为可存档的标定记录（JSON 结构）。"""
        return build_record(win_a=self._win_a, win_r=self._win_r,
                            mode=str(self.cmb_fit.currentData()), fit=self._fit,
                            rows=self.rows, quantity=self.current_quantity())

    def load_record(self, payload: dict) -> bool:
        """从 dict 载入标定记录；结构非法抛 ``ValueError``。"""
        parsed = parse_record(payload)
        self.rows = parsed["rows"]
        if parsed["win_a"] is not None:
            self._win_a = parsed["win_a"]
        if parsed["win_r"] is not None:
            self._win_r = parsed["win_r"]
        self.cmb_fit.setCurrentIndex(1 if parsed["mode"] == "origin" else 0)
        # 恢复口径时不触发重测失效（旧记录缺 quantity 时解析层已兜底为 area）
        self.cmb_quantity.blockSignals(True)
        self.cmb_quantity.setCurrentIndex(
            1 if parsed["quantity"] == "height" else 0)
        self.cmb_quantity.blockSignals(False)
        self._refresh()
        return True

    # ------------------------------------------------------------------ #
    # 动作
    # ------------------------------------------------------------------ #
    def _on_add(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("kwizard.add"), "", tr("filter.pattern"))
        for p in paths:
            self.add_row(p)

    def _on_remove(self) -> None:
        row = self.table.currentRow()
        if 0 <= row < len(self.rows):
            del self.rows[row]
            self._refresh()

    def _on_clear(self) -> None:
        self.rows.clear()
        self._fit = None
        self._refresh()

    def _on_wr_changed(self, row: int, wr: float) -> None:
        """手工修改 w(金红石型)% -> 重算 m(A)/m(R) 并重拟合。"""
        if not (0 <= row < len(self.rows)):
            return
        clamped = min(99.99, max(0.01, float(wr)))
        self.rows[row]["wr"] = clamped
        self.rows[row]["ratio_m"] = mass_ratio_from_wr(clamped)
        self._refresh()

    def _on_mr_changed(self, row: int, ratio_m: float) -> None:
        """手工修改 m(A)/m(R) -> 反算 w(金红石型)% 并重拟合。"""
        if not (0 <= row < len(self.rows)):
            return
        if ratio_m <= 0:
            return
        wr = 100.0 / (1.0 + float(ratio_m))
        self.rows[row]["wr"] = min(99.99, max(0.01, wr))
        self.rows[row]["ratio_m"] = float(ratio_m)
        self._refresh()

    def _on_quantity_changed(self, _index: int) -> None:
        """切换峰强口径：旧测量值属旧口径，全部置无效并提示重新「测量全部」。

        不禁用下拉（允许先切口径再测量），但旧 ratio_i 一律作废，
        杜绝旧口径的测量值混入新口径的拟合。
        """
        for row in self.rows:
            row["ratio_i"] = None
            row["ok"] = False
            row["message"] = tr("kwizard.remeasure")
        self._refresh()

    def _on_measure_all(self) -> None:
        """后台线程逐行测量 I(A)/I(R)，期间显示忙对话框。"""
        if not self.rows:
            QMessageBox.information(self, tr("msg.info"), tr("kwizard.no_point"))
            return
        specs = [{"file": r["file"], "wr": r["wr"]} for r in self.rows]
        run_busy_task(
            self, services.measure_calib_rows,
            args=(specs, self._win_a, self._win_r),
            kwargs={"quantity": self.current_quantity()},
            title=tr("busy.title_calib"), cancellable=services.supports_cancel("a"),
            degraded=not services.supports_progress("a"),
            on_success=self._apply_measure, on_error=self._show_error)

    def _apply_measure(self, measured: list[dict]) -> None:
        """回填测量结果并重拟合。"""
        for row, got in zip(self.rows, measured):
            row["ratio_i"] = got.get("ratio_i")
            row["ok"] = bool(got.get("ok"))
            row["message"] = str(got.get("message", ""))
        self._refresh()

    def _on_adopt(self) -> None:
        if self._fit is None:
            QMessageBox.information(self, tr("msg.info"), tr("kwizard.no_point"))
            return
        self.k_adopted.emit(self._fit["K"], self._fit["intercept"],
                            self._fit["r2"], self.current_quantity())
        self.accept()

    # ------------------------------------------------------------------ #
    # 存档 / 载入
    # ------------------------------------------------------------------ #
    def _on_save(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, tr("kwizard.dlg.save"), "k_calibration.json", tr("kwizard.filter"))
        if not path:
            return
        try:
            Path(path).write_text(
                json.dumps(self.record(), ensure_ascii=False, indent=2),
                encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._show_error(exc)
            return
        QMessageBox.information(self, tr("msg.info"), tr("kwizard.saved", path=path))

    def _on_load(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, tr("kwizard.dlg.load"), "", tr("kwizard.filter"))
        if not path:
            return
        try:
            self.load_record(json.loads(Path(path).read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001
            QMessageBox.warning(self, tr("msg.error"),
                                tr("kwizard.load_fail", detail=exc))

    # ------------------------------------------------------------------ #
    # 视图刷新
    # ------------------------------------------------------------------ #
    def _refresh(self) -> None:
        """表格重建 -> 重拟合 -> 刷新结果行/警示/曲线。"""
        self.table.render_rows(self.rows)
        self._refit()

    def _refit(self) -> None:
        """按当前口径重算 K 并刷新曲线/结果/警示。"""
        pts = self.measured_points()
        if len(pts) < 3:
            self._fit = None
            self._update_fit_view(note=tr("kwizard.min_points", n=len(pts)) if pts
                                  else tr("kwizard.no_point"))
            return
        try:
            res = services.calibrate_from_points(
                pts, force_zero=self.cmb_fit.currentData() == "origin")
        except services.CoreUnavailableError as exc:
            self._fit = None
            self._update_fit_view(note=str(exc), error=True)
            return
        except Exception as exc:  # noqa: BLE001 —— 统一转成可读提示
            self._fit = None
            self._update_fit_view(note=tr("msg.k_calib_fail", detail=exc), error=True)
            return
        self._fit = {"K": float(res.K), "intercept": float(res.intercept),
                     "r2": float(res.r2), "n": int(res.n_points)}
        self._update_fit_view()

    def _update_fit_view(self, note: str = "", *, error: bool = False) -> None:
        """统一刷新：结果行 + 警示行 + 曲线 + 采用按钮可用性。"""
        if self._fit is None:
            self.lbl_result.setText(note or tr("verdict.na"))
            self.lbl_warn.hide()
            self.btn_adopt.setEnabled(False)
            self.canvas.clear_view()
            return
        fit = self._fit
        self.lbl_result.setText(tr("kwizard.result", k=fit["K"], b=fit["intercept"],
                                   r2=fit["r2"], n=fit["n"]))
        if fit["r2"] < R2_WARN_LIMIT:
            self.lbl_warn.setText(tr("kwizard.warn_r2", r2=fit["r2"]))
            self.lbl_warn.show()
        else:
            self.lbl_warn.hide()
        if error and note:
            self.lbl_warn.setText(note)
            self.lbl_warn.show()
        self.btn_adopt.setEnabled(True)
        pts = self.measured_points()
        self.canvas.plot([p[0] for p in pts], [p[1] for p in pts],
                         k=fit["K"], intercept=fit["intercept"], r2=fit["r2"],
                         n=fit["n"])

    def _show_error(self, exc: Exception) -> None:
        """统一的异常提示（保留 CoreUnavailableError 语义）。"""
        if isinstance(exc, services.CoreUnavailableError):
            QMessageBox.critical(self, tr("msg.error"),
                                 tr("msg.core_unavailable", detail=exc))
        elif isinstance(exc, services.TaskCanceled):
            QMessageBox.information(self, tr("msg.info"), tr("msg.busy_canceled"))
        else:
            QMessageBox.critical(self, tr("msg.error"),
                                 tr("msg.k_calib_fail", detail=exc))

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.setWindowTitle(tr("kwizard.title"))
        self.lbl_intro.setText(tr("kwizard.intro"))
        self.table.retranslate()
        self.btn_add.setText(tr("kwizard.add"))
        self.btn_remove.setText(tr("kwizard.remove"))
        self.btn_clear.setText(tr("kwizard.clear"))
        self.btn_measure.setText(tr("kwizard.measure"))
        self.lbl_fit_mode.setText(tr("kwizard.fit_mode") + "：")
        self.cmb_fit.setItemText(0, tr("kwizard.fit.ols"))
        self.cmb_fit.setItemText(1, tr("kwizard.fit.origin"))
        self.lbl_quantity.setText(tr("kwizard.quantity") + "：")
        self.cmb_quantity.setItemText(0, tr("kwizard.quantity.area"))
        self.cmb_quantity.setItemText(1, tr("kwizard.quantity.height"))
        self.btn_load.setText(tr("kwizard.load"))
        self.btn_save.setText(tr("kwizard.save"))
        self.btn_adopt.setText(tr("kwizard.adopt"))
        self.btn_close.setText(tr("dialog.close"))
        self.canvas.retranslate()
        self.table.render_rows(self.rows)
        self._update_fit_view()
