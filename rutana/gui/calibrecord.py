"""K 标定记录（JSON）的序列化与解析。

从 :mod:`rutana.gui.kwizard` 拆出（单文件 ≤400 行约束）。

记录结构（``version = 1``）::

    {
      "version": 1,
      "win_a": [24.5, 26.5], "win_r": [26.5, 28.5],   # 标定时的取峰窗口
      "mode": "ols" | "origin",                        # 拟合口径
      "quantity": "area" | "height",                   # 峰强口径（v1.1.0，可缺省）
      "K": 1.22, "intercept": 0.001, "r2": 0.9998,     # 拟合结果（可缺省）
      "saved_at": "2026-01-01T00:00:00",
      "rows": [{"file","wr","ratio_m","ratio_i","ok","message"}, ...]
    }

解析时对缺失/越界字段做保守归一化：``wr`` 夹在 (0, 100)，
``ratio_m`` 缺失时由 ``wr`` 反算，``ok`` 缺省时按 ``ratio_i`` 是否存在推断，
``quantity`` 缺失时按 ``"area"``（v1.1.0 前的旧记录兼容）。
"""

from __future__ import annotations

import datetime
from typing import Any

#: 记录结构版本
CALIB_JSON_VERSION = 1

#: w(金红石型) 的合法区间（%），越界会被夹紧
WR_MIN, WR_MAX = 0.01, 99.99


def mass_ratio_from_wr(wr: float) -> float | None:
    """金红石型质量分数 w(R)% -> m(A)/m(R)；越界返回 None。"""
    value = float(wr)
    if value <= 0.0 or value >= 100.0:
        return None
    return (100.0 - value) / value


def build_record(*, win_a: tuple[float, float], win_r: tuple[float, float],
                 mode: str, fit: dict[str, Any] | None,
                 rows: list[dict], quantity: str = "area") -> dict:
    """组装可写入 JSON 的标定记录（``quantity`` 为峰强口径）。"""
    fit = fit or {}
    return {
        "version": CALIB_JSON_VERSION,
        "win_a": [float(win_a[0]), float(win_a[1])],
        "win_r": [float(win_r[0]), float(win_r[1])],
        "mode": "origin" if mode == "origin" else "ols",
        "quantity": "height" if quantity == "height" else "area",
        "K": fit.get("K"),
        "intercept": fit.get("intercept"),
        "r2": fit.get("r2"),
        "saved_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "rows": [
            {"file": str(r.get("file", "")), "wr": float(r.get("wr", 0.0)),
             "ratio_m": r.get("ratio_m"), "ratio_i": r.get("ratio_i"),
             "ok": bool(r.get("ok")), "message": str(r.get("message", ""))}
            for r in rows
        ],
    }


def parse_record(payload: dict) -> dict:
    """解析标定记录；返回归一化后的字段。

    返回 ``{"win_a","win_r","mode","quantity","rows"}``；``rows`` 中每项含
    ``file / wr / ratio_m / ratio_i / ok / message``。结构非法抛 ``ValueError``。
    """
    if not isinstance(payload, dict):
        raise ValueError("标定记录必须是 JSON 对象")
    raw_rows = payload.get("rows")
    if not isinstance(raw_rows, list):
        raise ValueError("缺少 rows 字段")

    rows: list[dict] = []
    for item in raw_rows:
        if not isinstance(item, dict) or not item.get("file"):
            continue
        wr = float(item.get("wr", 0.0))
        wr = min(WR_MAX, max(WR_MIN, wr))
        ratio_i = item.get("ratio_i")
        ratio_m = item.get("ratio_m")
        if ratio_m is None:
            ratio_m = mass_ratio_from_wr(wr)
        rows.append({
            "file": str(item["file"]),
            "wr": wr,
            "ratio_m": None if ratio_m is None else float(ratio_m),
            "ratio_i": None if ratio_i is None else float(ratio_i),
            "ok": bool(item.get("ok", ratio_i is not None)),
            "message": str(item.get("message", "")),
        })

    win_a = _pair(payload.get("win_a"))
    win_r = _pair(payload.get("win_r"))
    mode = "origin" if payload.get("mode") == "origin" else "ols"
    quantity = "height" if payload.get("quantity") == "height" else "area"
    return {"win_a": win_a, "win_r": win_r, "mode": mode,
            "quantity": quantity, "rows": rows}


def _pair(value: Any) -> tuple[float, float] | None:
    """把 [a, b] 归一化为 (float, float)；非法返回 None。"""
    if isinstance(value, (list, tuple)) and len(value) == 2:
        try:
            return float(value[0]), float(value[1])
        except (TypeError, ValueError):
            return None
    return None
