"""导出功能 mixin：HTML 报告 / CSV / PNG。

从 MainWindow 拆出（单文件 ≤ 400 行约束），依赖宿主窗口提供的
``_current_pattern`` / ``_msg`` / ``canvas`` / ``_last_a`` / ``_last_b``。
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import numpy as np
from PySide6.QtWidgets import QFileDialog

from rutana.gui.report import build_html_report
from rutana.i18n import tr


def a_rows(result, dup: dict | None = None) -> list[tuple[str, str]]:
    """A 法结果 -> 报告行 [(标签, 值), ...]（标签已本地化）。"""
    rows = [
        (tr("result.wa"), f"{result.wa:.2f}"),
        (tr("result.wr"), f"{result.wr:.2f}"),
        (tr("result.k"), f"{result.K:.4f}"),
        (tr("result.ia"), f"{result.ia:.1f}"),
        (tr("result.ir"), f"{result.ir:.1f}"),
    ]
    if dup is not None:
        rows.append((tr("result.dup"), f"{dup['abs_diff']:.2f}"))
    return rows


class ExportMixin:
    """MainWindow 的导出行为（HTML 报告 / CSV 数据 / 谱图 PNG）。"""

    def _on_export_html(self) -> None:
        """导出自包含 HTML 报告（优先 A 法汇总，其次 B 法）。"""
        summary = self._last_a or self._last_b
        if summary is None:
            self._msg("msg.need_pattern")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_html"), "report.html", tr("filter.html"))
        if not path:
            return
        try:
            html = build_html_report(
                sample=summary["sample"], file_name=summary["file"],
                rows=summary["rows"], verdict=summary["verdict"],
                png_b64=self._canvas_png_b64())
            Path(path).write_text(html, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001 —— 统一转成用户可读提示
            self._msg("msg.export_fail", str(exc), error=True)
            return
        self._msg("msg.export_ok", path)

    def _on_export_csv(self) -> None:
        """导出当前谱图为两列 CSV。"""
        pat = self._current_pattern()
        if pat is None:
            self._msg("msg.need_pattern")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_csv"), "data.csv", tr("filter.csv"))
        if not path:
            return
        try:
            tt = np.asarray(pat.two_theta)
            ii = np.asarray(pat.intensity)
            lines = ["two_theta,intensity"] + [f"{a:.6g},{b:.6g}" for a, b in zip(tt, ii)]
            Path(path).write_text("\n".join(lines), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            self._msg("msg.export_fail", str(exc), error=True)
            return
        self._msg("msg.export_ok", path)

    def _on_export_png(self) -> None:
        """导出当前画布为 PNG。"""
        pat = self._current_pattern()
        if pat is None:
            self._msg("msg.need_pattern")
            return
        path, _ = QFileDialog.getSaveFileName(
            self, tr("dlg.export_png"), "pattern.png", tr("filter.png"))
        if not path:
            return
        try:
            self.canvas.save_png(path)
        except Exception as exc:  # noqa: BLE001
            self._msg("msg.export_fail", str(exc), error=True)
            return
        self._msg("msg.export_ok", path)

    def _canvas_png_b64(self) -> str:
        """把当前画布渲染为 PNG 并编码 base64（报告内嵌用）。"""
        buf = io.BytesIO()
        self.canvas.figure.savefig(buf, format="png", dpi=120, facecolor="white")
        return base64.b64encode(buf.getvalue()).decode("ascii")
