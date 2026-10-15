"""A 法参数与结果面板（强度比值法）。

面板只负责采集参数与展示结果，与 core 的交互一律经由上层调
``rutana.gui.services`` 完成，再回填 ``set_result_a``。
所有文案经 i18n，``retranslate()`` 支持运行时热切换。

v1.0.0：K 分组重做（手输 K + 「K 值说明」+「K 标定向导…」两个入口，K 来源在
界面上明示）；结果卡给出 wa/wr + K + I(A)/I(R) + R² + 双平行差 + 合格判定，
并提供可选「参考真值」输入 → 显示相对误差（便于用真实标样验证）。
v1.2.0：新增「批量计算…」入口（与「计算比率」并排）。

B 法面板见 :mod:`rutana.gui.panels_b`（同一约束下拆出）；
选项卡容器见 :mod:`rutana.gui.tabs.MethodTabs`。
"""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from rutana.gui.resultcard import ResultCard
from rutana.i18n import tr

#: A 法结果卡行（顺序即显示顺序）
A_RESULT_ROWS = (
    "result.wa", "result.wr", "result.k", "result.ia_ir", "result.r2",
    "result.dup", "result.verdict", "result.ref_err",
)

#: R² 告警阈值（低于此值提示线性不佳）
R2_WARN_LIMIT = 0.995


class APanel(QWidget):
    """A 法（强度比值法）面板：双窗口、K 值、参考真值与结果卡。"""

    compute_requested = Signal()
    batch_requested = Signal()
    k_help_requested = Signal()
    k_wizard_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._k_override: float | None = None
        self._r2: float | None = None
        #: 峰强口径（"area" 净峰面积 / "height" 净峰高）；由 K 向导采用时同步
        self._quantity: str = "area"
        root = QVBoxLayout(self)

        # ---- 测量窗口 ----
        self.grp_windows = QGroupBox(self)
        grid = QVBoxLayout(self.grp_windows)
        for _row, phase_key in enumerate(("a.anatase", "a.rutile")):
            h = QHBoxLayout()
            lab = QLabel(self.grp_windows)
            h.addWidget(lab)
            spin_min = QDoubleSpinBox(self.grp_windows)
            spin_min.setRange(5.0, 90.0)
            spin_min.setDecimals(2)
            spin_min.setSingleStep(0.1)
            spin_max = QDoubleSpinBox(self.grp_windows)
            spin_max.setRange(5.0, 90.0)
            spin_max.setDecimals(2)
            spin_max.setSingleStep(0.1)
            if phase_key == "a.anatase":
                spin_min.setValue(24.5)
                spin_max.setValue(26.5)
            else:
                spin_min.setValue(26.5)
                spin_max.setValue(28.5)
            h.addWidget(spin_min)
            h.addWidget(spin_max)
            grid.addLayout(h)
            setattr(self, f"lab_{phase_key[2:]}", lab)
            setattr(self, f"sp_{'a' if phase_key == 'a.anatase' else 'r'}_min", spin_min)
            setattr(self, f"sp_{'a' if phase_key == 'a.anatase' else 'r'}_max", spin_max)
        root.addWidget(self.grp_windows)

        # ---- K 值 ----
        self.grp_k = QGroupBox(self)
        kv = QVBoxLayout(self.grp_k)
        h = QHBoxLayout()
        self.lbl_k = QLabel(self.grp_k)
        self.sp_k = QDoubleSpinBox(self.grp_k)
        self.sp_k.setRange(0.001, 1000.0)
        self.sp_k.setDecimals(3)
        self.sp_k.setValue(1.0)
        h.addWidget(self.lbl_k)
        h.addWidget(self.sp_k)
        h.addStretch(1)
        kv.addLayout(h)
        kh = QHBoxLayout()
        self.btn_k_help = QPushButton(self.grp_k)
        self.btn_k_help.clicked.connect(self.k_help_requested.emit)
        self.btn_k_wizard = QPushButton(self.grp_k)
        self.btn_k_wizard.clicked.connect(self.k_wizard_requested.emit)
        kh.addWidget(self.btn_k_help)
        kh.addWidget(self.btn_k_wizard)
        kv.addLayout(kh)
        self.lbl_kinfo = QLabel(tr("a.k.source_manual"), self.grp_k)
        self.lbl_kinfo.setWordWrap(True)
        self.lbl_kinfo.setStyleSheet("font-size:12px; color:#64748B;")
        kv.addWidget(self.lbl_kinfo)
        root.addWidget(self.grp_k)

        # ---- 参考真值（可选）----
        self.grp_ref = QGroupBox(self)
        rv = QVBoxLayout(self.grp_ref)
        self.chk_ref = QCheckBox(self.grp_ref)
        self.chk_ref.setChecked(False)
        self.chk_ref.toggled.connect(lambda _on: self.sp_ref.setEnabled(self.chk_ref.isChecked()))
        self.sp_ref = QDoubleSpinBox(self.grp_ref)
        self.sp_ref.setRange(0.0, 100.0)
        self.sp_ref.setDecimals(2)
        self.sp_ref.setValue(50.0)
        self.sp_ref.setEnabled(False)
        rh = QHBoxLayout()
        rh.addWidget(self.chk_ref)
        rh.addWidget(self.sp_ref)
        rv.addLayout(rh)
        root.addWidget(self.grp_ref)

        # ---- 计算（单文件 / 批量）----
        hb = QHBoxLayout()
        self.btn_compute = QPushButton(self)
        self.btn_compute.clicked.connect(self.compute_requested.emit)
        self.btn_batch = QPushButton(self)
        self.btn_batch.setToolTip(tr("a.batch.tip"))
        self.btn_batch.clicked.connect(self.batch_requested.emit)
        hb.addWidget(self.btn_compute)
        hb.addWidget(self.btn_batch)
        root.addLayout(hb)

        # ---- 结果卡 ----
        self.card_a = ResultCard(A_RESULT_ROWS, self, title_key="a.result_group")
        root.addWidget(self.card_a)
        root.addStretch(1)
        self.retranslate()

    # ------------------------------------------------------------------ #
    # 数据交换
    # ------------------------------------------------------------------ #
    def params(self) -> dict:
        """收集 A 法参数。"""
        return {
            "win_a": (self.sp_a_min.value(), self.sp_a_max.value()),
            "win_r": (self.sp_r_min.value(), self.sp_r_max.value()),
        }

    def current_k(self) -> float:
        """标定过则用标定 K，否则用手输 K。"""
        return self._k_override if self._k_override is not None else self.sp_k.value()

    def current_r2(self) -> float | None:
        """标定 R²（未标定时为 None）。"""
        return self._r2

    def current_quantity(self) -> str:
        """当前峰强口径（``"area"`` 净峰面积 / ``"height"`` 净峰高）。"""
        return self._quantity

    def set_quantity(self, quantity: str) -> None:
        """写入峰强口径（K 向导「采用此 K」时一并同步）。"""
        self._quantity = "height" if quantity == "height" else "area"

    def reference_value(self) -> float | None:
        """参考真值 w(金红石型)%；未启用返回 None。"""
        if not self.chk_ref.isChecked():
            return None
        return float(self.sp_ref.value())

    def set_k(self, k: float, r2: float | None = None) -> None:
        """写入标定结果并锁定 K。"""
        self._k_override = float(k)
        self._r2 = float(r2) if r2 is not None else None
        self._refresh_k_info()

    def clear_k(self) -> None:
        """回到手输 K（切换样品/清空标定时可调用）。"""
        self._k_override = None
        self._r2 = None
        self._refresh_k_info()

    def set_result_a(self, result, dup: dict | None = None,
                     r2: float | None = None, ref: float | None = None) -> None:
        """回填 A 法结果。

        result: RatioResult；dup: combine_duplicates 返回值；
        r2: 标定 R²（展示用）；ref: 参考真值 w(R)%（启用时显示相对误差）。
        """
        wa = float(getattr(result, "wa", 0.0))
        wr = float(getattr(result, "wr", 0.0))
        self.card_a.set_value("result.wa", f"{wa:.2f}")
        self.card_a.set_value("result.wr", f"{wr:.2f}")
        self.card_a.set_value("result.k", f"{float(getattr(result, 'K', 0.0)):.4f}")
        ia = float(getattr(result, "ia", 0.0))
        ir = float(getattr(result, "ir", 0.0))
        self.card_a.set_value("result.ia_ir",
                              f"{ia / ir:.4f}" if ir > 0 else tr("verdict.na"))
        if r2 is None:
            self.card_a.set_value("result.r2", tr("verdict.na"))
        else:
            self.card_a.set_value("result.r2", f"{r2:.4f}",
                                  "warn" if r2 < R2_WARN_LIMIT else "good")
        if dup is None:
            self.card_a.set_value("result.dup", tr("verdict.na"))
            self.card_a.set_value("result.verdict", tr("verdict.na"))
        else:
            self.card_a.set_value("result.dup", f"{dup['abs_diff']:.2f}")
            ok = bool(dup["within_limit"])
            self.card_a.set_value("result.verdict",
                                  tr("verdict.pass" if ok else "verdict.fail"),
                                  "good" if ok else "bad")
        self._set_ref_error(wr, ref)

    def clear_result_a(self) -> None:
        """结果卡复位（换谱/清空时用）。"""
        self.card_a.clear()

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslate(self) -> None:
        self.grp_windows.setTitle(tr("a.windows"))
        self.lab_anatase.setText(tr("a.anatase"))
        self.lab_rutile.setText(tr("a.rutile"))
        self.sp_a_min.setToolTip(tr("a.tmin"))
        self.sp_r_min.setToolTip(tr("a.tmin"))
        self.grp_k.setTitle(tr("a.k_group"))
        self.lbl_k.setText(tr("a.k.label"))
        self.btn_k_help.setText(tr("a.k_help"))
        self.btn_k_wizard.setText(tr("a.k_wizard"))
        self.grp_ref.setTitle(tr("result.ref_label"))
        self.chk_ref.setText(tr("a.ref_enable"))
        self.btn_compute.setText(tr("a.compute"))
        self.btn_batch.setText(tr("a.batch"))
        self.btn_batch.setToolTip(tr("a.batch.tip"))
        self.card_a.retranslate()
        self._refresh_k_info()

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _refresh_k_info(self) -> None:
        """刷新 K 来源说明行（手输 / 标定 + R²）。"""
        if self._k_override is None:
            self.lbl_kinfo.setText(tr("a.k.source_manual"))
            return
        if self._r2 is None:
            self.lbl_kinfo.setText(f"{tr('a.k.source_calib')}：K = {self._k_override:.4f}")
        else:
            self.lbl_kinfo.setText(
                f"{tr('a.k.source_calib')}：{tr('a.k.result', k=self._k_override, r2=self._r2)}")

    def _set_ref_error(self, wr: float, ref: float | None) -> None:
        """按参考真值（w(金红石型) wt%）计算并显示相对误差（%）。"""
        if ref is None or ref <= 0:
            self.card_a.set_value("result.ref_err", tr("verdict.na"))
            return
        rel = (wr - float(ref)) / float(ref) * 100.0
        self.card_a.set_value("result.ref_err", f"{rel:+.2f}",
                              "good" if abs(rel) <= 2.0 else "warn")
