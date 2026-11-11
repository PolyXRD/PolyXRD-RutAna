"""离屏（QT_QPA_PLATFORM=offscreen）抓取 UI 界面证据图。

用途：给评审/回归留**可见证据**——进度弹出窗口、K 值说明、K 标定向导、
A 法结果卡与 B 法 R 因子卡的实际渲染效果。

用法（必须在 PySide6 可用的解释器下运行）::

    QT_QPA_PLATFORM=offscreen python tools/capture_ui_evidence.py [输出目录]

输出目录缺省为 ``docs/evidence/``。
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rutana.gui.busy import BusyDialog  # noqa: E402
from rutana.gui.khelp import KHelpDialog  # noqa: E402
from rutana.gui.kwizard import KCalibWizardDialog  # noqa: E402
from rutana.gui.main_window import MainWindow  # noqa: E402
from rutana.gui.refine_view import RefineDetailDialog  # noqa: E402
from rutana.i18n import set_language, tr  # noqa: E402

#: 输出目录缺省值
DEFAULT_OUT = Path("docs") / "evidence"


def _synthetic_pattern():
    """合成一条带锐钛型/金红石型双峰的伪谱图（纯 numpy，不依赖真实数据文件）。"""
    tt = np.arange(20.0, 32.0, 0.02)
    anatase = 900.0 * np.exp(-0.5 * ((tt - 25.30) / 0.18) ** 2)
    rutile = 1100.0 * np.exp(-0.5 * ((tt - 27.44) / 0.20) ** 2)
    bg = 120.0 + 0.6 * (tt - 20.0)
    return SimpleNamespace(two_theta=tt, intensity=anatase + rutile + bg,
                           meta={"source": "synthetic"})


def _grab(widget, path: Path) -> Path:
    """显示 -> 刷新事件 -> 抓图 -> 存 PNG。"""
    widget.show()
    app = QApplication.instance()
    for _ in range(30):
        app.processEvents()
        time.sleep(0.01)
    QApplication.processEvents()
    pix = widget.grab()
    path.parent.mkdir(parents=True, exist_ok=True)
    pix.save(str(path), "PNG")
    return path


def _fill_main_window(win: MainWindow) -> None:
    """往主窗口灌入一份伪谱图 + 一次 A 法结果，便于截图展示。"""
    win._patterns["D:/data/demo-TiO2.xy"] = _synthetic_pattern()
    win.file_list.addItem("demo-TiO2.xy")
    win.file_list.setCurrentRow(0)
    panel = win.tabs.a_panel
    panel.sp_k.setValue(1.22)
    panel.set_k(1.2200, 0.9997)
    panel.chk_ref.setChecked(True)
    panel.sp_ref.setValue(42.0)
    result = SimpleNamespace(wa=42.46, wr=57.54, K=1.22, ia=1234.5, ir=1678.9)
    panel.set_result_a(
        result,
        dup={"wa_mean": 42.5, "abs_diff": 0.08, "within_limit": True, "limit": 0.15},
        r2=0.9997, ref=42.0)


def _demo_summary():
    """合成一份精修摘要（v1.7.1 截图用；数值取自 18% 实测谱的真实精修结果）。"""
    from rutana.core.phasepeak import RefinedPhase, RefineSummary

    return RefineSummary(
        phases=(
            RefinedPhase(name="anatase", a=3.7853, b=3.7853, c=9.5134,
                         alpha=90.0, beta=90.0, gamma=90.0, volume=136.31,
                         scale=0.003962, two_theta=25.335, fwhm=0.1528,
                         size_nm=53.3, po_r=1.0054),
            RefinedPhase(name="rutile", a=4.5937, b=4.5937, c=2.9593,
                         alpha=90.0, beta=90.0, gamma=90.0, volume=62.45,
                         scale=0.00384, two_theta=27.468, fwhm=0.1512,
                         size_nm=54.1, po_r=1.0167),
        ),
        wavelength=1.540598, zero=0.0325, u=0.03372, v=-0.04033, w=0.03069,
        eta=0.669, asym=0.0505, bfactor=0.308, rwp=9.29, rp=6.47, chi2=1.526,
        iters=113, restarted=False, dropped=())


def capture(out_dir: Path) -> list[Path]:
    """抓全部证据图，返回生成的文件路径列表。"""
    set_language("zh_CN")
    made: list[Path] = []

    # 1) 主窗口（A 法结果卡 + 谱图）
    win = MainWindow()
    _fill_main_window(win)
    win.resize(1280, 800)
    made.append(_grab(win, out_dir / "01_main_window_a.png"))

    # 2) B 法 R 因子卡 + 精修结构摘要（拟合良好）
    win.tabs.setCurrentIndex(1)
    win.tabs.b_panel.set_rfactors(8.42, 6.10, 1.234)
    win.tabs.b_panel.set_quantities(48.21, 51.79)
    win.tabs.b_panel.set_po(1.0054, 1.0167)
    win.tabs.b_panel.set_summary(_demo_summary())
    made.append(_grab(win, out_dir / "02_main_window_b.png"))

    # 2b) v1.7.1「更多信息」窗口（精修后的完整结果）
    made.append(_grab(RefineDetailDialog(_demo_summary(), win),
                      out_dir / "16_refine_more.png"))

    # 3) 忙对话框：确定百分比 + 迭代行
    busy = BusyDialog(win, title=tr("busy.title_refine"), cancellable=False)
    busy.start_timer()
    busy.set_message(tr("busy.refine", gen=12, rwp=8.42), 63)
    busy.set_iteration(12, 8.42)
    time.sleep(1.2)
    made.append(_grab(busy, out_dir / "03_busy_dialog_refine.png"))
    busy.finish()

    # 4) 忙对话框：不确定模式（降级路径）
    busy2 = BusyDialog(win, title=tr("busy.title"))
    busy2.start_timer()
    busy2.set_message(tr("busy.measure"))
    busy2.set_degraded(True)
    time.sleep(1.2)
    made.append(_grab(busy2, out_dir / "04_busy_dialog_degraded.png"))
    busy2.finish()

    # 5) 忙对话框：真实 core 进度（A 法支持取消 -> 显示取消按钮）
    busy3 = BusyDialog(win, title=tr("busy.title"), cancellable=True)
    busy3.start_timer()
    busy3.set_message("正在定位峰位与积分", 38)
    time.sleep(1.2)
    made.append(_grab(busy3, out_dir / "05_busy_dialog_cancelable.png"))
    busy3.finish()

    # 6) K 值说明对话框
    made.append(_grab(KHelpDialog(win), out_dir / "06_k_help.png"))

    # 7) K 标定向导（三个已测标定点 + 拟合曲线）
    wizard = KCalibWizardDialog(win, win_a=(24.5, 26.5), win_r=(26.5, 28.5))
    specs = [(50.0, 1.2205), (33.3, 2.4410), (75.0, 0.4068)]
    for idx, (wr, ratio_i) in enumerate(specs, start=1):
        wizard.add_row(f"D:/std/mix{idx}.xy", wr, ratio_i=ratio_i, ok=True)
    time.sleep(0.5)
    made.append(_grab(wizard, out_dir / "07_k_wizard.png"))
    wizard.close()

    win.close()
    for dlg in (busy, busy2, busy3):
        if isinstance(dlg, QDialog):
            dlg.close()
    return made


def main() -> int:
    """入口：解析输出目录并执行抓图。"""
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUT
    app = QApplication.instance() or QApplication([])
    paths = capture(out)
    app.processEvents()
    for p in paths:
        print(f"[evidence] {p}  {p.stat().st_size} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
