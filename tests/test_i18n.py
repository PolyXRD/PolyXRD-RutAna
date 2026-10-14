"""i18n 三语文案与持久化测试。"""

from __future__ import annotations

import json

import rutana.i18n.i18n_manager as m
from rutana.i18n import (
    available_languages,
    current_language,
    set_language,
    tr,
)
from rutana.i18n.translations import en_US, ja_JP, zh_CN

LANGS = ("zh_CN", "en_US", "ja_JP")
TABLES = {
    "zh_CN": zh_CN.TRANSLATIONS,
    "en_US": en_US.TRANSLATIONS,
    "ja_JP": ja_JP.TRANSLATIONS,
}


def test_key_sets_identical():
    """三语键集合必须完全一致（漏译/多译都会在此暴露）。"""
    base = set(TABLES["zh_CN"])
    assert base, "zh_CN 键集不能为空"
    for lang in LANGS[1:]:
        extra = set(TABLES[lang]) - base
        missing = base - set(TABLES[lang])
        assert not extra, f"{lang} 多出的键: {sorted(extra)}"
        assert not missing, f"{lang} 缺失的键: {sorted(missing)}"


def test_values_nonempty():
    """所有键的值必须是非空字符串。"""
    for lang, table in TABLES.items():
        for key, value in table.items():
            assert isinstance(value, str) and value.strip(), f"{lang}.{key} 为空"


def test_tr_basic():
    """tr 按当前语言取值。"""
    set_language("zh_CN")
    assert tr("menu.help.about") == TABLES["zh_CN"]["menu.help.about"]
    set_language("ja_JP")
    assert tr("menu.help.about") == TABLES["ja_JP"]["menu.help.about"]
    set_language("en_US")
    assert tr("menu.help.about") == TABLES["en_US"]["menu.help.about"]
    set_language("zh_CN")


def test_tr_missing_key():
    """缺失键返回 ⟪key⟫ 标记（不回退，暴露漏译）。"""
    set_language("zh_CN")
    assert tr("no.such.key") == "⟪no.such.key⟫"


def test_tr_format_kwargs():
    """带占位符的文案支持 kwargs 格式化。"""
    set_language("en_US")
    assert "Boom" in tr("msg.load_fail", detail="Boom")
    set_language("zh_CN")
    assert "Boom" in tr("msg.load_fail", detail="Boom")


def test_set_language_ignores_unknown():
    """未知语言代码被忽略。"""
    set_language("zh_CN")
    set_language("xx_XX")
    assert current_language() == "zh_CN"


def test_available_languages():
    """语言表包含三语且名称为原生写法。"""
    langs = available_languages()
    assert set(langs) == set(LANGS)
    assert langs["zh_CN"] == "简体中文"
    assert langs["en_US"] == "English"
    assert langs["ja_JP"] == "日本語"


def test_persistence_roundtrip(tmp_path, monkeypatch):
    """save_language → （模拟重启）→ load_language 往返一致。"""
    cfg = tmp_path / "config.json"
    monkeypatch.setattr(m, "CONFIG_PATH", cfg)

    set_language("ja_JP")
    m.save_language()
    assert cfg.exists()
    assert json.loads(cfg.read_text(encoding="utf-8"))["language"] == "ja_JP"

    # 模拟重启：把当前语言复位为默认后再读回
    m.set_language(m.DEFAULT_LANGUAGE)
    assert m.load_language() == "ja_JP"

    # 非法语言回退默认值
    cfg.write_text(json.dumps({"language": "xx_XX"}), encoding="utf-8")
    m.set_language(m.DEFAULT_LANGUAGE)
    assert m.load_language() == m.DEFAULT_LANGUAGE
    set_language("zh_CN")


def test_load_language_missing_file(tmp_path, monkeypatch):
    """配置文件缺失时 load_language 返回默认语言且不报错。"""
    monkeypatch.setattr(m, "CONFIG_PATH", tmp_path / "nonexistent" / "config.json")
    m.set_language(m.DEFAULT_LANGUAGE)
    assert m.load_language() == m.DEFAULT_LANGUAGE
