"""谱图读取与基础操作 —— A/B 法共用的数据入口（T1.1 / v1.0.0 扩展）。

实现说明：参考 PolyXRD-SynthPattern 的 load_measured() 思路自行实现，
不 import 兄弟仓库（项目铁律）。

v1.0.0 新增（真实数据接入，对应 XRData/TiO2 岛津应用数据集 XRD-019）：
  1) 容忍 UTF-8 BOM（utf-8-sig）与首个非数值行（岛津导出首行为 `?`）；
  2) 支持 FullProf/GSAS 风格 pd 格式（`loop_` + `_pd_proc_2theta_corrected`
     + `_pd_meas_intensity_total` / `_pd_calc_intensity_total`）。
"""

from __future__ import annotations

from pathlib import Path

import numpy as np

from rutana.core.dtypes import Pattern

# 本卡支持的两列文本格式；.ras/.raw/.uxd 等二进制格式留待后续任务卡
SUPPORTED_EXTS = {".xy", ".txt", ".dat", ".csv"}

# FullProf pd 格式：数据块起始标记与常见列名
PD_LOOP_TOKEN = "loop_"
PD_X_NAMES = ("_pd_proc_2theta_corrected", "_pd_meas_2theta",
              "_pd_proc_2theta", "_pd_calc_2theta")
PD_Y_NAMES = ("_pd_meas_intensity_total", "_pd_calc_intensity_total",
              "_pd_meas_intensity", "_pd_calc_intensity",
              "_pd_proc_intensity_total")

# 读取时的编码候选顺序（中文 Windows 导出常见 GBK，其次 utf-8-sig/latin-1）
_ENCODINGS = ("utf-8-sig", "gbk", "latin-1")


def _read_text(path: Path) -> str:
    """按候选编码顺序读取文本；utf-8-sig 自动吃掉 BOM。"""
    raw = path.read_bytes()
    for enc in _ENCODINGS:
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("latin-1", errors="replace")


def _to_float(token: str) -> float | None:
    """把 token 解析为 float；失败返回 None。"""
    try:
        return float(token)
    except ValueError:
        return None


def _parse_two_column(text: str) -> tuple[np.ndarray, np.ndarray]:
    """解析两列文本：跳过 #/ / 开头注释行，容忍首个非数据行（表头/`?`）。"""
    xs: list[float] = []
    ys: list[float] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        s = raw.strip()
        if not s or s.startswith("#") or s.startswith("//"):
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 2:
            if not xs:  # 尚未读到数据 -> 视为表头行，容忍
                continue
            raise ValueError(f"第 {lineno} 行列数不足（需要两列）: {raw!r}")
        try:
            x = float(parts[0])
            y = float(parts[1])
        except ValueError:
            if not xs:  # 尚未读到数据 -> 视为表头行，容忍
                continue
            raise ValueError(f"第 {lineno} 行无法解析为数字: {raw!r}") from None
        xs.append(x)
        ys.append(y)
    if len(xs) < 2:
        raise ValueError("有效数据点不足 2 个，无法构成谱图")
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def is_pd_format(text: str) -> bool:
    """判断文本是否为 FullProf pd 格式（含 loop_ 与 2θ 列名）。"""
    if PD_LOOP_TOKEN not in text:
        return False
    return any(name in text for name in PD_X_NAMES)


def _parse_pd(text: str) -> tuple[np.ndarray, np.ndarray]:
    """解析 pd 格式：定位 loop_ 数据块，按列名行之后的两列取数。

    数据块内的行规则：
      - 以 `_` 开头 -> 列名行（收集）；
      - 空行 / 再次出现 `loop_` -> 数据块结束；
      - 其余必须解析出至少两个 float，否则抛 ValueError。
    """
    lines = text.splitlines()
    start = next(i for i, s in enumerate(lines)
                 if s.strip().lower() == PD_LOOP_TOKEN)
    xs: list[float] = []
    ys: list[float] = []
    names: list[str] = []
    for lineno, raw in enumerate(lines[start + 1:], start=start + 2):
        s = raw.strip()
        if not s:
            if xs:  # 数据已开始 -> 空行视为块结束
                break
            continue
        if s.lower() == PD_LOOP_TOKEN:
            break
        if s.startswith("_"):
            if xs:  # 新列名行出现在数据之后 -> 块结束
                break
            names.append(s.split()[0])
            continue
        parts = s.replace(",", " ").split()
        if len(parts) < 2:
            if not xs:
                continue
            raise ValueError(f"pd 格式第 {lineno} 行列数不足: {raw!r}")
        x = _to_float(parts[0])
        y = _to_float(parts[1])
        if x is None or y is None:
            if not xs:
                continue
            raise ValueError(f"pd 格式第 {lineno} 行无法解析为数字: {raw!r}")
        xs.append(x)
        ys.append(y)
    if len(xs) < 2:
        raise ValueError("pd 格式有效数据点不足 2 个，无法构成谱图")
    if not any(n in PD_X_NAMES for n in names):
        raise ValueError(f"pd 格式未找到 2θ 列名，实际列名: {names}")
    return np.asarray(xs, dtype=np.float64), np.asarray(ys, dtype=np.float64)


def load_pattern(path: str | Path) -> Pattern:
    """读取谱图文本，自动识别 FullProf pd 格式与普通两列格式。

    支持：UTF-8 BOM、首个非数值行（如岛津导出的 `?`）、FullProf pd。
    未知扩展名抛 NotImplementedError；行解析失败抛 ValueError。
    """
    p = Path(path)
    ext = p.suffix.lower()
    if ext not in SUPPORTED_EXTS:
        raise NotImplementedError(f"暂不支持的格式: {ext}")
    text = _read_text(p)
    if is_pd_format(text):
        tt, ii = _parse_pd(text)
        fmt = "pd"
    else:
        tt, ii = _parse_two_column(text)
        fmt = "two_column"
    anode = _guess_anode(text)
    # source_format 保留文件扩展名（v0.1.0 契约）；layout 标注实际文本布局
    meta = {"path": str(p), "source_format": ext.lstrip("."),
            "layout": fmt, "wavelength_anode": anode}
    return Pattern(two_theta=tt, intensity=ii, meta=meta)


def _guess_anode(text: str) -> str | None:
    """从文本头部猜测靶材（Cu/Fe/Co/Mo），猜不到返回 None。"""
    head = text[:4000].lower()
    for key, name in (("cuka", "Cu"), ("cu ka", "Cu"), ("fe ka", "Fe"),
                      ("co ka", "Co"), ("mo ka", "Mo")):
        if key in head:
            return name
    if "lambda=1.54" in head or "1.5406" in head:
        return "Cu"
    return None


def clip(p: Pattern, tmin: float, tmax: float) -> Pattern:
    """按 2θ 区间 [tmin, tmax] 布尔掩码裁剪（不含端外插值）。"""
    if tmin > tmax:
        raise ValueError(f"裁剪区间非法: tmin={tmin} > tmax={tmax}")
    mask = (p.two_theta >= tmin) & (p.two_theta <= tmax)
    if not bool(mask.any()):
        raise ValueError(f"裁剪区间 [{tmin}, {tmax}] 内无数据点")
    return Pattern(two_theta=p.two_theta[mask].copy(),
                   intensity=p.intensity[mask].copy(),
                   meta=dict(p.meta))


def estimate_step(p: Pattern) -> float:
    """中位数步长（度）。"""
    return p.step
