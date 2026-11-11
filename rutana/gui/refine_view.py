"""B 法精修结构摘要：面板内的紧凑区 + 「更多信息」详情窗口。

两处界面共用本模块：

- :class:`RefineSummaryBox` —— 贴在 B 法结果卡下方的紧凑区，一相两行文字
  （第一行晶胞参数；第二行晶胞体积与晶粒尺寸），只留一个「更多信息…」按钮；
- :class:`RefineDetailDialog` —— 把 :class:`RefineSummary` 的全部字段摆开：
  每相晶胞六参数与体积、每相峰形与微结构、全局峰形参数与拟合统计。

数据来源单一：core 的 :func:`rutana.core.phasepeak.refined_summary`。控件只做
格式化与展示，不碰算法（与 :mod:`rutana.gui.peaks_panel` 同款约束）。语言
热切换靠 ``retranslate`` 重设文案后按**缓存摘要**重排，不重算任何数值。
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from rutana.i18n import tr

if TYPE_CHECKING:  # 仅类型提示，运行期不把 GUI 绑到 core 上
    from rutana.core.phasepeak import RefinedPhase, RefineSummary

COLOR_MUTED = "#64748B"
COLOR_TEXT = "#0F172A"

#: 判「同一根轴」的容差（Å / 度）
AXIS_TOL = 1e-4
#: 直角判据（度）
RIGHT_ANGLE = 90.0
#: 详情表最多直接显示的行数（再多就滚动，避免窗口被表格撑高）
MAX_VISIBLE_ROWS = 8

#: 内置两相的显示名键（与 :mod:`rutana.gui.peaks_panel` 同源）
PHASE_NAME_KEYS = {"anatase": "phase.anatase", "rutile": "phase.rutile"}

#: 晶胞表的轴列（长度单位与角度单位本身跨语言通用，不进 i18n 表）
CELL_HEADERS = ("a / Å", "b / Å", "c / Å", "α / °", "β / °", "γ / °", "V / Å³")


# --------------------------------------------------------------------------- #
# 纯格式化函数（无 Qt 状态，便于单元测试）
# --------------------------------------------------------------------------- #
def phase_name(phase: str) -> str:
    """物相显示名（内置两相走 i18n；附加相直接用 CIF 名）。"""
    key = PHASE_NAME_KEYS.get(str(phase))
    return tr(key) if key else str(phase)


def fmt_num(value: float | None, spec: str) -> str:
    """浮点格式化：缺失值（None / nan / inf）统一显示「—」。"""
    try:
        v = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return tr("verdict.na")
    if not math.isfinite(v):
        return tr("verdict.na")
    return spec.format(v)


def _same(x: float, y: float, tol: float = AXIS_TOL) -> bool:
    return abs(float(x) - float(y)) <= tol


def cell_text(p: RefinedPhase) -> str:
    """紧凑视图的晶胞参数单行文本。

    等轴相写 ``a = …``、四方相写 ``a = b = …，c = …``（避免把两根等长轴
    抄两遍），其余写三根轴；角度非直角时在末尾补 α/β/γ 一项。
    """
    sa, sb, sc = (fmt_num(p.a, "{:.4f}"), fmt_num(p.b, "{:.4f}"),
                  fmt_num(p.c, "{:.4f}"))
    if _same(p.a, p.b) and _same(p.b, p.c):
        text = tr("b.summary.cell_cubic", a=sa)
    elif _same(p.a, p.b):
        text = tr("b.summary.cell_tet", a=sa, c=sc)
    else:
        text = tr("b.summary.cell_tri", a=sa, b=sb, c=sc)
    if not all(_same(x, RIGHT_ANGLE) for x in (p.alpha, p.beta, p.gamma)):
        text += tr("b.summary.angles", alpha=fmt_num(p.alpha, "{:.3f}"),
                   beta=fmt_num(p.beta, "{:.3f}"),
                   gamma=fmt_num(p.gamma, "{:.3f}"))
    return text


def vol_size_text(p: RefinedPhase) -> str:
    """紧凑视图的第二行：晶胞体积 + 晶粒尺寸。"""
    return tr("b.summary.vol_size", v=fmt_num(p.volume, "{:.2f}"),
              d=fmt_num(getattr(p, "size_nm", None), "{:.1f}"))


def full_tooltip(p: RefinedPhase) -> str:
    """悬停提示：完整六参数 + 体积 + 晶粒（只有符号与数字，跨语言通用）。"""
    size = getattr(p, "size_nm", None)
    a, b, c = (fmt_num(p.a, "{:.4f}"), fmt_num(p.b, "{:.4f}"),
               fmt_num(p.c, "{:.4f}"))
    al, be, ga = (fmt_num(p.alpha, "{:.3f}"), fmt_num(p.beta, "{:.3f}"),
                  fmt_num(p.gamma, "{:.3f}"))
    vol, dia = fmt_num(p.volume, "{:.2f}"), fmt_num(size, "{:.1f}")
    lines = [
        phase_name(p.name),
        f"a = {a} Å    b = {b} Å    c = {c} Å",
        f"α = {al}°    β = {be}°    γ = {ga}°",
        f"V = {vol} Å³    D = {dia} nm",
    ]
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 面板紧凑区
# --------------------------------------------------------------------------- #
class RefineSummaryBox(QGroupBox):
    """B 法面板的紧凑精修摘要区（每相：晶胞参数一行 / 体积与晶粒一行）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary: RefineSummary | None = None
        self._value_labels: list[QLabel] = []
        box = QVBoxLayout(self)
        box.setContentsMargins(9, 6, 9, 6)
        box.setSpacing(3)

        self._rows = QVBoxLayout()
        self._rows.setSpacing(3)
        box.addLayout(self._rows)

        self.lbl_empty = QLabel(self)
        self.lbl_empty.setWordWrap(True)
        self.lbl_empty.setStyleSheet(f"font-size:11px; color:{COLOR_MUTED};")
        box.addWidget(self.lbl_empty)

        self.btn_more = QPushButton(self)
        self.btn_more.clicked.connect(self.open_more)
        box.addWidget(self.btn_more)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 数据
    # ------------------------------------------------------------------ #
    def set_summary(self, summary: RefineSummary | None) -> None:
        """载入一次精修摘要（``None`` = 回到空态）。"""
        self._summary = summary
        self._rebuild()

    def summary(self) -> RefineSummary | None:
        """当前缓存的摘要（无结果为 None）。"""
        return self._summary

    def clear(self) -> None:
        """回到空态（尚未精修 / 结果已作废）。"""
        self.set_summary(None)

    def phase_count(self) -> int:
        """当前展示的物相数（空态为 0）。"""
        return 0 if self._summary is None else len(self._summary.phases)

    def value_texts(self) -> list[str]:
        """每相的值文本（换行分隔两行）——供测试断言。"""
        return [lab.text() for lab in self._value_labels]

    # ------------------------------------------------------------------ #
    # 「更多信息」
    # ------------------------------------------------------------------ #
    def open_more(self) -> QDialog | None:
        """弹出「更多信息」窗口（空态不弹，按钮此时也是禁用的）。"""
        if self._summary is None:
            return None
        dlg = RefineDetailDialog(self._summary, self)
        dlg.exec()
        return dlg

    # ------------------------------------------------------------------ #
    # 渲染
    # ------------------------------------------------------------------ #
    def _rebuild(self) -> None:
        """按缓存摘要重排行；语言切换也走这里（文案全部现取 tr）。"""
        while self._rows.count():
            item = self._rows.takeAt(0)
            w = item.widget()
            if w is not None:
                w.deleteLater()
        self._value_labels.clear()

        empty = self._summary is None or not self._summary.phases
        self.lbl_empty.setVisible(empty)
        self.btn_more.setEnabled(not empty)
        if empty:
            return
        for p in self._summary.phases:
            self._rows.addWidget(self._phase_row(p))

    def _phase_row(self, p: RefinedPhase) -> QWidget:
        row = QWidget(self)
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(6)
        name = QLabel(phase_name(p.name), row)
        name.setStyleSheet("font-size:12px; font-weight:600;")
        val = QLabel(f"{cell_text(p)}\n{vol_size_text(p)}", row)
        val.setStyleSheet("font-size:11px;")
        val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        tip = full_tooltip(p)
        name.setToolTip(tip)
        val.setToolTip(tip)
        h.addWidget(name)
        h.addStretch(1)
        h.addWidget(val)
        self._value_labels.append(val)
        return row

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        """语言热切换：标题 / 按钮 / 空态提示 / 缓存行（不重算数值）。"""
        self.setTitle(tr("b.summary.title"))
        self.btn_more.setText(tr("b.summary.more"))
        self.btn_more.setToolTip(tr("b.summary.more.tip"))
        self.lbl_empty.setText(tr("b.summary.empty"))
        self._rebuild()


# --------------------------------------------------------------------------- #
# 「更多信息」窗口
# --------------------------------------------------------------------------- #
def _table(headers: list[str] | tuple[str, ...], rows: list[list[str]],
           parent: QWidget) -> QTableWidget:
    """只读等宽表（首列左对齐，其余居中），高度按行数撑开（超 10 行滚动）。"""
    tbl = QTableWidget(len(rows), len(headers), parent)
    tbl.setHorizontalHeaderLabels([str(h) for h in headers])
    tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
    tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
    tbl.setAlternatingRowColors(True)
    tbl.setShowGrid(False)
    tbl.verticalHeader().setVisible(False)
    tbl.verticalHeader().setDefaultSectionSize(22)
    tbl.setStyleSheet("QTableWidget { font-size:12px; }")
    header = tbl.horizontalHeader()
    header.setSectionResizeMode(QHeaderView.Stretch)
    header.setHighlightSections(False)
    for r, cells in enumerate(rows):
        for c, text in enumerate(cells):
            item = QTableWidgetItem(str(text))
            item.setFlags(Qt.ItemIsSelectable | Qt.ItemIsEnabled)
            item.setTextAlignment((Qt.AlignLeft if c == 0 else Qt.AlignHCenter)
                                  | Qt.AlignVCenter)
            tbl.setItem(r, c, item)
    # QTableWidget 的 sizeHint 与行数无关（固定 256×192），只靠布局算不出内容
    # 高度：这里把高度钉成「表头 + 行 × 行高」，超过 10 行则滚动（与主峰表同款）。
    header_h = header.height() or 26
    height = min(header_h + 22 * max(1, len(rows)) + 4, 26 + 22 * MAX_VISIBLE_ROWS + 4)
    tbl.setMinimumHeight(height)
    tbl.setMaximumHeight(height)
    return tbl


class RefineDetailDialog(QDialog):
    """「更多信息」窗口：精修后的全部可展示结果。

    文案在构造时取一次 ``tr``（本窗口是短生命周期的模态窗，语言热切换后由
    面板重开即可）；数值全部来自 :class:`RefineSummary`，不在此重算。
    """

    def __init__(self, summary: RefineSummary, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._summary = summary
        self.setWindowTitle(tr("b.more.title"))
        self.resize(860, 520)

        root = QVBoxLayout(self)
        root.setSpacing(8)

        self.lbl_head = QLabel(tr(
            "b.more.head",
            rwp=fmt_num(summary.rwp, "{:.2f}"), rp=fmt_num(summary.rp, "{:.2f}"),
            chi2=fmt_num(summary.chi2, "{:.3f}"),
            lam=fmt_num(summary.wavelength, "{:.4f}")), self)
        self.lbl_head.setStyleSheet(
            f"font-size:13px; font-weight:600; color:{COLOR_TEXT};")
        root.addWidget(self.lbl_head)

        root.addWidget(self._cell_group())
        root.addWidget(self._shape_group())
        root.addWidget(self._global_group())
        root.addStretch(1)

        self.lbl_note = QLabel(tr("b.more.note"), self)
        self.lbl_note.setWordWrap(True)
        self.lbl_note.setStyleSheet(f"font-size:11px; color:{COLOR_MUTED};")
        root.addWidget(self.lbl_note)

        buttons = QDialogButtonBox(QDialogButtonBox.Close, self)
        buttons.button(QDialogButtonBox.Close).setText(tr("b.more.close"))
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        root.addWidget(buttons)

    # ------------------------------------------------------------------ #
    # 分区
    # ------------------------------------------------------------------ #
    def _cell_group(self) -> QGroupBox:
        """每相晶胞六参数与体积（精修后的缩放值）。"""
        grp = QGroupBox(tr("b.more.cell"), self)
        box = QVBoxLayout(grp)
        rows = [[phase_name(p.name), fmt_num(p.a, "{:.4f}"), fmt_num(p.b, "{:.4f}"),
                 fmt_num(p.c, "{:.4f}"), fmt_num(p.alpha, "{:.3f}"),
                 fmt_num(p.beta, "{:.3f}"), fmt_num(p.gamma, "{:.3f}"),
                 fmt_num(p.volume, "{:.2f}")] for p in self._summary.phases]
        self.tbl_cell = _table([tr("peaks.col.phase"), *CELL_HEADERS], rows, grp)
        box.addWidget(self.tbl_cell)
        return grp

    def _shape_group(self) -> QGroupBox:
        """每相标度、最强峰位与半峰宽、晶粒、择优取向。"""
        grp = QGroupBox(tr("b.more.shape"), self)
        box = QVBoxLayout(grp)
        headers = [tr("peaks.col.phase"), tr("b.more.col.scale"), "2θ / °",
                   "FWHM / °", tr("b.more.col.size"), tr("b.more.col.po")]
        rows = [[phase_name(p.name), fmt_num(p.scale, "{:.4g}"),
                 fmt_num(p.two_theta, "{:.3f}"), fmt_num(p.fwhm, "{:.4f}"),
                 fmt_num(getattr(p, "size_nm", None), "{:.1f}"),
                 fmt_num(getattr(p, "po_r", None), "{:.4f}")]
                for p in self._summary.phases]
        self.tbl_shape = _table(headers, rows, grp)
        box.addWidget(self.tbl_shape)
        return grp

    def _global_group(self) -> QGroupBox:
        """全局峰形参数与拟合统计（两列排布，省高度）。"""
        grp = QGroupBox(tr("b.more.globals"), self)
        grid = QGridLayout(grp)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(4)
        s = self._summary
        items = [
            (tr("b.more.lam"), fmt_num(s.wavelength, "{:.4f}")),
            (tr("b.more.zero"), fmt_num(s.zero, "{:.4f}")),
            (tr("b.more.u"), fmt_num(s.u, "{:.5f}")),
            (tr("b.more.v"), fmt_num(s.v, "{:.5f}")),
            (tr("b.more.w"), fmt_num(s.w, "{:.5f}")),
            (tr("b.more.eta"), fmt_num(s.eta, "{:.3f}")),
            (tr("b.more.asym"), fmt_num(s.asym, "{:.4f}")),
            (tr("b.more.bfactor"), fmt_num(s.bfactor, "{:.3f}")),
            (tr("b.more.iters"), str(int(s.iters))),
            (tr("b.more.restarted"), tr("b.more.yes") if s.restarted
             else tr("b.more.no")),
            (tr("b.more.dropped"), self._dropped_text()),
        ]
        self._global_values: dict[str, str] = {}
        for i, (lab, val) in enumerate(items):
            r, c = divmod(i, 2)
            lw = QLabel(lab + "：", grp)
            lw.setStyleSheet(f"font-size:12px; color:{COLOR_MUTED};")
            vw = QLabel(val, grp)
            vw.setStyleSheet("font-size:12px; font-weight:600;")
            grid.addWidget(lw, r, c * 2)
            grid.addWidget(vw, r, c * 2 + 1)
            self._global_values[lab] = val
        return grp

    def _dropped_text(self) -> str:
        """被丢弃的物相序号（1 起，逗号分隔）；无丢相显示「—」。"""
        idx = self._summary.dropped
        if not idx:
            return tr("verdict.na")
        return ", ".join(str(int(i) + 1) for i in idx)

    # ------------------------------------------------------------------ #
    # 查询（供测试）
    # ------------------------------------------------------------------ #
    def global_values(self) -> dict[str, str]:
        """全局区分项 -> 显示值。"""
        return dict(self._global_values)
