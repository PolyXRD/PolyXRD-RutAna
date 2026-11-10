"""i18n 三语文案与持久化测试。"""

from __future__ import annotations

import json
import re
from pathlib import Path

import rutana.i18n.i18n_manager as m
from rutana.i18n import (
    available_languages,
    current_language,
    set_language,
    tr,
)
from rutana.i18n.translations import en_US, ja_JP, zh_CN
from rutana.version import __version__

LANGS = ("zh_CN", "en_US", "ja_JP")
TABLES = {
    "zh_CN": zh_CN.TRANSLATIONS,
    "en_US": en_US.TRANSLATIONS,
    "ja_JP": ja_JP.TRANSLATIONS,
}

#: v1.0.0 起的最低键数基线（进度窗 / K 说明 / K 标定向导 / 结果卡增强）
MIN_KEY_COUNT = 183

#: v1.0.0 必须存在的关键键（漏一个就意味着新功能文案没收口）
V1_REQUIRED_KEYS = (
    # 忙对话框
    "busy.title", "busy.title_refine", "busy.elapsed", "busy.degraded",
    "busy.load", "busy.measure", "busy.ratio", "busy.refine", "busy.report",
    "busy.cancel", "busy.canceling", "msg.busy_canceled", "status.computing",
    # K 值说明
    "khelp.title", "khelp.formula_k", "khelp.formula_wa", "khelp.typical",
    "khelp.open_doc", "khelp.doc_missing",
    # K 标定向导
    "kwizard.title", "kwizard.measure", "kwizard.fit.ols", "kwizard.fit.origin",
    "kwizard.result", "kwizard.warn_r2", "kwizard.adopt", "kwizard.saved",
    "kwizard.load_fail", "kwizard.adopted", "kwizard.min_points",
    # 面板入口与结果卡增强
    "a.k_help", "a.k_wizard", "a.k.source_manual", "a.k.source_calib",
    "a.ref_enable", "result.ia_ir", "result.r2", "result.ref_label",
    "result.ref_err", "result.fit_verdict",
    "verdict.fit_very_good", "verdict.fit_good", "verdict.fit_fair",
    "verdict.fit_bad",
)


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


def test_v1_keys_present_in_all_languages():
    """v1.0.0 新增功能的键必须在三语中齐备（漏译立即暴露）。"""
    for lang in LANGS:
        missing = [k for k in V1_REQUIRED_KEYS if k not in TABLES[lang]]
        assert not missing, f"{lang} 缺失 v1.0.0 键: {missing}"


def test_key_count_meets_minimum():
    """键总数不低于 v1.0.0 基线（防止后续误删整段文案）。"""
    for lang in LANGS:
        assert len(TABLES[lang]) >= MIN_KEY_COUNT, f"{lang} 键数低于基线"


def test_placeholders_consistent():
    """同一 key 的三语占位符必须一致（否则 tr(..., ) 会 KeyError）。"""
    pat = re.compile(r"\{(\w+)(?:[:}])")
    for key in sorted(set(TABLES["zh_CN"])):
        names = {lang: tuple(sorted(pat.findall(TABLES[lang][key])))
                 for lang in LANGS}
        assert names["zh_CN"] == names["en_US"] == names["ja_JP"], (
            f"{key} 占位符在三语中不一致: {names}")


def test_version_is_170():
    """版本号与 rutana/version.py 同源推进（UI/EXE/安装包统一取这里）。"""
    assert __version__ == "1.7.0"


def test_all_code_keys_defined_in_all_languages():
    """源码里出现的每个 tr("key") 都必须在三语表中（防漏译/拼错）。

    例外：rutana/gui/registration.py 为家族注册模块逐字节原样复用；
    rutana/core/vendor/text_formats.py 为 Converter 读谱器副本并自带局部中文错误
    格式化器。两者的 ``tr()`` 均不走 rutana.i18n，扫描时跳过。
    """
    pat = re.compile(r'tr\(\s*"([A-Za-z0-9_.]+)"')
    root = Path(__file__).resolve().parent.parent / "rutana"
    missing: dict[str, list[str]] = {}
    for path in sorted(root.rglob("*.py")):
        if path.name == "registration.py" or path.as_posix().endswith(
                "core/vendor/text_formats.py"):
            continue
        text = path.read_text(encoding="utf-8")
        for key in sorted(set(pat.findall(text))):
            for lang, table in TABLES.items():
                if key not in table:
                    missing.setdefault(str(path.relative_to(root.parent)), []).append(
                        f"{key}@{lang}")
    assert not missing, f"以下文案键未定义: {missing}"


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
