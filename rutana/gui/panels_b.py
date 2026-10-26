"""B 法参数与结果面板（Rietveld 全谱拟合）。

从 :mod:`rutana.gui.panels` 拆出（单文件 ≤400 行约束），内容与 A 法面板同源：
只负责采集参数与展示结果，core 交互经上层调 ``rutana.gui.services`` 完成，
再回填 ``set_rfactors`` / ``set_quantities``；文案全量走 i18n 热切换。

v1.2.0：新增「批量精修…」入口（与「运行精修」并排）。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from rutana.gui.resultcard import ResultCard
from rutana.gui.verdict import rwp_verdict
from rutana.i18n import tr

#: 附加 CIF 路径存放在 QListWidgetItem 的 UserRole
ROLE_CIF_PATH = Qt.UserRole + 1

#: B 法结果卡行（定量结果在前，R 因子在后）
B_RESULT_ROWS = ("result.b_wa", "result.b_wr",
                 "result.rwp", "result.rp", "result.chi2", "result.fit_verdict",
                 "result.b_po")

#: 「择优取向修正」复选框默认态（v1.4.0 真实数据实证后设定，
#: 见 docs/VALIDATION_v1.0.0.md §v1.4.0：preset 默认开 -> 勾选）
PO_CHECK_DEFAULT = True


class BPanel(QWidget):
    """B 法（Rietveld 全谱拟合）面板：物相清单、精修开关、运行与 R 因子。"""

    run_requested = Signal()
    batch_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        root = QVBoxLayout(self)

        # ---- 物相清单（内置两相只读）----
        self.grp_phases = QGroupBox(self)
        pv = QVBoxLayout(self.grp_phases)
        self.lst_phases = QListWidget(self.grp_phases)
        for key in ("b.phases.anatase", "b.phases.rutile"):
            item = QListWidgetItem(tr(key))
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self.lst_phases.addItem(item)
        pv.addWidget(self.lst_phases)
        self.btn_add_cif = QPushButton(self.grp_phases)
        self.btn_add_cif.clicked.connect(self._on_add_cif)
        pv.addWidget(self.btn_add_cif)
        root.addWidget(self.grp_phases)

        # ---- 精修参数 ----
        self.grp_refine = QGroupBox(self)
        rv = QVBoxLayout(self.grp_refine)
        self.chk_zero = QCheckBox(self.grp_refine)
        self.chk_zero.setChecked(True)
        self.chk_uvw = QCheckBox(self.grp_refine)
        self.chk_uvw.setChecked(True)
        self.chk_eta = QCheckBox(self.grp_refine)
        # v1.0.0 实证：真实粉末谱上 eta 必须精修（固定 0.54 差 1.8pp，
        # 见 docs/VALIDATION_v1.0.0.md §B.3），故默认勾选
        self.chk_eta.setChecked(True)
        # v1.4.0：择优取向（March–Dollase）修正；真实数据实证不劣化定量
        # （见 docs/VALIDATION_v1.0.0.md §v1.4.0），随 preset 默认勾选
        self.chk_po = QCheckBox(self.grp_refine)
        self.chk_po.setChecked(PO_CHECK_DEFAULT)
        for w in (self.chk_zero, self.chk_uvw, self.chk_eta, self.chk_po):
            rv.addWidget(w)
        h = QHBoxLayout()
        self.lbl_nbg = QLabel(self.grp_refine)
        self.sp_nbg = QSpinBox(self.grp_refine)
        self.sp_nbg.setRange(1, 8)
        self.sp_nbg.setValue(3)
        h.addWidget(self.lbl_nbg)
        h.addWidget(self.sp_nbg)
        h.addStretch(1)
        rv.addLayout(h)
        root.addWidget(self.grp_refine)

        # ---- 运行（单文件 / 批量）----
        hb = QHBoxLayout()
        self.btn_run = QPushButton(self)
        self.btn_run.clicked.connect(self.run_requested.emit)
        self.btn_batch = QPushButton(self)
        self.btn_batch.setToolTip(tr("b.batch.tip"))
        self.btn_batch.clicked.connect(self.batch_requested.emit)
        hb.addWidget(self.btn_run)
        hb.addWidget(self.btn_batch)
        root.addLayout(hb)
        self.lbl_busy = QLabel(tr("status.computing"), self)
        self.lbl_busy.setStyleSheet("font-size:12px; color:#0284C7;")
        self.lbl_busy.hide()
        root.addWidget(self.lbl_busy)

        # ---- R 因子结果卡 ----
        self.card_b = ResultCard(B_RESULT_ROWS, self, title_key="b.rfactors")
        root.addWidget(self.card_b)
        root.addStretch(1)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 数据交换
    # ------------------------------------------------------------------ #
    def params(self) -> dict:
        """收集 B 法参数（含附加 CIF 路径）。"""
        extra = []
        for i in range(self.lst_phases.count()):
            path = self.lst_phases.item(i).data(ROLE_CIF_PATH)
            if path:
                extra.append(str(path))
        return {
            "refine_zero": self.chk_zero.isChecked(),
            "refine_uvw": self.chk_uvw.isChecked(),
            "refine_eta": self.chk_eta.isChecked(),
            "refine_po": self.chk_po.isChecked(),
            "n_bg": self.sp_nbg.value(),
            "extra_cifs": tuple(extra),
        }

    def set_busy(self, busy: bool) -> None:
        """切换忙碌状态（忙窗为主，面板此处仅同步禁用运行按钮与提示行）。"""
        self.lbl_busy.setVisible(busy)
        self.btn_run.setEnabled(not busy)
        self.btn_batch.setEnabled(not busy)

    def set_quantities(self, wa: float | None, wr: float | None) -> None:
        """回填内置两相质量分数（定量失败时显示「—」）。"""
        self.card_b.set_value("result.b_wa",
                              f"{wa:.2f}" if wa is not None else tr("verdict.na"))
        self.card_b.set_value("result.b_wr",
                              f"{wr:.2f}" if wr is not None else tr("verdict.na"))

    def set_rfactors(self, rwp: float, rp: float, chi2: float) -> None:
        """回填 R 因子；判定按 v1.6.2 四档口径（见 :mod:`rutana.gui.verdict`）。

        很好 → 绿、良好 → 蓝、尚可 → 琥珀、不佳 → 红；Rwp 行与「拟合判定」行同色。
        """
        key, level = rwp_verdict(rwp)
        self.card_b.set_value("result.rwp", f"{rwp:.2f}", level)
        self.card_b.set_value("result.rp", f"{rp:.2f}")
        self.card_b.set_value("result.chi2", f"{chi2:.3f}")
        self.card_b.set_value("result.fit_verdict", tr(key), level)

    def set_po(self, ra: float | None, rr: float | None) -> None:
        """回填择优取向 r（锐钛/金红石）；缺失（未精修或无结果）显示「—」。"""
        if ra is None or rr is None:
            self.card_b.set_value("result.b_po", tr("verdict.na"))
            return
        self.card_b.set_value("result.b_po", f"{ra:.2f} / {rr:.2f}")

    def clear_rfactors(self) -> None:
        """R 因子卡复位。"""
        self.card_b.clear()

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.grp_phases.setTitle(tr("b.phases"))
        if self.lst_phases.count() >= 2:
            self.lst_phases.item(0).setText(tr("b.phases.anatase"))
            self.lst_phases.item(1).setText(tr("b.phases.rutile"))
        self.btn_add_cif.setText(tr("b.add_cif"))
        self.grp_refine.setTitle(tr("b.refine"))
        self.chk_zero.setText(tr("b.refine.zero"))
        self.chk_uvw.setText(tr("b.refine.uvw"))
        self.chk_eta.setText(tr("b.refine.eta"))
        self.chk_po.setText(tr("b.refine.po"))
        self.chk_po.setToolTip(tr("b.refine.po.tip"))
        self.lbl_nbg.setText(tr("b.n_bg") + "：")
        self.btn_run.setText(tr("b.run"))
        self.btn_batch.setText(tr("b.batch"))
        self.btn_batch.setToolTip(tr("b.batch.tip"))
        self.lbl_busy.setText(tr("status.computing"))
        self.card_b.retranslate()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _on_add_cif(self) -> None:
        """选择附加 CIF 并加入物相清单（只增不改内置两相）。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("b.add_cif"), "", "CIF (*.cif *.CIF);;* (*)")
        for p in paths:
            item = QListWidgetItem(p)
            item.setData(ROLE_CIF_PATH, p)
            self.lst_phases.addItem(item)
