"""T1.1 谱读取器测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from rutana.core.patterns import clip, estimate_step, load_pattern

DATA_DIR = Path(__file__).parent / "data"


def test_load_fixture_basic() -> None:
    """读入两列 xy 正确（注释头被跳过）。"""
    p = load_pattern(DATA_DIR / "fixture_basic.xy")
    assert p.two_theta.size >= 100
    assert p.meta["source_format"] == "xy"
    assert estimate_step(p) == pytest.approx(0.05, abs=1e-9)
    assert bool((p.intensity > 0).any())


def test_load_csv_with_header(tmp_path: Path) -> None:
    """带表头的 csv（逗号分隔）正确解析。"""
    f = tmp_path / "s.csv"
    f.write_text("2Theta,Intensity\n10.0,100\n10.5,120\n11.0,115\n",
                 encoding="utf-8")
    p = load_pattern(f)
    assert p.two_theta.size == 3
    assert p.intensity[0] == pytest.approx(100.0)


def test_ragged_line_raises(tmp_path: Path) -> None:
    """数据区出现单列行（列数不匹配）必须报错。"""
    f = tmp_path / "bad.xy"
    f.write_text("10.0 100\n10.5\n", encoding="utf-8")
    with pytest.raises(ValueError):
        load_pattern(f)


def test_unknown_extension_raises() -> None:
    """未知扩展名抛 NotImplementedError。"""
    with pytest.raises(NotImplementedError):
        load_pattern(DATA_DIR / "no_such_file.uxd")


def test_clip_window(tmp_path: Path) -> None:
    """clip 后点数与区间一致（±1 点内），端点含在区间内。"""
    lines = [f"{10.0 + 0.02 * i:.4f} {i}" for i in range(501)]  # 10..20°
    f = tmp_path / "wide.xy"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    p = load_pattern(f)
    c = clip(p, 12.0, 14.0)
    assert c.two_theta[0] >= 12.0
    assert c.two_theta[-1] <= 14.0
    assert abs(c.two_theta.size - 101) <= 1


def test_clip_empty_raises(tmp_path: Path) -> None:
    """裁剪区间无数据点时报错。"""
    lines = ["10.0 1.0", "10.5 2.0"]
    f = tmp_path / "tiny.xy"
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")
    with pytest.raises(ValueError):
        clip(load_pattern(f), 30.0, 40.0)


def test_slash_comment_lines(tmp_path: Path) -> None:
    """// 开头的注释行同样被跳过。"""
    f = tmp_path / "c.xy"
    f.write_text("// instrument dump\n10.0 5\n10.5 6\n", encoding="utf-8")
    p = load_pattern(f)
    assert p.two_theta.size == 2
