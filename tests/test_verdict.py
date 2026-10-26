"""v1.6.2：B 法 Rwp 四档判定（口径唯一出处 :mod:`rutana.gui.verdict`）。

覆盖三件事：
1. 四档区间与边界归并（10.0 归二档、15.0/20.0 归三档、>20.0 归四档）；
2. 结果卡配色等级映射（很好=green、良好=blue/info、尚可=warn、不佳=bad）；
3. B 法面板 ``set_rfactors`` 走真实代码路径时文本与配色一致，且三语文案齐备。
"""

from __future__ import annotations

import pytest

from rutana.gui.verdict import (
    RWP_FAIR_LIMIT,
    RWP_GOOD_LIMIT,
    RWP_VERY_GOOD_LIMIT,
    rwp_verdict,
)
from rutana.i18n import set_language, tr
from rutana.i18n.translations import en_US, ja_JP, zh_CN

LANGS = ("zh_CN", "en_US", "ja_JP")
TABLES = {"zh_CN": zh_CN.TRANSLATIONS,
          "en_US": en_US.TRANSLATIONS,
          "ja_JP": ja_JP.TRANSLATIONS}

#: 四档 i18n 键（顺序即档位由好到差）
VERDICT_KEYS = ("verdict.fit_very_good", "verdict.fit_good",
                "verdict.fit_fair", "verdict.fit_bad")


def test_thresholds_are_10_15_20():
    """阈值固定为 10 / 15 / 20（%）——需求口径，改动必须同步文档与测试。"""
    assert (RWP_VERY_GOOD_LIMIT, RWP_GOOD_LIMIT, RWP_FAIR_LIMIT) == (10.0, 15.0, 20.0)


@pytest.mark.parametrize("rwp, key, level", [
    (0.0, "verdict.fit_very_good", "good"),
    (2.13, "verdict.fit_very_good", "good"),
    (9.99, "verdict.fit_very_good", "good"),
    (10.0, "verdict.fit_good", "info"),        # 边界：10.0 归二档（一档要求 <10）
    (12.5, "verdict.fit_good", "info"),
    (14.99, "verdict.fit_good", "info"),
    (15.0, "verdict.fit_fair", "warn"),        # 边界：15.0 归三档
    (18.0, "verdict.fit_fair", "warn"),
    (20.0, "verdict.fit_fair", "warn"),        # 边界：20.0 归三档（四档要求 >20）
    (20.01, "verdict.fit_bad", "bad"),
    (25.5, "verdict.fit_bad", "bad"),
    (99.0, "verdict.fit_bad", "bad"),
])
def test_four_tiers(rwp, key, level):
    """四档判定与配色等级按 Rwp 区间落位。"""
    assert rwp_verdict(rwp) == (key, level)


def test_levels_exist_in_resultcard_palette():
    """判定返回的配色等级必须都在结果卡调色板里（防拼写漂移成默认色）。"""
    from rutana.gui.resultcard import COLOR_INFO, LEVEL_COLORS

    for level in {lvl for _k, lvl in map(rwp_verdict, (5.0, 12.0, 18.0, 30.0))}:
        assert level in LEVEL_COLORS, f"结果卡缺少配色等级: {level}"
    assert LEVEL_COLORS["info"] == COLOR_INFO == "#0284C7"
    # 四档四色互不相同（一眼可辨）
    colors = [LEVEL_COLORS[lvl] for lvl in ("good", "info", "warn", "bad")]
    assert len(set(colors)) == 4, colors


def test_verdict_texts_defined_in_three_languages():
    """四档文案在三语中均存在且非空，且与阈值区间自洽（不含旧的 ≤10% 口径）。"""
    for key in VERDICT_KEYS:
        for lang in LANGS:
            text = TABLES[lang].get(key)
            assert text, f"{lang} 缺文案: {key}"
    assert "Rwp ≤ 10%" not in TABLES["zh_CN"]["verdict.fit_good"], "旧二档文案未替换"
    assert "20" in TABLES["zh_CN"]["verdict.fit_bad"], "四档文案应写明 >20% 口径"


@pytest.fixture(scope="module")
def qapp():
    """模块级 QApplication（本模块只构造面板，不建主窗口）。"""
    QtWidgets = pytest.importorskip("PySide6.QtWidgets")
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app


@pytest.mark.parametrize("rwp, key, color", [
    (8.42, "verdict.fit_very_good", "#16A34A"),
    (12.0, "verdict.fit_good", "#0284C7"),
    (18.0, "verdict.fit_fair", "#CA8A04"),
    (25.5, "verdict.fit_bad", "#DC2626"),
])
def test_b_panel_applies_tier_text_and_color(qapp, rwp, key, color):
    """B 法面板回填：判定文本与配色随档位变化（真实 set_rfactors 路径）。"""
    from rutana.gui.panels_b import BPanel

    set_language("zh_CN")
    panel = BPanel()
    try:
        panel.set_rfactors(rwp, 7.1, 1.2)
        assert panel.card_b.value("result.fit_verdict") == tr(key)
        style = panel.card_b.rows["result.fit_verdict"][1].styleSheet()
        assert color in style.upper(), f"{rwp}% 应为 {color}: {style}"
        # Rwp 数值行与判定行同色
        rwp_style = panel.card_b.rows["result.rwp"][1].styleSheet()
        assert color in rwp_style.upper(), rwp_style
    finally:
        panel.deleteLater()
