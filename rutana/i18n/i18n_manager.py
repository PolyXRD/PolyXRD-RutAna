"""i18n 管理器。

提供三语（zh_CN / en_US / ja_JP）文案查询与语言切换：

- ``tr(key, **kw) -> str``            查询当前语言文案，缺失返回 ``⟪key⟫``（不回退，
                                       让漏译在界面上直接暴露，便于测试断言）。
- ``set_language(lang)``              运行时切换语言（未知代码忽略）。
- ``current_language() -> str``       当前语言代码。
- ``available_languages() -> dict``   语言代码 -> 原生语言名。
- ``load_language() / save_language`` 语言选择持久化到
                                       ``%USERPROFILE%/.rutana/config.json``。

界面文案全部收口于 ``rutana/i18n/translations/`` 下的三个模块，key 用点分。
"""

from __future__ import annotations

import json
from pathlib import Path

from rutana.i18n.translations import en_US, ja_JP, zh_CN

# --------------------------------------------------------------------------- #
# 语言表与常量
# --------------------------------------------------------------------------- #
TABLE: dict[str, dict[str, str]] = {
    "zh_CN": zh_CN.TRANSLATIONS,
    "en_US": en_US.TRANSLATIONS,
    "ja_JP": ja_JP.TRANSLATIONS,
}

#: 语言代码 -> 原生语言名（语言菜单显示用，任何界面语言下保持原生写法）
LANGUAGE_NAMES: dict[str, str] = {
    "zh_CN": "简体中文",
    "en_US": "English",
    "ja_JP": "日本語",
}

DEFAULT_LANGUAGE = "zh_CN"

#: 语言配置持久化路径（测试可通过 monkeypatch 替换）
CONFIG_PATH: Path = Path.home() / ".rutana" / "config.json"

# 当前语言（模块级状态）
_current: str = DEFAULT_LANGUAGE


def available_languages() -> dict[str, str]:
    """返回 {语言代码: 原生语言名}。"""
    return dict(LANGUAGE_NAMES)


def current_language() -> str:
    """返回当前语言代码。"""
    return _current


def set_language(lang: str) -> None:
    """切换当前语言；未知代码忽略。"""
    global _current
    if lang in TABLE:
        _current = lang


def tr(key: str, **kw) -> str:
    """查询当前语言文案；缺失键返回 ``⟪key⟫`` 标记（不做语言回退）。"""
    text = TABLE.get(_current, {}).get(key)
    if text is None:
        return f"⟪{key}⟫"
    return text.format(**kw) if kw else text


# --------------------------------------------------------------------------- #
# 语言选择持久化（%USERPROFILE%/.rutana/config.json）
# --------------------------------------------------------------------------- #
def load_language() -> str:
    """从配置文件读取上次选择的语言并设为当前语言；文件缺失/非法用默认值。"""
    global _current
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
        lang = str(data.get("language", ""))
    except (OSError, ValueError):
        lang = ""
    if lang in TABLE:
        _current = lang
    return _current


def save_language(lang: str | None = None) -> None:
    """把语言选择写入配置文件；lang 缺省时保存当前语言。"""
    global _current
    target = lang if lang is not None else _current
    if target not in TABLE:
        return
    _current = target
    try:
        CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
        CONFIG_PATH.write_text(
            json.dumps({"language": target}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError:
        # 配置写入失败不应阻断界面运行（如只读环境）
        pass
