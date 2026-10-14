"""A 法 / B 法参数与结果面板。

面板只负责采集参数与展示结果，与 core 的交互一律经由 MainWindow 调
``rutana.gui.services`` 完成，再回填 ``set_result`` / ``set_rfactors``。
所有文案经 i18n，``retranslate()`` 支持运行时热切换。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from rutana.i18n import tr

#: 附加 CIF 路径存放在 QListWidgetItem 的 UserRole
ROLE_CIF_PATH = Qt.UserRole + 1


def _result_row() -> tuple[QLabel, QLabel]:
    """构造「标签: 值」一行，返回 (标签, 值) 控件（文案由 retranslate 填）。"""
    lab = QLabel()
    val = QLabel(tr("verdict.na"))
    val.setStyleSheet("font-weight:600;")
    return lab, val


class APanel(QWidget):
    """A 法（强度比值法）面板：双窗口、K 值、计算与结果卡。"""

    compute_requested = Signal()
    k_calibrate_requested = Signal(list)  # list[tuple[float, float]]

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._k_override: float | None = None
        self._r2: float | None = None
        root = QVBoxLayout(self)

        # ---- 测量窗口 ----
        self.grp_windows = QGroupBox(self)
        grid = QVBoxLayout(self.grp_windows)
        for row, phase_key in enumerate(("a.anatase", "a.rutile")):
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
        self.ed_calib = QPlainTextEdit(self.grp_k)
        self.ed_calib.setFixedHeight(72)
        self.ed_calib.setPlaceholderText(tr("a.k.table_hint"))
        kv.addWidget(self.ed_calib)
        self.btn_calib = QPushButton(self.grp_k)
        self.btn_calib.clicked.connect(self._on_calibrate)
        kv.addWidget(self.btn_calib)
        self.lbl_kinfo = QLabel(tr("verdict.na"), self.grp_k)
        kv.addWidget(self.lbl_kinfo)
        root.addWidget(self.grp_k)

        # ---- 计算 ----
        self.btn_compute = QPushButton(self)
        self.btn_compute.clicked.connect(self.compute_requested.emit)
        root.addWidget(self.btn_compute)

        # ---- 结果卡 ----
        self.grp_result = QGroupBox(self)
        rv = QVBoxLayout(self.grp_result)
        self.rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key in ("result.wa", "result.wr", "result.k", "result.ia",
                    "result.ir", "result.dup", "result.verdict"):
            lab, val = _result_row()
            self.rows[key] = (lab, val)
            row = QHBoxLayout()
            row.addWidget(lab)
            row.addStretch(1)
            row.addWidget(val)
            rv.addLayout(row)
        root.addWidget(self.grp_result)
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

    def set_k(self, k: float, r2: float) -> None:
        """写入标定结果并锁定 K。"""
        self._k_override = float(k)
        self._r2 = float(r2)
        self.lbl_kinfo.setText(tr("a.k.result", k=k, r2=r2))

    def set_result_a(self, result, dup: dict | None = None) -> None:
        """回填 A 法结果（result: RatioResult；dup: combine_duplicates 返回值）。"""
        self.rows["result.wa"][1].setText(f"{result.wa:.2f}")
        self.rows["result.wr"][1].setText(f"{result.wr:.2f}")
        self.rows["result.k"][1].setText(f"{result.K:.4f}")
        self.rows["result.ia"][1].setText(f"{result.ia:.1f}")
        self.rows["result.ir"][1].setText(f"{result.ir:.1f}")
        if dup is None:
            self.rows["result.dup"][1].setText(tr("verdict.na"))
            self.rows["result.verdict"][1].setText(tr("verdict.na"))
        else:
            self.rows["result.dup"][1].setText(f"{dup['abs_diff']:.2f}")
            key = "verdict.pass" if dup["within_limit"] else "verdict.fail"
            self.rows["result.verdict"][1].setText(tr(key))

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
        self.ed_calib.setPlaceholderText(tr("a.k.table_hint"))
        self.btn_calib.setText(tr("a.k.calibrate"))
        self.btn_compute.setText(tr("a.compute"))
        self.grp_result.setTitle(tr("a.result_group"))
        for key, (lab, _val) in self.rows.items():
            lab.setText(tr(key) + "：")

    # ------------------------------------------------------------------ #
    # 内部
    # ------------------------------------------------------------------ #
    def _on_calibrate(self) -> None:
        """解析标定表文本并发出标定请求（不足 3 行也交由上层给出提示）。"""
        points: list[tuple[float, float]] = []
        for line in self.ed_calib.toPlainText().splitlines():
            parts = [p for p in line.replace("，", ",").split(",") if p.strip()]
            if len(parts) < 2:
                continue
            try:
                points.append((float(parts[0]), float(parts[1])))
            except ValueError:
                continue
        self.k_calibrate_requested.emit(points)


class BPanel(QWidget):
    """B 法（Rietveld 全谱拟合）面板：物相清单、精修开关、运行与 R 因子。"""

    run_requested = Signal()

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
        self.chk_eta.setChecked(False)
        for w in (self.chk_zero, self.chk_uvw, self.chk_eta):
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

        # ---- 运行 ----
        self.btn_run = QPushButton(self)
        self.btn_run.clicked.connect(self.run_requested.emit)
        root.addWidget(self.btn_run)
        self.progress = QProgressBar(self)
        self.progress.setRange(0, 0)  # 忙碌指示
        self.progress.hide()
        root.addWidget(self.progress)

        # ---- R 因子结果卡 ----
        self.grp_rf = QGroupBox(self)
        fv = QVBoxLayout(self.grp_rf)
        self.rows: dict[str, tuple[QLabel, QLabel]] = {}
        for key in ("result.rwp", "result.rp", "result.chi2"):
            lab, val = _result_row()
            self.rows[key] = (lab, val)
            row = QHBoxLayout()
            row.addWidget(lab)
            row.addStretch(1)
            row.addWidget(val)
            fv.addLayout(row)
        root.addWidget(self.grp_rf)
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
            "n_bg": self.sp_nbg.value(),
            "extra_cifs": tuple(extra),
        }

    def set_busy(self, busy: bool) -> None:
        """切换忙碌状态（进度条 + 禁用运行按钮）。"""
        self.progress.setVisible(busy)
        self.btn_run.setEnabled(not busy)

    def set_rfactors(self, rwp: float, rp: float, chi2: float) -> None:
        """回填 R 因子。"""
        self.rows["result.rwp"][1].setText(f"{rwp:.2f}")
        self.rows["result.rp"][1].setText(f"{rp:.2f}")
        self.rows["result.chi2"][1].setText(f"{chi2:.3f}")

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
        self.lbl_nbg.setText(tr("b.n_bg") + "：")
        self.btn_run.setText(tr("b.run"))
        self.grp_rf.setTitle(tr("b.rfactors"))
        for key, (lab, _val) in self.rows.items():
            lab.setText(tr(key) + "：")

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


class MethodTabs(QTabWidget):
    """右侧参数/结果选项卡容器（A 法 / B 法）。"""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.a_panel = APanel(self)
        self.b_panel = BPanel(self)
        self.addTab(self.a_panel, "")
        self.addTab(self.b_panel, "")
        self.retranslate()

    def retranslate(self) -> None:
        self.setTabText(0, tr("tab.a"))
        self.setTabText(1, tr("tab.b"))
        self.a_panel.retranslate()
        self.b_panel.retranslate()
