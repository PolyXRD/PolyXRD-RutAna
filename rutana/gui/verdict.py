"""B 法 Rwp 判定口径（v1.6.2）：阈值与档位的**唯一出处**。

判定按四档给结论（区间取「下限含、上限含于最后一档」）：

====== ==================== ========================== ==================
档位   判定（中/EN/JP）      Rwp 区间                    结果卡配色等级
====== ==================== ========================== ==================
一档   拟合很好              Rwp < 10%                  ``good``（绿）
二档   拟合良好              10% ≤ Rwp < 15%            ``info``（蓝）
三档   拟合尚可              15% ≤ Rwp ≤ 20%            ``warn``（琥珀）
四档   拟合不佳              Rwp > 20%                  ``bad``（红）
====== ==================== ========================== ==================

边界说明：恰好 10.0% 归二档（一档要求严格小于）；15.0% 与 20.0% 归三档
（三档上界取闭区间，四档要求严格大于 20%）。

v1.6.0 及以前只有两档（Rwp ≤ 10% 判「拟合良好」，否则「拟合不佳」），
v1.6.2 起按用户口径细分为四档；本模块不 import PySide6，可在无界面环境下单测。
"""

from __future__ import annotations

#: 一档上界：Rwp < 此值判「拟合很好」（%）
RWP_VERY_GOOD_LIMIT = 10.0
#: 二档上界：Rwp < 此值（且 ≥ 一档上界）判「拟合良好」（%）
RWP_GOOD_LIMIT = 15.0
#: 三档上界：Rwp ≤ 此值判「拟合尚可」，超过判「拟合不佳」（%）
RWP_FAIR_LIMIT = 20.0


def rwp_verdict(rwp: float) -> tuple[str, str]:
    """Rwp(%) → ``(i18n 键, 结果卡配色等级)``。

    配色等级取值见 :data:`rutana.gui.resultcard.LEVEL_COLORS`
    （``good`` / ``info`` / ``warn`` / ``bad``）。
    """
    value = float(rwp)
    if value < RWP_VERY_GOOD_LIMIT:
        return "verdict.fit_very_good", "good"
    if value < RWP_GOOD_LIMIT:
        return "verdict.fit_good", "info"
    if value <= RWP_FAIR_LIMIT:
        return "verdict.fit_fair", "warn"
    return "verdict.fit_bad", "bad"
