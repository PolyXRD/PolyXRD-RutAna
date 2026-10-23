"""PolyXRD RutAna 主窗口。

布局：左侧导入谱图与文件列表；中部 matplotlib 画布；右侧 QTabWidget
（A 法 / B 法）。菜单：文件 / 语言（运行时热切换）/ 帮助（关于、版权）。
状态栏显示当前语言与文件路径。所有 core 交互经 ``rutana.gui.services``。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QActionGroup, QIcon
from PySide6.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from rutana import edition
from rutana.gui import services
from rutana.gui.batch import is_tool_csv
from rutana.gui.canvas import PatternCanvas
from rutana.gui.dialogs import AboutDialog, CopyrightDialog
from rutana.gui.exports import ExportMixin
from rutana.gui.resources import resource_path
from rutana.gui.tabs import MethodTabs
from rutana.gui.tasks import TaskMixin
from rutana.i18n import (
    available_languages,
    current_language,
    load_language,
    save_language,
    set_language,
    tr,
)
from rutana.version import APP_NAME, __version__

LANG_ORDER = ("zh_CN", "en_US", "ja_JP")

#: 内部评估版状态栏提示的字色（醒目红，状态栏灰底上对比度足够）
INTERNAL_NOTICE_COLOR = "#C00000"

#: 状态栏「语言/文件」信息区占状态栏宽度的上限（超出则中段省略路径）。
#: 取 0.3：为居中的版次提示留出「越过中线的余量」，否则文本在几何上无处安放
FILE_STATUS_MAX_RATIO = 0.3

#: 「添加文件夹…」用的谱图扩展名（与 filter.pattern 的口径一致）
PATTERN_EXTS = (
    ".xy", ".txt", ".dat", ".csv", ".raw", ".org", ".rsm", ".rbg",
    ".rk1", ".rax", ".rlz", ".rfi", ".mdi", ".gsas", ".gss", ".gsa",
    ".gda", ".fxye", ".ras", ".rasx", ".xye", ".qye", ".chi", ".qchi",
    ".xrdml", ".xml", ".brml", ".json", ".smz",
)


class MainWindow(TaskMixin, ExportMixin, QMainWindow):
    """主窗口：导入 → 计算 → 出结果三击可达。

    计算过程全部在 :mod:`rutana.gui.tasks` 的后台线程中完成，
    前台由 BusyDialog 显示「正在计算/正在拟合」与已用时，界面不冻结。
    """

    def __init__(self) -> None:
        super().__init__()
        load_language()
        self._patterns: dict[str, object] = {}   # {路径: Pattern}，保持插入序
        self._last_a: dict | None = None         # 最近一次 A 法汇总
        self._last_b: dict | None = None         # 最近一次 B 法汇总
        # v1.5.0 注册机制（registered 版次；internal 版次 _reg 恒为 None）
        self._reg = None
        self.act_regcode = None
        if not edition.IS_INTERNAL:
            from rutana.gui import registration  # 延迟导入：internal 版次不含该模块
            registration.set_language(current_language().split("_")[0])
            self._reg = registration.RegistrationManager(
                APP_NAME, registration.default_state_path("PolyXRD-RutAna"))
        self._build_actions()
        self._build_menus()
        self._build_central()
        self._build_status()
        self.retranslateUi()

    # ------------------------------------------------------------------ #
    # 构建界面
    # ------------------------------------------------------------------ #
    def _build_actions(self) -> None:
        """创建全部 QAction（文案在 retranslateUi 中统一设置）。"""
        self.act_open = QAction(self)
        self.act_open.triggered.connect(self._on_open)
        self.act_add_folder = QAction(self)
        self.act_add_folder.triggered.connect(self._on_add_folder)
        self.act_export_html = QAction(self)
        self.act_export_html.triggered.connect(self._on_export_html)
        self.act_export_csv = QAction(self)
        self.act_export_csv.triggered.connect(self._on_export_csv)
        self.act_export_png = QAction(self)
        self.act_export_png.triggered.connect(self._on_export_png)
        self.act_exit = QAction(self)
        self.act_exit.triggered.connect(self.close)

        self.act_about = QAction(self)
        self.act_about.triggered.connect(self._on_about)
        self.act_copyright = QAction(self)
        self.act_copyright.triggered.connect(self._on_copyright)

        # 语言组（互斥、可勾选）
        self.lang_group = QActionGroup(self)
        self.lang_group.setExclusive(True)
        self.act_langs: dict[str, QAction] = {}
        for code in LANG_ORDER:
            act = QAction(self)
            act.setCheckable(True)
            act.triggered.connect(lambda _checked=False, c=code: self._on_language(c))
            self.lang_group.addAction(act)
            self.act_langs[code] = act

    def _build_menus(self) -> None:
        """组装三条菜单。"""
        self.menu_file = self.menuBar().addMenu("")
        self.menu_file.addAction(self.act_open)
        self.menu_file.addAction(self.act_add_folder)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_export_html)
        self.menu_file.addAction(self.act_export_csv)
        self.menu_file.addAction(self.act_export_png)
        self.menu_file.addSeparator()
        self.menu_file.addAction(self.act_exit)

        self.menu_language = self.menuBar().addMenu("")
        for code in LANG_ORDER:
            self.menu_language.addAction(self.act_langs[code])

        self.menu_help = self.menuBar().addMenu("")
        self.menu_help.addAction(self.act_about)
        self.menu_help.addAction(self.act_copyright)
        if not edition.IS_INTERNAL and self._reg is not None:
            self._reg.add_help_action(self.menu_help, self)
            self.act_regcode = self.menu_help.actions()[-1]

    def _build_central(self) -> None:
        """三栏布局：文件列表 | 画布 | 参数/结果选项卡。"""
        splitter = QSplitter(Qt.Horizontal, self)

        # 左：导入谱图
        left = QWidget(self)
        lv = QVBoxLayout(left)
        self.grp_files = QGroupBox(left)
        fv = QVBoxLayout(self.grp_files)
        self.file_list = QListWidget(self.grp_files)
        self.file_list.currentRowChanged.connect(self._on_file_selected)
        fv.addWidget(self.file_list)
        hb = QHBoxLayout()
        self.btn_add = QPushButton(self.grp_files)
        self.btn_add.clicked.connect(self._on_open)
        self.btn_remove = QPushButton(self.grp_files)
        self.btn_remove.clicked.connect(self._on_remove_file)
        self.btn_clear = QPushButton(self.grp_files)
        self.btn_clear.clicked.connect(self._on_clear_files)
        for w in (self.btn_add, self.btn_remove, self.btn_clear):
            hb.addWidget(w)
        fv.addLayout(hb)
        lv.addWidget(self.grp_files)
        splitter.addWidget(left)

        # 中：画布
        self.canvas = PatternCanvas(self)
        splitter.addWidget(self.canvas)

        # 右：A/B 法选项卡
        self.tabs = MethodTabs(self)
        self.tabs.a_panel.compute_requested.connect(self.run_task_a)
        self.tabs.a_panel.batch_requested.connect(self.run_task_a_batch)
        self.tabs.a_panel.k_help_requested.connect(self.open_k_help)
        self.tabs.a_panel.k_wizard_requested.connect(self.open_k_wizard)
        self.tabs.b_panel.run_requested.connect(self.run_task_b)
        self.tabs.b_panel.batch_requested.connect(self.run_task_b_batch)
        splitter.addWidget(self.tabs)

        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([210, 520, 330])
        self.setCentralWidget(splitter)
        icon = resource_path("app-icon.png")
        if icon.exists():
            self.setWindowIcon(QIcon(str(icon)))

    def _build_status(self) -> None:
        """状态栏：左语言/文件；中部版次提示（internal）或右侧注册单位（registered）。"""
        self.lbl_lang = QLabel(self)
        self.lbl_file = QLabel(self)
        self.statusBar().addWidget(self.lbl_lang, 0)
        # v1.6.1：文件标签不再吃 stretch（空白留给居中的版次提示），
        # 路径过长时由 _elide_file_status 中段省略，避免把居中提示挤到右侧
        self.statusBar().addWidget(self.lbl_file, 0)
        if not edition.IS_INTERNAL and self._reg is not None:
            # 注册标签：永久控件 + stretch=1，吃掉中间空白，名称贴右端；
            # 必须在其它 addWidget 之后调用，才能排在最右侧
            self._reg.attach_status_label(self.statusBar(), self)
        else:
            self._build_edition_label()

    # ------------------------------------------------------------------ #
    # 状态栏配平（internal 版次）
    # ------------------------------------------------------------------ #
    def _build_edition_label(self) -> None:
        """内部评估版次提示（v1.6.1）：状态栏居中、加粗、红色，字号不调整。

        ``addPermanentWidget(..., 1)`` 先让标签吃下右侧全部剩余空间，再由
        :meth:`_sync_status_layout` 用右侧内边距补偿左侧「语言/文件」占位，
        把文本几何中心拉回状态栏正中；字号沿用状态栏默认，只打开 ``setBold``。
        """
        self.lbl_edition = QLabel(self)
        self.lbl_edition.setObjectName("editionStatusLabel")
        self.lbl_edition.setAlignment(Qt.AlignCenter)
        font = self.lbl_edition.font()
        font.setBold(True)          # 只改字重，不改字号
        self.lbl_edition.setFont(font)
        self.lbl_edition.setStyleSheet(f"color: {INTERNAL_NOTICE_COLOR};")
        self.statusBar().addPermanentWidget(self.lbl_edition, 1)

    def _elide_file_status(self, text: str) -> None:
        """状态栏文件/消息文本：超过宽度上限时中段省略（完整内容进 tooltip）。

        上限取状态栏宽度的 :data:`FILE_STATUS_MAX_RATIO`，保证左侧信息区不会
        长到把居中的版次提示挤偏或挤没。
        """
        self._file_status_full = text
        self.lbl_file.setToolTip(text)
        cap = max(120, int(self.statusBar().width() * FILE_STATUS_MAX_RATIO))
        self.lbl_file.setText(
            self.lbl_file.fontMetrics().elidedText(text, Qt.ElideMiddle, cap))

    def _sync_status_layout(self) -> None:
        """状态栏水平配平：按当前几何重算文件标签省略宽度与版次提示居中补偿。

        居中补偿的推导：状态栏左侧「语言/文件」区占位使版次标签区域整体右移，
        设标签矩形为 [S, E]、状态栏宽 W，则文本中心原在 (S+E)/2；给标签加
        右侧内边距 m 后文本中心左移 m/2，故取 m = 2 × ((S+E)/2 - W/2) 即正中。
        该式只依赖实测几何，不依赖 QStatusBar 内部 spacing/margin 的取值；
        内边距再以「文字仍可完整绘制」为上限收口（防止内容矩形被压成负宽）。
        """
        bar = self.statusBar()
        if getattr(self, "_file_status_full", None) is not None:
            self._elide_file_status(self._file_status_full)
        lbl = getattr(self, "lbl_edition", None)
        if lbl is None or bar.width() <= 0:
            return
        # 文本刚改过时几何仍是旧值，先强制跑一遍布局再量（否则补偿会跳变）
        lay = bar.layout()
        if lay is not None:
            lay.activate()
        if lbl.width() <= 0:
            return
        need = 2 * (lbl.x() + lbl.width() / 2) - bar.width()   # 2×(中心−栏宽/2)
        room = lbl.width() - lbl.fontMetrics().horizontalAdvance(lbl.text()) - 4
        lbl.setContentsMargins(0, 0, max(0, min(int(need), max(0, room))), 0)

    def resizeEvent(self, event) -> None:
        """窗口尺寸变化后重新配平状态栏（居中补偿与省略宽度都依赖宽度）。"""
        super().resizeEvent(event)
        self._sync_status_layout()

    def showEvent(self, event) -> None:
        """首次显示后配平一次（首次 resize 早于布局，那时还量不到几何）。"""
        super().showEvent(event)
        self._sync_status_layout()

    def startup_registration(self) -> None:
        """启动注册检查（registered 版次）：未注册弹提示，已注册静默。

        由 ``__main__`` 在 ``window.show()`` 后经 ``QTimer.singleShot`` 调度，
        模态提示在事件循环起来后出现；internal 版次无操作。
        """
        if self._reg is not None:
            self._reg.startup_check(self)

    # ------------------------------------------------------------------ #
    # 多语言
    # ------------------------------------------------------------------ #
    def retranslateUi(self) -> None:
        """语言切换后刷新全部文案（菜单/按钮/表头/状态栏/画布）。"""
        self.setWindowTitle(f"{APP_NAME} v{__version__} · {tr('app.title')}")
        self.menu_file.setTitle(tr("menu.file"))
        self.menu_language.setTitle(tr("menu.language"))
        self.menu_help.setTitle(tr("menu.help"))
        self.act_open.setText(tr("menu.file.open"))
        self.act_add_folder.setText(tr("menu.file.add_folder"))
        self.act_export_html.setText(tr("menu.file.export_html"))
        self.act_export_csv.setText(tr("menu.file.export_csv"))
        self.act_export_png.setText(tr("menu.file.export_png"))
        self.act_exit.setText(tr("menu.file.exit"))
        self.act_about.setText(tr("menu.help.about"))
        self.act_copyright.setText(tr("menu.help.copyright"))
        for code, act in self.act_langs.items():
            act.setText(tr(f"lang.{code}"))
            act.setChecked(code == current_language())
        self.grp_files.setTitle(tr("panel.files"))
        self.btn_add.setText(tr("panel.files.add"))
        self.btn_remove.setText(tr("panel.files.remove"))
        self.btn_clear.setText(tr("panel.files.clear"))
        self.tabs.retranslate()
        self.canvas.retranslate()
        self.lbl_lang.setText(tr("status.lang", lang=tr(f"lang.{current_language()}")))
        if getattr(self, "lbl_edition", None) is not None:
            self.lbl_edition.setText(tr("status.internal_edition"))
        # 语言/文件文案变长会改变左侧信息区宽度，重算省略与居中补偿
        self._sync_status_layout()

    # ------------------------------------------------------------------ #
    # 槽：文件
    # ------------------------------------------------------------------ #
    def _on_open(self) -> None:
        """打开谱图（可多选），经 services 读取，失败弹中文提示。"""
        paths, _ = QFileDialog.getOpenFileNames(
            self, tr("dlg.open_pattern"), "", tr("filter.pattern"))
        self._import_paths(paths)

    def _on_add_folder(self) -> None:
        """添加文件夹：按扩展名批量导入该文件夹下的谱图（不含子目录）。"""
        folder = QFileDialog.getExistingDirectory(self, tr("dlg.add_folder"), "")
        if not folder:
            return
        paths = [str(p) for ext in PATTERN_EXTS
                 for p in sorted(Path(folder).glob(f"*{ext}"))]
        self._import_paths(paths)

    def _import_paths(self, paths) -> None:
        """读取并登记谱图；本工具产物 CSV 自动跳过；失败最后汇总弹一次。

        v1.3.0：批量导入不再逐文件弹模态框——累计失败后弹一次汇总
        （失败明细同步写状态栏）；「添加文件夹」把本工具导出的结果
        CSV 误当谱图的问题在此统一过滤（两条导入路径都经过本方法）。
        """
        if not paths:
            return
        last_ok: str | None = None
        ok_n = 0
        failed: list[str] = []
        skipped = 0
        for p in paths:
            if is_tool_csv(p):
                skipped += 1
                continue
            name = Path(p).name
            try:
                pat = services.load_pattern(p)
            except Exception as exc:  # noqa: BLE001 —— 统一转成用户可读提示
                failed.append(f"{name}: {exc}")
                continue
            self._patterns[p] = pat
            self.file_list.addItem(name)
            item = self.file_list.item(self.file_list.count() - 1)
            format_key = getattr(pat, "meta", {}).get("format_key")
            if format_key:
                item.setToolTip(f"{p}\nformat_key: {format_key}")
            last_ok = p
            ok_n += 1
        if last_ok:
            self.file_list.setCurrentRow(list(self._patterns).index(last_ok))
        if failed:
            preview = "、".join(failed[:5]) + ("…" if len(failed) > 5 else "")
            self.statusBar().showMessage("；".join(failed))
            text = tr("msg.import_fail_summary", ok=ok_n, fail=len(failed),
                      names=preview)
            if skipped:
                text += "\n" + tr("msg.import_skipped", n=skipped)
            self._msg_box(text, error=True)
        elif skipped:
            self._msg_box(tr("msg.import_skipped", n=skipped))

    def _on_remove_file(self) -> None:
        row = self.file_list.currentRow()
        if row < 0:
            return
        path = list(self._patterns)[row]
        del self._patterns[path]
        self.file_list.takeItem(row)
        self._refresh_canvas()

    def _on_clear_files(self) -> None:
        self._patterns.clear()
        self.file_list.clear()
        self._refresh_canvas()

    def _on_file_selected(self, row: int) -> None:
        if 0 <= row < len(self._patterns):
            self._refresh_canvas()

    def _refresh_canvas(self) -> None:
        """按当前选中项刷新画布与状态栏文件显示。"""
        path = self._current_path()
        if path is None:
            self.canvas.clear()
            self._elide_file_status(tr("status.ready"))
            self._sync_status_layout()
            return
        pat = self._patterns[path]
        self.canvas.show_pattern(np.asarray(pat.two_theta), np.asarray(pat.intensity))
        self._elide_file_status(tr("status.file", path=path))
        self._sync_status_layout()

    def _current_path(self) -> str | None:
        row = self.file_list.currentRow()
        if 0 <= row < len(self._patterns):
            return list(self._patterns)[row]
        return None

    def _current_pattern(self):
        path = self._current_path()
        return self._patterns[path] if path else None

    # ------------------------------------------------------------------ #
    # 槽：语言与帮助
    # ------------------------------------------------------------------ #
    def _on_language(self, code: str) -> None:
        set_language(code)
        save_language(code)
        self.retranslateUi()
        if not edition.IS_INTERNAL and self._reg is not None:
            from rutana.gui import registration  # 延迟导入：internal 版次不含该模块
            registration.set_language(code.split("_")[0])
            if self.act_regcode is not None:
                self.act_regcode.setText(registration.tr("输入注册码 (&R)…"))
            self._reg.refresh()

    def _on_about(self) -> None:
        AboutDialog(self).exec()

    def _on_copyright(self) -> None:
        CopyrightDialog(self).exec()

    # ------------------------------------------------------------------ #
    # 工具
    # ------------------------------------------------------------------ #
    def _msg(self, key: str, detail: str | None = None, error: bool = False) -> None:
        """统一弹窗：error=True 用错误样式，detail 填充 {detail} 占位。"""
        text = tr(key, detail=detail) if detail is not None else tr(key)
        self._msg_box(text, error=error)

    def _msg_box(self, text: str, *, error: bool = False) -> None:
        """显示一段已经本地化好的文本（供 TaskMixin 等复用）。"""
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Critical if error else QMessageBox.Information)
        box.setWindowTitle(tr("msg.error") if error else tr("msg.info"))
        box.setText(text)
        box.exec()
