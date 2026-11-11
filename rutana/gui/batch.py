"""批量计算服务层（v1.2.0）：多文件 A 法 / B 法与结果落盘。

把 :mod:`rutana.gui.services` 的**单样本**算法编排成**批量**流程，并保证：

1. 单文件失败不中断整批（错误写进该行 ``message``，继续跑下一个）；
2. 可取消——取消时**已完成文件的结果照常返回**，由上层落盘（不丢弃已算成果）；
3. 与 GUI 解耦：本模块只依赖 :mod:`rutana.i18n`（文案）与 services（算法），
   不 import PySide6，因此可在无界面环境下直接单测。

结果行约定（A 法）::

    {"path","sample","wa","wr","K","ia","ir","ok","message"}

结果行约定（B 法）::

    {"path","sample","wa","wr","rwp","rp","chi2","ok","message",
     "po_r": {phase: (h,k,l,r)} 或 None,
     "fit": {"two_theta","yobs","ycalc","diff"},   # fit 仅成功行有
     "summary": RefineSummary 或 None}             # v1.7.1 精修结构摘要

CSV 一律 **UTF-8 with BOM**（``utf-8-sig``）写出：中文表头/备注在 Excel
双击直开时不乱码，同时 Python/ pandas 以 ``utf-8-sig`` 读回也能正确剥掉 BOM。
"""

from __future__ import annotations

import csv
from pathlib import Path
from typing import Any, Callable, Iterable, Sequence

from rutana.gui import services
from rutana.gui.verdict import rwp_verdict
from rutana.i18n import tr
from rutana.i18n.translations import en_US, ja_JP, zh_CN

#: 进度回调签名 cb(message: str, pct: float | None)（pct 为 0..1 比例）
ProgressCb = Callable[[str, "float | None"], None] | None

#: 冲突序号上限（防呆，正常不会触到）
_MAX_SUFFIX = 999

#: 本工具批量 CSV 的首列表头（三语全集）：识别导入时的自家产物用
_TOOL_FILE_HEADERS = frozenset(
    t.TRANSLATIONS["batch.csv.file"] for t in (zh_CN, en_US, ja_JP))
#: 本工具批量 CSV 的固定列数（A/B 两法都是 7 列）
_TOOL_CSV_COLUMNS = 7


def is_tool_csv(path: Any) -> bool:
    """判断一个文件是否为本工具批量导出的结果 CSV（而非谱图数据）。

    读首行按 UTF-8（容错 BOM/乱码）解析：列数等于本工具表头列数且首列
    是任一语言下的「文件名」表头即判定为本工具产物。普通两列谱图 CSV、
    空文件、乱码/二进制文件均返回 False（csv 解析异常同样视为非产物，
    不让导入过滤器被脏文件打崩）。
    """
    try:
        with Path(str(path)).open("r", encoding="utf-8-sig",
                                  errors="replace", newline="") as fh:
            row = next(csv.reader(fh), None)
    except OSError:
        return False
    except csv.Error:
        return False
    if not row:
        return False
    return len(row) == _TOOL_CSV_COLUMNS and row[0].strip() in _TOOL_FILE_HEADERS


def _emit(cb: ProgressCb, key: str, pct: float | None = None, **kw) -> None:
    """安全地向回调推送一条本地化进度文案（cb 为空则忽略）。"""
    if cb is None:
        return
    text = tr(key, **kw) if kw else tr(key)
    cb(text, None if pct is None else float(pct))


def _sample_name(path: Any) -> str:
    """数据路径 -> 样品名（去扩展名的文件名）。"""
    return Path(str(path)).stem


def _file_name(path: Any) -> str:
    """数据路径 -> 文件名（带扩展名，CSV 与进度文案用，便于回溯源文件）。"""
    return Path(str(path)).name


def _fmt(value: Any, spec: str) -> str:
    """数值格式化；None 输出空串（CSV 里留空比写 None 干净）。"""
    if value is None:
        return ""
    try:
        return format(float(value), spec)
    except (TypeError, ValueError):
        return str(value)


def _canceled(cancel_cb: Callable[[], bool] | None) -> bool:
    """取消探测（回调不可调用时视为未取消）。"""
    return bool(callable(cancel_cb) and cancel_cb())


# --------------------------------------------------------------------------- #
# 批量计算
# --------------------------------------------------------------------------- #
def run_method_a_batch(items: Sequence[tuple[Any, Any]], win_a: tuple[float, float],
                       win_r: tuple[float, float], k: float, *,
                       quantity: str = services.QUANTITY_AREA,
                       progress_cb: ProgressCb = None,
                       cancel_cb: Callable[[], bool] | None = None) -> list[dict]:
    """逐个文件跑 A 法（单文件口径，不做双平行）。

    items: ``[(path, Pattern), ...]``；单文件失败只记 ``message`` 并继续。
    被取消时**停止后续文件并原样返回已完成的行**（不抛 :class:`TaskCanceled`），
    保证上层能把已算成果落盘。返回行列表（顺序与 items 中已处理的部分一致）。
    """
    total = max(1, len(items))
    out: list[dict] = []
    for idx, item in enumerate(items, start=1):
        path, pat = item
        name = _file_name(path)          # 进度/CSV 用文件名
        sample = _sample_name(path)     # 结果行的样品名（去扩展名）
        if _canceled(cancel_cb):
            break
        _emit(progress_cb, "busy.batch_a", (idx - 1) / total,
              i=idx, n=len(items), name=name)
        row: dict[str, Any] = {
            "path": str(path), "sample": sample, "wa": None, "wr": None,
            "K": float(k), "ia": None, "ir": None, "ok": False, "message": ""}
        try:
            res = services.run_method_a(
                pat, win_a, win_r, k, quantity=quantity,
                progress_cb=services.sub_progress(progress_cb,
                                                  (idx - 1) / total, idx / total),
                cancel_cb=cancel_cb)
        except services.TaskCanceled:
            break
        except services.CoreUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 单文件失败不中断整批
            row["message"] = str(exc)
            out.append(row)
            continue
        result = res["result"]
        row.update(wa=float(getattr(result, "wa", 0.0)),
                   wr=float(getattr(result, "wr", 0.0)),
                   K=float(getattr(result, "K", k)),
                   ia=float(getattr(result, "ia", 0.0)),
                   ir=float(getattr(result, "ir", 0.0)),
                   ok=True)
        out.append(row)
        _emit(progress_cb, "busy.batch_a", idx / total, i=idx, n=len(items), name=name)
    return out


def run_method_b_batch(items: Sequence[tuple[Any, Any]], *, refine_zero: bool = True,
                       refine_uvw: bool = True, refine_eta: bool = True,
                       n_bg: int = 3, refine_po: bool | None = None,
                       extra_cifs: tuple[str, ...] = (),
                       progress_cb: ProgressCb = None,
                       on_iter: Callable[[int, float], None] | None = None,
                       cancel_cb: Callable[[], bool] | None = None) -> list[dict]:
    """逐个文件跑 B 法 Rietveld 精修（单文件 ~10 s，务必走后台线程）。

    items: ``[(path, Pattern), ...]``；成功行的 ``fit`` 携带绘制谱图所需的
    ``two_theta / yobs / ycalc / diff``（供主画布与逐文件 PNG 导出），
    ``po_r`` 携带精修出的每相 March–Dollase 参数（未开启时为 None；
    仅用于界面回填，不写入 CSV——CSV 列数保持 7 列不变）。
    单文件失败只记 ``message`` 并继续；取消时返回已完成的行（同 A 法）。
    """
    total = max(1, len(items))
    out: list[dict] = []
    for idx, item in enumerate(items, start=1):
        path, pat = item
        name = _file_name(path)          # 进度/CSV 用文件名
        sample = _sample_name(path)     # 结果行的样品名（去扩展名）
        if _canceled(cancel_cb):
            break
        _emit(progress_cb, "busy.batch_b", (idx - 1) / total,
              i=idx, n=len(items), name=name)
        row: dict[str, Any] = {
            "path": str(path), "sample": sample, "wa": None, "wr": None,
            "rwp": None, "rp": None, "chi2": None, "ok": False, "message": "",
            "po_r": None, "fit": None, "summary": None}
        try:
            res = services.run_method_b(
                pat, refine_zero=refine_zero, refine_uvw=refine_uvw,
                refine_eta=refine_eta, n_bg=n_bg, refine_po=refine_po,
                extra_cifs=extra_cifs,
                progress_cb=services.sub_progress(progress_cb,
                                                  (idx - 1) / total, idx / total),
                on_iter=on_iter, cancel_cb=cancel_cb)
        except services.TaskCanceled:
            break
        except services.CoreUnavailableError:
            raise
        except Exception as exc:  # noqa: BLE001 —— 单文件失败不中断整批
            row["message"] = str(exc)
            out.append(row)
            continue
        rf = res["result"].rf
        row.update(wa=res.get("wa"), wr=res.get("wr"),
                   rwp=float(rf.rwp), rp=float(rf.rp), chi2=float(rf.chi2), ok=True,
                   po_r=res.get("po_r"), summary=res.get("summary"))
        row["fit"] = {"two_theta": res["two_theta"], "yobs": pat.intensity,
                      "ycalc": res["ycalc"], "diff": res["diff"]}
        out.append(row)
        _emit(progress_cb, "busy.batch_b", idx / total, i=idx, n=len(items), name=name)
    return out


# --------------------------------------------------------------------------- #
# 结果落盘
# --------------------------------------------------------------------------- #
def batch_save_plan(rows: Iterable[dict]) -> list[tuple[Path, list[dict]]]:
    """按**来源文件夹**分组给出 CSV 落盘计划 ``[(dest_path, rows), ...]``。

    命名规则（v1.2.0）：

    - 同一来源文件夹内 ≥2 个文件 → 合并成一个 CSV，名为 ``<文件夹名>.csv``；
    - 同一来源文件夹内只有 1 个文件 → 单个 CSV，名为 ``<数据文件去扩展名>.csv``；
    - 多个不同文件夹 → 各自按上面规则分别保存；
    - 目标已存在 → 自动追加 ``_1`` / ``_2`` … 序号，绝不静默覆盖。
    """
    groups: dict[str, list[dict]] = {}
    parents: dict[str, Path] = {}
    order: list[str] = []
    for row in rows:
        parent = Path(str(row["path"])).parent
        key = str(parent)
        if key not in groups:
            groups[key] = []
            parents[key] = parent
            order.append(key)
        groups[key].append(row)

    plan: list[tuple[Path, list[dict]]] = []
    for key in order:
        group = groups[key]
        if len(group) == 1:
            base = _sample_name(group[0]["path"])
        else:
            base = parents[key].name or "batch"
        plan.append((_unique_path(parents[key] / f"{base}.csv"), group))
    return plan


def _unique_path(path: Path) -> Path:
    """目标已存在时追加 _1/_2… 序号（不覆盖既有文件）。"""
    if not path.exists():
        return path
    for i in range(1, _MAX_SUFFIX + 1):
        cand = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not cand.exists():
            return cand
    return path


def _csv_header(method: str) -> list[str]:
    """A/B 两法的本地化表头。"""
    if method == "b":
        return [tr("batch.csv.file"), tr("batch.csv.wa"), tr("batch.csv.wr"),
                tr("batch.csv.rwp"), tr("batch.csv.rp"), tr("batch.csv.chi2"),
                tr("batch.csv.verdict")]
    return [tr("batch.csv.file"), tr("batch.csv.wa"), tr("batch.csv.wr"),
            tr("batch.csv.k"), tr("batch.csv.ia"), tr("batch.csv.ir"),
            tr("batch.csv.note")]


def _csv_row(row: dict, method: str) -> list[str]:
    """结果行 -> CSV 单元（按方法取列）。"""
    if method == "b":
        if not row.get("ok"):
            verdict = str(row.get("message") or "")
        else:
            # 四档判定口径统一见 rutana.gui.verdict（v1.6.2）
            rwp = row.get("rwp")
            verdict = tr("verdict.na" if rwp is None
                         else rwp_verdict(float(rwp))[0])
        return [_file_name(row["path"]), _fmt(row.get("wa"), ".2f"),
                _fmt(row.get("wr"), ".2f"), _fmt(row.get("rwp"), ".2f"),
                _fmt(row.get("rp"), ".2f"), _fmt(row.get("chi2"), ".3f"), verdict]
    note = tr("batch.csv.ok") if row.get("ok") else str(row.get("message") or "")
    return [_file_name(row["path"]), _fmt(row.get("wa"), ".2f"),
            _fmt(row.get("wr"), ".2f"), _fmt(row.get("K"), ".4f"),
            _fmt(row.get("ia"), ".1f"), _fmt(row.get("ir"), ".1f"), note]


def export_batch_csv(rows: Sequence[dict], dest_path: Any,
                     method: str | None = None) -> str:
    """把批量结果写成 CSV（UTF-8 with BOM），返回实际写入的路径。

    ``method`` 为 ``"a"`` / ``"b"``；省略时按行内容自动判定（有 rwp 列即 B 法）。
    用 :mod:`csv` 而非手工拼接，保证备注里的逗号/换行被正确转义。
    """
    rows = list(rows)
    if method is None:
        method = "b" if any("rwp" in row for row in rows) else "a"
    dest = Path(str(dest_path))
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as fh:
        writer = csv.writer(fh)
        writer.writerow(_csv_header(method))
        for row in rows:
            writer.writerow(_csv_row(row, method))
    return str(dest)


def export_fit_png(fit: dict, path: Any) -> str:
    """离屏渲染单份精修谱图 PNG（Agg 后端，dpi=150），不依赖主画布。

    fit: ``{"two_theta","yobs","ycalc","diff"}``；样式与主画布同源
    （:func:`rutana.gui.canvas.draw_fit`），保证导出与界面所见一致。
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    from matplotlib.figure import Figure

    from rutana.gui.canvas import draw_fit

    fig = Figure(figsize=(6.4, 4.8), dpi=150)
    FigureCanvasAgg(fig)
    ax_main, ax_diff = fig.subplots(2, 1, height_ratios=[2, 1], sharex=True)
    draw_fit(ax_main, ax_diff, fit["two_theta"], fit["yobs"],
             fit["ycalc"], fit["diff"])
    fig.tight_layout()
    fig.savefig(str(path), dpi=150, facecolor="white")
    return str(path)


def fit_png_path(data_path: Any) -> Path:
    """数据文件 -> 同名 PNG 路径（sample01.xy -> sample01.png，与数据同目录）。"""
    return Path(str(data_path)).with_suffix(".png")
