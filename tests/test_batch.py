"""v1.2.0 批量计算测试（A 法 / B 法 / 落盘命名 / CSV / PNG）。

批量服务层 :mod:`rutana.gui.batch` 不依赖 PySide6，因此本文件**不需要**
offscreen Qt 平台即可直接单测；真实数据那条（B 法批量）按用户要求真跑
两个 pd 实测谱，验证 wr 回收与 PNG 落盘。
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from rutana.gui import batch, services  # noqa: E402
from rutana.i18n import set_language, tr  # noqa: E402

REAL = ROOT / "tests" / "data" / "real"


def _row(path: str, **extra) -> dict:
    """构造一条批量结果行。"""
    row = {"path": path, "sample": Path(path).stem, "ok": True, "message": ""}
    row.update(extra)
    return row


# --------------------------------------------------------------------------- #
# 需求 E：CSV 分组命名规则
# --------------------------------------------------------------------------- #
def test_batch_save_plan_single_file(tmp_path):
    """同文件夹只有 1 个文件 -> CSV 名为 <数据文件去扩展名>.csv。"""
    d = tmp_path / "批样1"
    d.mkdir()
    plan = batch.batch_save_plan([_row(str(d / "sample01.xy"))])
    assert len(plan) == 1
    dest, group = plan[0]
    assert dest == d / "sample01.csv"
    assert len(group) == 1


def test_batch_save_plan_multi_files_same_folder(tmp_path):
    """同文件夹 ≥2 个文件 -> 合并成一个 <文件夹名>.csv。"""
    d = tmp_path / "批样2"
    d.mkdir()
    rows = [_row(str(d / "a.xy")), _row(str(d / "b.xy")), _row(str(d / "c.xy"))]
    plan = batch.batch_save_plan(rows)
    assert len(plan) == 1
    dest, group = plan[0]
    assert dest == d / "批样2.csv"
    assert len(group) == 3


def test_batch_save_plan_multiple_folders(tmp_path):
    """多个不同文件夹 -> 各自按自身规则分别落盘（顺序即出现顺序）。"""
    d1 = tmp_path / "A组"
    d2 = tmp_path / "B组"
    d1.mkdir()
    d2.mkdir()
    rows = [_row(str(d1 / "a1.xy")), _row(str(d1 / "a2.xy")),
            _row(str(d2 / "b1.xy"))]
    plan = batch.batch_save_plan(rows)
    assert [(str(p), len(g)) for p, g in plan] == [
        (str(d1 / "A组.csv"), 2), (str(d2 / "b1.csv"), 1)]


def test_batch_save_plan_avoids_overwrite(tmp_path):
    """同名 CSV 已存在 -> 自动追加 _1/_2 序号，不静默覆盖。"""
    d = tmp_path / "批样1"
    d.mkdir()
    (d / "批样1.csv").write_text("old", encoding="utf-8")
    (d / "批样1_1.csv").write_text("old1", encoding="utf-8")
    plan = batch.batch_save_plan([_row(str(d / "a.xy")), _row(str(d / "b.xy"))])
    dest, _group = plan[0]
    assert dest == d / "批样1_2.csv"
    assert not dest.exists(), "只规划不落盘，写入时机由上层决定"
    assert (d / "批样1.csv").read_text(encoding="utf-8") == "old"


def test_batch_save_plan_empty():
    """空结果 -> 空计划（不产生任何文件）。"""
    assert batch.batch_save_plan([]) == []


# --------------------------------------------------------------------------- #
# CSV 写出
# --------------------------------------------------------------------------- #
def test_export_batch_csv_method_a(tmp_path):
    """A 法 CSV：表头/数值/失败备注齐全，且为 UTF-8 with BOM。"""
    set_language("zh_CN")
    rows = [_row("D:/x/a.xy", wa=42.5, wr=57.5, K=1.22, ia=1200.0, ir=800.0),
            _row("D:/x/b.xy", ok=False, message="金红石型: 峰未找到")]
    dest = tmp_path / "out.csv"
    written = batch.export_batch_csv(rows, dest, method="a")
    raw = Path(written).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "应带 UTF-8 BOM（Excel 直开不乱码）"
    text = raw.decode("utf-8-sig")
    lines = text.strip().splitlines()
    assert lines[0] == ",".join([tr("batch.csv.file"), tr("batch.csv.wa"),
                                 tr("batch.csv.wr"), tr("batch.csv.k"),
                                 tr("batch.csv.ia"), tr("batch.csv.ir"),
                                 tr("batch.csv.note")])
    assert lines[1] == "a.xy,42.50,57.50,1.2200,1200.0,800.0," + tr("batch.csv.ok")
    assert lines[2].startswith('b.xy,,,,,,')
    assert "峰未找到" in lines[2]


def test_export_batch_csv_method_b_autodetect(tmp_path):
    """B 法 CSV：Rwp/Rp/χ²/判定；省略 method 时按行内容自动判定为 B 法。"""
    set_language("zh_CN")
    rows = [_row("D:/x/a.xy", wa=82.0, wr=18.0, rwp=9.42, rp=7.10, chi2=1.234),
            _row("D:/x/b.xy", wa=None, wr=None, rwp=25.5, rp=20.0, chi2=9.9),
            _row("D:/x/c.xy", ok=False, message="boom")]
    dest = tmp_path / "b.csv"
    batch.export_batch_csv(rows, dest)
    lines = dest.read_text(encoding="utf-8-sig").strip().splitlines()
    assert lines[0].endswith(tr("batch.csv.verdict"))
    assert lines[1] == f"a.xy,82.00,18.00,9.42,7.10,1.234,{tr('verdict.fit_good')}"
    assert tr("verdict.fit_bad") in lines[2], "Rwp > 10% 应判拟合不佳"
    assert "boom" in lines[3], "失败行把原因写进判定列"


def test_export_batch_csv_escapes_note(tmp_path):
    """备注里的逗号/换行被 csv 模块正确转义（不破坏列数）。"""
    rows = [_row("D:/x/a.xy", ok=False, message="bad, note\nsecond line")]
    dest = tmp_path / "esc.csv"
    batch.export_batch_csv(rows, dest, method="a")
    text = dest.read_text(encoding="utf-8-sig")
    assert '"bad, note' in text
    assert text.strip().splitlines()[1].count(",") == 7  # 6 个分隔符 + 备注内 1 个


# --------------------------------------------------------------------------- #
# A 法批量（桩测峰，不触碰真实谱）
# --------------------------------------------------------------------------- #
def _fake_measure(pat, expected, tol, **_kwargs):
    """测峰桩：A 窗口净面积 6000，R 窗口 4000；bad 谱测峰失败。"""
    if getattr(pat, "bad", False):
        return SimpleNamespace(ok=False, net_height=0.0, net_area=0.0,
                               message="峰未找到")
    if expected < 26.0:
        return SimpleNamespace(ok=True, net_height=100.0, net_area=6000.0,
                               message="")
    return SimpleNamespace(ok=True, net_height=80.0, net_area=4000.0, message="")


def _fake_pattern(bad: bool = False) -> SimpleNamespace:
    tt = np.arange(20.0, 32.0, 0.02)
    ii = 100.0 + 50.0 * np.exp(-0.5 * ((tt - 25.3) / 0.2) ** 2)
    return SimpleNamespace(two_theta=tt, intensity=ii, bad=bad,
                           meta={"source": "stub"})


def test_run_method_a_batch_aggregates_and_skips_failure(monkeypatch):
    """A 法批量：逐文件聚合 wa/wr/K/Ia/Ir，单文件失败不中断整批。"""
    monkeypatch.setattr(services, "measure_peak", _fake_measure)
    items = [("D:/x/a.xy", _fake_pattern()), ("D:/x/b.xy", _fake_pattern(bad=True)),
             ("D:/x/c.xy", _fake_pattern())]
    seen: list[tuple[str, float | None]] = []
    rows = batch.run_method_a_batch(
        items, (24.5, 26.5), (26.5, 28.5), 1.22, progress_cb=lambda m, p: seen.append((m, p)))
    assert len(rows) == 3, "失败文件也占一行（带 message）"
    assert [r["sample"] for r in rows] == ["a", "b", "c"]
    assert rows[0]["ok"] and rows[2]["ok"]
    assert not rows[1]["ok"] and "峰未找到" in rows[1]["message"]
    # K=1.22、Ia/Ir=6000/4000=1.5 -> w(锐) = 1/(1+1.22/1.5) = 55.15%
    assert rows[0]["wa"] == pytest.approx(100.0 / (1.0 + 1.22 * 4000.0 / 6000.0))
    assert rows[0]["wa"] + rows[0]["wr"] == pytest.approx(100.0)
    assert rows[0]["K"] == pytest.approx(1.22)
    assert any(tr("busy.batch_a", i=1, n=3, name="a.xy") == m for m, _p in seen)
    assert any(tr("busy.batch_a", i=3, n=3, name="c.xy") == m for m, _p in seen)


def test_run_method_a_batch_cancel_keeps_done_rows(monkeypatch):
    """取消：已算完的文件照常返回（不抛 TaskCanceled），后续文件不再处理。"""
    monkeypatch.setattr(services, "measure_peak", _fake_measure)
    items = [(f"D:/x/{n}.xy", _fake_pattern()) for n in "abcd"]
    state = {"n": 0}

    def cancel_after_two() -> bool:
        state["n"] += 1
        return state["n"] > 4  # 跑完前两个文件后取消

    rows = batch.run_method_a_batch(
        items, (24.5, 26.5), (26.5, 28.5), 1.22, cancel_cb=cancel_after_two)
    assert len(rows) == 2, "取消后已完成的两行必须保留（供上层落盘）"
    assert all(r["ok"] for r in rows)


def test_run_method_a_batch_quantity_height(monkeypatch):
    """批量沿用峰强口径：height 时取净峰高（100/80）。"""
    monkeypatch.setattr(services, "measure_peak", _fake_measure)
    rows = batch.run_method_a_batch(
        [("D:/x/a.xy", _fake_pattern())], (24.5, 26.5), (26.5, 28.5), 1.0,
        quantity="height")
    assert rows[0]["ia"] == pytest.approx(100.0)
    assert rows[0]["ir"] == pytest.approx(80.0)


def test_run_method_a_batch_reraises_core_unavailable(monkeypatch):
    """core 未就绪时整批立即失败（逐文件记 message 只会刷屏，没意义）。"""

    def boom(*_a, **_k):
        raise services.CoreUnavailableError("core missing")

    monkeypatch.setattr(services, "run_method_a", boom)
    with pytest.raises(services.CoreUnavailableError):
        batch.run_method_a_batch([("D:/x/a.xy", _fake_pattern())],
                                 (24.5, 26.5), (26.5, 28.5), 1.0)


# --------------------------------------------------------------------------- #
# 精修谱图 PNG（离屏）
# --------------------------------------------------------------------------- #
def test_export_fit_png_nonempty(tmp_path):
    """离屏 PNG：非空、PNG 魔数、dpi 150 下尺寸合理。"""
    tt = np.linspace(20.0, 32.0, 600)
    yobs = 100.0 + 50.0 * np.exp(-0.5 * ((tt - 25.3) / 0.2) ** 2)
    fit = {"two_theta": tt, "yobs": yobs, "ycalc": yobs * 0.98,
           "diff": yobs - yobs * 0.98}
    dest = tmp_path / "sample01.png"
    written = batch.export_fit_png(fit, dest)
    raw = Path(written).read_bytes()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n"
    assert len(raw) > 5000, "应是一张真实渲染的图，而非空文件"


def test_fit_png_path_siblings_data_file():
    """PNG 与数据文件同名同目录（sample01.xy -> sample01.png）。"""
    assert batch.fit_png_path("D:/data/sample01.xy") == Path("D:/data/sample01.png")
    assert batch.fit_png_path("D:/data/18%实测谱.txt") == Path("D:/data/18%实测谱.png")


# --------------------------------------------------------------------------- #
# B 法批量：真数据
# --------------------------------------------------------------------------- #
def test_run_method_b_batch_real_pd(tmp_path):
    """B 法批量真跑 pd 18%/36% 实测谱：wr 回收达标 + 逐文件 PNG 落盘 + CSV。"""
    from verify_realdata_b import load_any

    work = tmp_path / "pd"
    pats = {}
    for name in ("18%实测谱.txt", "36%实测谱.txt"):
        src = REAL / "pd" / name
        dst = work / name
        work.mkdir(parents=True, exist_ok=True)
        dst.write_bytes(src.read_bytes())
        pats[str(dst)] = load_any(dst)

    rows = batch.run_method_b_batch(list(pats.items()))
    assert len(rows) == 2
    for row in rows:
        assert row["ok"], f"{row['path']}: {row['message']}"
        assert row["rwp"] <= 10.0, f"Rwp={row['rwp']:.2f}% 应 ≤ 10%"
        assert row["wa"] is not None and row["wr"] is not None
        assert row["wa"] + row["wr"] == pytest.approx(100.0, abs=0.01)
        assert set(row["fit"]) == {"two_theta", "yobs", "ycalc", "diff"}

    wrs = {Path(r["path"]).name: r["wr"] for r in rows}
    assert wrs["18%实测谱.txt"] == pytest.approx(18.106, abs=0.5)
    assert wrs["36%实测谱.txt"] == pytest.approx(36.0, abs=3.0)

    # 逐文件 PNG（与数据同名同目录）
    pngs = []
    for row in rows:
        png = batch.fit_png_path(row["path"])
        batch.export_fit_png(row["fit"], png)
        assert png.exists() and png.stat().st_size > 5000
        pngs.append(png.name)
    assert pngs == ["18%实测谱.png", "36%实测谱.png"]

    # 同文件夹 2 个文件 -> 合并为一个 <文件夹名>.csv
    plan = batch.batch_save_plan(rows)
    assert len(plan) == 1 and plan[0][0] == work / "pd.csv"
    written = batch.export_batch_csv(plan[0][1], plan[0][0])
    raw = Path(written).read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf"), "带 UTF-8 BOM"
    text = raw.decode("utf-8-sig")
    assert "18%实测谱.txt" in text and "36%实测谱.txt" in text
    assert tr("verdict.fit_good") in text


def test_run_method_b_batch_failure_row(monkeypatch):
    """B 法批量：单文件精修异常只记 message，整批继续（不中断）。"""
    calls = {"n": 0}

    def fake_b(pat, **_kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ValueError("精修不收敛")
        tt = np.asarray(pat.two_theta)
        ycalc = np.asarray(pat.intensity) * 0.98
        return {"result": SimpleNamespace(
                    rf=SimpleNamespace(rwp=8.0, rp=6.0, chi2=1.2)),
                "two_theta": tt, "ycalc": ycalc,
                "diff": np.asarray(pat.intensity) - ycalc,
                "wa": 60.0, "wr": 40.0}

    monkeypatch.setattr(services, "run_method_b", fake_b)
    rows = batch.run_method_b_batch([("D:/x/a.xy", _fake_pattern()),
                                     ("D:/x/b.xy", _fake_pattern())])
    assert len(rows) == 2
    assert not rows[0]["ok"] and "精修不收敛" in rows[0]["message"]
    assert rows[1]["ok"] and rows[1]["wr"] == pytest.approx(40.0)
    assert "yobs" in rows[1]["fit"], "成功行必须带 fit，供画布与 PNG 使用"
    assert rows[0]["fit"] is None


def test_batch_progress_uses_sub_range(monkeypatch):
    """批量进度按文件切成互不重叠的区间（0→1 单调推进）。"""
    monkeypatch.setattr(services, "measure_peak", _fake_measure)
    seen: list[float | None] = []

    def cb(_msg, pct):
        if pct is not None:
            seen.append(pct)

    items = [(f"D:/x/{n}.xy", _fake_pattern()) for n in "abc"]
    batch.run_method_a_batch(items, (24.5, 26.5), (26.5, 28.5), 1.0, progress_cb=cb)
    assert seen, "应上报进度"
    assert max(seen) <= 1.0 + 1e-9 and min(seen) >= 0.0
    assert seen[-1] == pytest.approx(1.0), "最后一个文件跑完应到 100%"
