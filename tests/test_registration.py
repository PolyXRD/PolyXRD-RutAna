"""v1.5.0 注册机制核心测试（无需 Qt）+ 跨仓库一致性。

覆盖内容：

- 注册码往返：generate_code → verify_code 还原「单位部门名称」；
- 输入容错：带/不带 PXRD1- 前缀、全角连字符、大小写、空白；
- 防伪：篡改 payload、换单位、非法输入一律 None；
- 注册状态：save_state/load_state 往返，手改 JSON 伪造「已注册」无效；
- 跨仓库一致性：与 PolyXRD-Reg 源头的 registration.py 密钥/出码逐字节
  一致（家族注册机 PolyXRD-RegTool.exe 互通的根基）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from rutana.gui import registration

UNIT = "清华大学材料学院"

#: PolyXRD-Reg 源头仓库（家族注册机制 + 出码工具）
REG_REPO = Path(r"D:/Project/XRD/PolyXRD-Reg")


# --------------------------------------------------------------------------- #
# 注册码：生成 / 校验 / 容错 / 防伪
# --------------------------------------------------------------------------- #
def test_roundtrip_generate_and_verify():
    """生成 → 校验应还原出完全相同的单位部门名称。"""
    code = registration.generate_code(UNIT)
    assert code.startswith("PXRD1-")
    assert registration.verify_code(code) == UNIT


def test_verify_tolerates_prefix_dashes_case_whitespace():
    """输入容错：不带前缀 / 全角连字符 / 小写 / 任意空白均可通过。"""
    code = registration.generate_code(UNIT)
    body = code[len("PXRD1-"):]
    assert registration.verify_code(code) == UNIT
    assert registration.verify_code(body) == UNIT, "不带前缀也应通过"
    assert registration.verify_code(code.replace("-", "－")) == UNIT, "全角连字符"
    assert registration.verify_code(code.lower()) == UNIT, "大小写混输"
    spaced = "  ".join(code) + "\n"
    assert registration.verify_code(spaced) == UNIT, "任意空白插入"


def test_verify_rejects_tampered_and_bad_input():
    """篡改 payload / 换单位 / 非法输入一律 None（不抛异常）。"""
    code = registration.generate_code(UNIT)
    body = code[len("PXRD1-"):]
    assert registration.verify_code("PXRD1-" + body[:-2] + "AA") is None, "篡改尾部"
    assert registration.verify_code(body[1:]) is None, "截断 Base32"
    other = registration.generate_code("另一家单位")
    assert registration.verify_code(other) == "另一家单位", "他单位自己的码有效"
    swapped = code[:-4] + other[-4:]
    assert registration.verify_code(swapped) is None, "拼凑两码必须失败"
    for bad in ("", "   ", "PXRD1-", "####", "不是注册码"):
        assert registration.verify_code(bad) is None, repr(bad)


def test_generate_rejects_invalid_unit():
    """空名 / 超长 / 含控制字符的单位名生成时抛 ValueError。"""
    with pytest.raises(ValueError):
        registration.generate_code("")
    with pytest.raises(ValueError):
        registration.generate_code("x" * 101)
    with pytest.raises(ValueError):
        registration.generate_code("单位\x00名")


# --------------------------------------------------------------------------- #
# 注册状态：存取 / 防手改
# --------------------------------------------------------------------------- #
def test_state_roundtrip(tmp_path):
    """save_state → load_state 往返一致（registered/unit/code 全保留）。"""
    code = registration.generate_code(UNIT)
    state_path = tmp_path / "reg" / "PolyXRD_RutAna.json"
    saved = registration.save_state(state_path, code)
    assert saved.registered and saved.unit == UNIT
    loaded = registration.load_state(state_path)
    assert loaded.registered and loaded.unit == UNIT and loaded.code == code


def test_state_tampered_json_is_invalid(tmp_path):
    """手改 JSON 的 unit/code 重新过校验，伪造「已注册」无效。"""
    code = registration.generate_code(UNIT)
    state_path = tmp_path / "state.json"
    registration.save_state(state_path, code)

    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["unit"] = "冒名顶替单位"
    state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert registration.load_state(state_path).registered is False

    data = json.loads(state_path.read_text(encoding="utf-8"))
    data["code"] = "PXRD1-FAKE-FAKE-FAKE"
    state_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    assert registration.load_state(state_path).registered is False


def test_state_missing_or_broken_file(tmp_path):
    """缺失/损坏/空 code 的状态文件一律按未注册处理，不抛异常。"""
    assert registration.load_state(tmp_path / "nope.json").registered is False
    broken = tmp_path / "broken.json"
    broken.write_text("{not json", encoding="utf-8")
    assert registration.load_state(broken).registered is False
    empty = tmp_path / "empty.json"
    empty.write_text("{}", encoding="utf-8")
    assert registration.load_state(empty).registered is False


def test_save_state_rejects_invalid_code(tmp_path):
    """无效注册码保存时抛 ValueError，且不落盘。"""
    state_path = tmp_path / "state.json"
    with pytest.raises(ValueError):
        registration.save_state(state_path, "PXRD1-FAKE")
    assert not state_path.exists()


def test_default_state_path_shape(monkeypatch):
    """default_state_path 落在 %APPDATA%/PolyXRD/Registration/ 且 app_id 安全化。"""
    monkeypatch.setenv("APPDATA", str(Path(r"C:/Users/x/AppData/Roaming")))
    path = registration.default_state_path("PolyXRD-RutAna")
    assert path.parts[-3:] == ("PolyXRD", "Registration", "PolyXRD_RutAna.json")


# --------------------------------------------------------------------------- #
# 跨仓库一致性（家族注册机互通的根基）
# --------------------------------------------------------------------------- #
def test_cross_repo_registration_identity():
    """与 PolyXRD-Reg 源头的密钥与出码必须逐字节一致。"""
    if not REG_REPO.is_dir():
        pytest.skip(f"PolyXRD-Reg 仓库不存在：{REG_REPO}")
    assert str(REG_REPO) not in sys.path
    sys.path.insert(0, str(REG_REPO))
    try:
        import importlib

        origin = importlib.import_module("registration")
    finally:
        sys.path.remove(str(REG_REPO))
        sys.modules.pop("registration", None)

    assert registration._SECRET_KEY == origin._SECRET_KEY, "密钥必须一致"
    assert registration.CODE_PREFIX == origin.CODE_PREFIX
    for unit in (UNIT, "中国科学院物理研究所", "Acme Labs R&D"):
        assert registration.generate_code(unit) == origin.generate_code(unit), unit
        assert registration.verify_code(origin.generate_code(unit)) == unit, unit
