"""B 法精修结构摘要（v1.7.1）的测试：core 汇总口径 + 界面展示。

三层：
1. :func:`rutana.core.phasepeak.cell_volume` 的解析值（正交 / 四方 / 六方）；
2. :func:`rutana.core.phasepeak.refined_summary` 的映射口径——晶胞缩放、
   体积重算、最强峰位、Caglioti 宽度、谢乐晶粒、择优取向与降级行为；
3. 界面：面板紧凑区（每相两行 + 「更多信息…」）与详情窗口的分区表。
"""

from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

from rutana.core.phasepeak import (
    DEFAULT_WAVELENGTH,
    caglioti_2theta,
    cell_volume,
    refined_summary,
    scherrer_size_nm,
)
from rutana.core.profile.cif import CifStructure, parse_cif

DATA = Path(__file__).resolve().parent.parent / "rutana" / "data"


@pytest.fixture(scope="module")
def phases():
    """内置两相（锐钛矿 / 金红石）。"""
    return [parse_cif(str(DATA / "anatase.cif")),
            parse_cif(str(DATA / "rutile.cif"))]


def _result(*, zero: float = 0.03, u: float = 0.0337, v: float = -0.0403,
            w: float = 0.0307, cell_scales=None, scales=(0.0040, 0.0038),
            po: dict | None = None, dropped=()) -> SimpleNamespace:
    """构造一个与 ``RefineResult`` 同形的假结果（只含摘要用到的字段）。"""
    prm = SimpleNamespace(zero=zero, U=u, V=v, W=w, eta=0.669, asym=0.0505,
                          bfactor=0.308, wavelength=DEFAULT_WAVELENGTH)
    return SimpleNamespace(
        params=prm,
        cell_scales=cell_scales or [(1.0, 1.0), (1.0, 1.0)],
        scales=np.asarray(scales, dtype=float),
        po_r=(po if po is not None
              else {"anatase": (1, 0, 1, 1.0054), "rutile": (1, 1, 0, 1.0167)}),
        rf=SimpleNamespace(rwp=9.29, rp=6.47, chi2=1.526),
        iters=113, restarted=False, phase_dropped=dropped)


# --------------------------------------------------------------------------- #
# 1. 晶胞体积
# --------------------------------------------------------------------------- #
def test_cell_volume_orthogonal():
    """直角晶胞：V = a·b·c。"""
    assert cell_volume(3.0, 4.0, 5.0, 90.0, 90.0, 90.0) == pytest.approx(60.0)


def test_cell_volume_tetragonal_matches_builtin():
    """锐钛矿（四方）V = a²c，与 CifStructure.volume 同值。"""
    st = parse_cif(str(DATA / "anatase.cif"))
    a, _b, c = st.cell[0], st.cell[1], st.cell[2]
    assert cell_volume(*st.cell) == pytest.approx(st.volume, rel=1e-12)
    assert cell_volume(*st.cell) == pytest.approx(a * a * c, rel=1e-9)


def test_cell_volume_hexagonal():
    """六方晶胞：V = a²c·√3/2。"""
    assert cell_volume(3.2, 3.2, 5.2, 90.0, 90.0, 120.0) == pytest.approx(
        3.2 ** 2 * 5.2 * 0.86602540378, rel=1e-9)


def test_cell_volume_degenerate_is_not_nan():
    """退化角度（内层为负）返回 0 而不是 nan（界面不会显示 nan）。"""
    val = cell_volume(3.0, 3.0, 3.0, 10.0, 10.0, 170.0)
    assert val >= 0.0 and not np.isnan(val)


# --------------------------------------------------------------------------- #
# 2. 精修摘要映射
# --------------------------------------------------------------------------- #
def test_refined_summary_maps_fields(phases):
    """逐字段核对：晶胞原样、体积重算、最强峰 + 零点、Caglioti 宽度、谢乐晶粒。"""
    res = _result()
    s = refined_summary(phases, res)

    assert s.wavelength == pytest.approx(DEFAULT_WAVELENGTH, rel=1e-6)
    assert s.zero == pytest.approx(0.03)
    assert (s.u, s.v, s.w) == pytest.approx((0.0337, -0.0403, 0.0307))
    assert s.eta == pytest.approx(0.669)
    assert s.bfactor == pytest.approx(0.308)
    assert (s.rwp, s.rp, s.chi2) == pytest.approx((9.29, 6.47, 1.526))
    assert s.iters == 113 and s.restarted is False and s.dropped == ()
    assert [p.name for p in s.phases] == ["anatase", "rutile"]

    ana = s.phases[0]
    st = phases[0]
    assert ana.a == pytest.approx(st.cell[0]) and ana.b == pytest.approx(ana.a)
    assert ana.c == pytest.approx(st.cell[2])
    assert ana.volume == pytest.approx(st.volume, rel=1e-9)
    # 最强峰 = CIF 最强反射 + 精修零点；宽度由 Caglioti 在峰位处求值
    assert ana.two_theta == pytest.approx(25.34 + 0.03, abs=0.05)
    fwhm = caglioti_2theta(s.u, s.v, max(s.w, 1e-4))(ana.two_theta)
    assert ana.fwhm == pytest.approx(fwhm, rel=1e-9)
    assert ana.size_nm == pytest.approx(
        scherrer_size_nm(ana.fwhm, ana.two_theta, s.wavelength), rel=1e-9)
    # 择优取向与标度
    assert ana.po_r == pytest.approx(1.0054)
    assert ana.scale == pytest.approx(0.0040)
    assert s.phases[1].po_r == pytest.approx(1.0167)


def test_refined_summary_applies_cell_scales(phases):
    """cell_scales 的 (fa, fc)：a/b 随 fa、c 随 fc 缩放，体积与峰位同步变化。"""
    base = refined_summary(phases, _result())
    scaled = refined_summary(phases, _result(cell_scales=[(1.01, 1.02), (1.0, 1.0)]))

    a0, a1 = base.phases[0], scaled.phases[0]
    assert a1.a == pytest.approx(a0.a * 1.01)
    assert a1.b == pytest.approx(a0.b * 1.01)
    assert a1.c == pytest.approx(a0.c * 1.02)
    assert a1.volume == pytest.approx(a0.volume * 1.01 ** 2 * 1.02, rel=1e-9)
    assert a1.two_theta < a0.two_theta          # 晶胞变大 -> 峰位左移
    # 未缩放的相不受影响
    assert scaled.phases[1].volume == pytest.approx(base.phases[1].volume)


def test_refined_summary_degrades_phase_without_reflections(phases):
    """空原子列表的相：峰位/晶粒降级为 nan/None，晶胞与体积照常给出。"""
    broken = CifStructure("extra", (5.0, 5.0, 5.0, 90.0, 90.0, 90.0), [])
    s = refined_summary([phases[0], broken], _result(
        cell_scales=[(1.0, 1.0), (1.0, 1.0)], scales=(0.004, 0.001),
        po={"anatase": (1, 0, 1, 1.0054)}))
    bad = s.phases[1]
    assert bad.volume == pytest.approx(125.0)
    assert np.isnan(bad.two_theta) and np.isnan(bad.fwhm)
    assert bad.size_nm is None
    assert bad.po_r is None            # 未精修择优取向的相
    assert s.phases[0].size_nm is not None


def test_refined_summary_requires_params(phases):
    """缺少峰形参数的精修结果直接报错（上层会降级为「无摘要」）。"""
    with pytest.raises(ValueError):
        refined_summary(phases, SimpleNamespace())


def test_refined_summary_reports_flags(phases):
    """迭代次数外的诊断字段（重启 / 丢相）原样带出。"""
    res = _result(dropped=(0, 2))
    res.restarted = True
    s = refined_summary(phases, res)
    assert s.dropped == (0, 2)
    assert s.restarted is True


# --------------------------------------------------------------------------- #
# 3. 界面（离屏）
# --------------------------------------------------------------------------- #
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6", reason="PySide6 不可用，跳过界面测试")

from PySide6.QtWidgets import QApplication, QDialog  # noqa: E402

from rutana.gui.panels_b import BPanel  # noqa: E402
from rutana.gui.refine_view import (  # noqa: E402
    RefineDetailDialog,
    RefineSummaryBox,
    cell_text,
    vol_size_text,
)
from rutana.i18n import set_language  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def zh():
    """每个界面测试在简体中文下跑，结束后恢复（避免污染其它用例）。"""
    set_language("zh_CN")
    yield
    set_language("zh_CN")


@pytest.fixture()
def no_modal(monkeypatch):
    """屏蔽模态循环（面板的「更多信息」走 exec）。"""
    monkeypatch.setattr(QDialog, "exec", lambda _self, *a, **k: int(QDialog.Accepted))


def test_summary_box_empty_state(qapp, zh):
    """空态：无行、无相、按钮禁用、提示可见。"""
    box = RefineSummaryBox()
    assert box.phase_count() == 0
    assert box.value_texts() == []
    assert box.btn_more.isEnabled() is False
    assert box.lbl_empty.isVisible() is False   # 未 show() 前 isVisible 恒 False
    assert box.open_more() is None


def test_summary_box_rows_and_text(qapp, zh, phases):
    """有结果：每相一行，文本含晶胞、体积与晶粒；按钮可用、摘要可取回。"""
    box = RefineSummaryBox()
    s = refined_summary(phases, _result())
    box.set_summary(s)
    assert box.phase_count() == 2
    assert box.summary() is s
    assert box.btn_more.isEnabled() is True

    texts = box.value_texts()
    ana = s.phases[0]
    assert texts[0] == f"{cell_text(ana)}\n{vol_size_text(ana)}"
    assert "a = b = " in texts[0] and "Å" in texts[0]
    assert "V = " in texts[0] and "D = " in texts[0]
    # 四方相不重复抄第二根等长轴
    assert texts[0].count(f"{ana.a:.4f}") == 1

    box.clear()
    assert box.phase_count() == 0 and box.summary() is None


def test_summary_box_retranslate(qapp, zh, phases):
    """语言热切换：标题/按钮/行文本切到英文，数值不变、相数不变。"""
    box = RefineSummaryBox()
    box.set_summary(refined_summary(phases, _result()))
    set_language("en_US")
    box.retranslate()
    assert box.btn_more.text() == "More…"
    assert box.title() == "Refined structure"
    assert box.phase_count() == 2
    assert "V = " in box.value_texts()[0]
    set_language("zh_CN")


def test_summary_box_open_more(qapp, zh, phases, no_modal):
    """「更多信息」按钮弹出详情窗口并返回它（空态返回 None 已在上面覆盖）。"""
    box = RefineSummaryBox()
    box.set_summary(refined_summary(phases, _result()))
    dlg = box.open_more()
    assert isinstance(dlg, RefineDetailDialog)
    assert dlg.tbl_cell.rowCount() == 2


def test_detail_dialog_sections(qapp, zh, phases):
    """详情窗口：两张每相表 + 全局统计（丢相为空显示「—」）。"""
    s = refined_summary(phases, _result())
    dlg = RefineDetailDialog(s)
    assert dlg.tbl_cell.rowCount() == 2 and dlg.tbl_cell.columnCount() == 8
    assert dlg.tbl_shape.rowCount() == 2 and dlg.tbl_shape.columnCount() == 6
    # 晶胞表首行：物相名 + a/b/c/α/β/γ/V
    assert dlg.tbl_cell.item(0, 0).text() == "锐钛矿"
    assert dlg.tbl_cell.item(0, 1).text() == f"{s.phases[0].a:.4f}"
    assert dlg.tbl_cell.item(0, 7).text() == f"{s.phases[0].volume:.2f}"
    # 全局统计
    vals = dlg.global_values()
    assert len(vals) == 11
    assert "113" in vals.values()          # 迭代次数
    assert "否" in vals.values()            # 梯度重启
    assert "—" in vals.values()             # 无丢相
    assert "Rwp" not in vals                # Rwp 在标题行，不重复占格

    dropped = RefineDetailDialog(refined_summary(phases, _result(dropped=(0, 2))))
    assert "1, 3" in dropped.global_values().values()   # 序号 1 起


def test_bpanel_carries_summary(qapp, zh, phases):
    """B 法面板：set_summary 进紧凑区，clear_rfactors 一起复位。"""
    panel = BPanel()
    s = refined_summary(phases, _result())
    panel.set_summary(s)
    assert panel.summary_box.phase_count() == 2
    panel.clear_rfactors()
    assert panel.summary_box.phase_count() == 0
    assert panel.summary_box.btn_more.isEnabled() is False
