"""GUI → core 薄封装层。

规则（家族约定）：GUI 模块**只许**通过本模块调用 ``rutana.core`` 的算法，
且所有 core 导入都发生在函数体内（延迟导入 + 统一 try/except）。
core 未就绪/缺失时抛 ``CoreUnavailableError``（中文提示），从而保证：

1. GUI 模块本身不依赖 core 即可被导入与构造；
2. 冒烟测试可用 ``unittest.mock.patch`` 桩掉本模块的全部函数。

v1.0.0 新增（进度反馈）：全部耗时函数统一接受 ``progress_cb`` / ``on_iter`` /
``cancel_cb`` 三个**可选**回调（在参数列表最后，默认 None）。

**进度值协议**（与 ``rutana.core.peakmeasure`` 一致）：``progress_cb(msg, pct)``
中 ``pct`` 为 **0..1 的比例**（``None`` 或负值表示不确定）。GUI 侧由
:mod:`rutana.gui.workers` 统一归一化为 0..100 百分比后驱动进度条，
因此 core 若改用百分比写法（0..100）也能被同一适配层兼容。

本模块用 :func:`supports_param` 探测 core 是否支持这些回调，**不支持即静默降级**
（只在阶段级别回调，粒度粗但不报错），因此 core 升级前后都能正常工作。
"""

from __future__ import annotations

from typing import Any, Callable

from rutana.gui.corenodes import CoreUnavailableError, core_symbol, supports_param
from rutana.i18n import tr

#: 双平行重复性限缺省值（core 未就绪时的兜底；core 内的 DEFAULT_ABS_LIMIT 优先）
FALLBACK_ABS_LIMIT = 0.15

#: B 法 Rwp 拟合良好阈值（%）
RWP_GOOD_LIMIT = 10.0

# PROTOCOL_V100 的背景参数（docs/VALIDATION_v1.0.0.md §A.3 实证最优配置）。
# v1.3.0 起 GUI 的 A 法测峰（K 标定向导与样品计算两条路径）统一传给 core，
# 消除「GUI 用 core 缺省背景参数」与「core v1.0.0 协议」不一致造成的
# 跨 K 系统偏差（对齐前 pd 全谱实测谱 wr 最大相对误差 −15.9%）。
# 数值与 core 的 PROTOCOL_V100（rutana.core.peakmeasure）保持同步。
V100_BG_PARAMS: dict[str, Any] = {"mode": "linear_edges", "edge_frac": 0.14}
V100_BG_MARGIN = 0.18

#: 进度回调签名 cb(message: str, pct: float | None)（pct 为 0..1 比例）
ProgressCb = Callable[[str, "float | None"], None] | None


class TaskCanceled(RuntimeError):
    """用户请求取消且底层 core 响应了取消（由 core 抛或本模块转抛）。"""


def _core(key: str) -> Any:
    """取 core 符号（实现见 :mod:`rutana.gui.corenodes`）。"""
    return core_symbol(key)


def _try_core(key: str) -> Any:
    """取 core 符号；core 未就绪返回 None（用于能力探测，不弹错）。"""
    try:
        return _core(key)
    except Exception:  # noqa: BLE001 —— 能力探测失败即视为不支持
        return None


def _emit(cb: ProgressCb, key: str, pct: float | None = None, **kw) -> None:
    """安全地向回调推送一条本地化阶段文案（cb 为空则忽略；pct 为 0..1）。"""
    if cb is None:
        return
    text = tr(key, **kw) if kw else tr(key)
    cb(text, None if pct is None else float(pct))


def sub_progress(cb: ProgressCb, lo: float, hi: float) -> ProgressCb:
    """把子步骤的 0..1 进度线性映射到 ``[lo, hi]`` 比例区间。

    用于把 core 单峰测峰的 0..1 进度嵌入整体流程（如第一个峰 0.10..0.45、
    第二个峰 0.50..0.90），避免进度条在双峰测量时来回跳动。
    """
    if cb is None:
        return None

    def inner(msg: str, pct: float | None = None) -> None:
        try:
            value = float(pct) if pct is not None else -1.0
        except (TypeError, ValueError):
            value = -1.0
        if value < 0.0:
            out: float | None = None
        else:
            out = lo + (hi - lo) * min(1.0, value)
        cb(str(msg), out)

    return inner


def supports_progress(method: str) -> bool:
    """核心<a>/<b>是否支持 ``progress_cb``。不支持时 UI 走不确定模式。"""
    if method == "a":
        fn = _try_core("peakmeasure.measure_peak")
        return fn is not None and supports_param(fn, "progress_cb")
    fn = _try_core("refine.nonlinear.refine")
    return fn is not None and supports_param(fn, "progress_cb")


def supports_iteration(method: str = "b") -> bool:
    """是否支持 B 法的 ``on_iter(gen, rwp)`` 逐代回调。"""
    if method != "b":
        return False
    fn = _try_core("refine.nonlinear.refine")
    return fn is not None and supports_param(fn, "on_iter")


def supports_cancel(method: str) -> bool:
    """是否支持 ``cancel_cb``。据此决定是否显示「取消」按钮。"""
    if method == "a":
        fn = _try_core("peakmeasure.measure_peak")
        return fn is not None and supports_param(fn, "cancel_cb")
    fn = _try_core("refine.nonlinear.refine")
    return fn is not None and supports_param(fn, "cancel_cb")


# --------------------------------------------------------------------------- #
# A 法（强度比值法）
# --------------------------------------------------------------------------- #
def load_pattern(path: str, progress_cb: ProgressCb = None) -> Any:
    """读取谱图文件 -> rutana.core.dtypes.Pattern。"""
    _emit(progress_cb, "busy.load", 0.05)
    load = _core("patterns.load_pattern")
    return load(path)


def _v100_bg() -> Any:
    """构造 PROTOCOL_V100 背景配置（延迟导入 core，保持本模块懒加载约定）。"""
    return _core("background.BgConfig")(**V100_BG_PARAMS)


def measure_peak(pat: Any, expected: float, tol: float = 0.4,
                 progress_cb: ProgressCb = None,
                 cancel_cb: Callable[[], bool] | None = None) -> Any:
    """在 [expected-tol, expected+tol] 内测量净峰强度 -> PeakMeasure。

    v1.3.0 起统一传入 PROTOCOL_V100 的背景参数（``V100_BG_PARAMS`` /
    ``V100_BG_MARGIN``，见 docs/VALIDATION_v1.0.0.md §A.3）：K 标定向导
    （``measure_calib_rows``）与样品计算（``_measure_ratio``）都经本函数
    测峰，天然同口径（同参铁律）；峰强口径由调用方另行指定。
    """
    measure = _core("peakmeasure.measure_peak")
    kwargs: dict[str, Any] = {"cfg": _v100_bg(), "bg_margin": V100_BG_MARGIN}
    if supports_param(measure, "progress_cb"):
        kwargs["progress_cb"] = progress_cb
    if cancel_cb is not None and supports_param(measure, "cancel_cb"):
        kwargs["cancel_cb"] = cancel_cb
    return measure(pat, expected, tol, **kwargs)


#: 峰强口径：净峰面积（v1.0.0 实测最优，默认）与净峰高
QUANTITY_AREA = "area"
QUANTITY_HEIGHT = "height"


def _peak_intensity(m: Any, quantity: str = QUANTITY_AREA) -> float:
    """按口径从 PeakMeasure 取峰强（area=净峰面积 / height=净峰高）。"""
    if quantity == QUANTITY_HEIGHT:
        return float(getattr(m, "net_height", 0.0))
    return float(getattr(m, "net_area", 0.0))


def compute_ratio(ia: float, ir: float, k: float) -> Any:
    """由净峰强度与 K 计算 w_a/w_r -> RatioResult。"""
    compute = _core("method_a.compute_ratio")
    return compute(ia, ir, k)


def calibrate_from_points(points: list[tuple[float, float]],
                          force_zero: bool = False) -> Any:
    """由标定表 [(ma_over_mr, ia_over_ir), ...] 计算 K -> CalibResult。

    force_zero=False（默认，带截距 OLS）：采用 polyfit 斜率；
    force_zero=True：采用强制过原点的最小二乘斜率 K0。
    两种口径下 intercept / r2 均按带截距 OLS 回填，供上层诊断与告警。
    """
    point_cls = _core("method_a.CalibPoint")
    calibrate = _core("method_a.calibrate_k")
    kwargs = {"force_zero": bool(force_zero)} if supports_param(
        calibrate, "force_zero") else {}
    return calibrate([point_cls(m, i) for m, i in points], **kwargs)


def combine_duplicates(r1: Any, r2: Any, limit: float | None = None) -> dict:
    """合并双平行测定结果 -> {"wa_mean","abs_diff","within_limit","limit"}。"""
    if limit is None:
        try:
            import rutana.core.method_a as method_a

            limit = float(getattr(method_a, "DEFAULT_ABS_LIMIT", FALLBACK_ABS_LIMIT))
        except Exception:
            limit = FALLBACK_ABS_LIMIT
    combine = _core("method_a.combine_duplicates")
    return combine(r1, r2, limit)


def run_method_a(pat: Any, win_a: tuple[float, float],
                 win_r: tuple[float, float], k: float,
                 second_pat: Any = None, *, quantity: str = QUANTITY_AREA,
                 progress_cb: ProgressCb = None,
                 cancel_cb: Callable[[], bool] | None = None) -> dict:
    """A 法全流程：双窗口测峰 + 比率计算（可选第二份平行谱做双平行）。

    ``quantity`` 为峰强口径：``"area"``（净峰面积，默认）或 ``"height"``
    （净峰高）。返回 ``{"ia","ir","measure_a","measure_r","result","dup"}``，
    ``result`` 为 RatioResult（含 wa/wr/K/ia/ir），``dup`` 为合并结果或 None。
    """
    _emit(progress_cb, "busy.measure", 0.05)
    first = _measure_ratio(
        pat, win_a, win_r, quantity,
        sub_progress(progress_cb, 0.05, 0.25), sub_progress(progress_cb, 0.25, 0.45),
        cancel_cb)
    _emit(progress_cb, "busy.ratio", 0.50)
    result = compute_ratio(first["ia"], first["ir"], k)
    dup = None
    if second_pat is not None:
        second = _measure_ratio(
            second_pat, win_a, win_r, quantity,
            sub_progress(progress_cb, 0.50, 0.70),
            sub_progress(progress_cb, 0.70, 0.90), cancel_cb)
        result2 = compute_ratio(second["ia"], second["ir"], k)
        _emit(progress_cb, "busy.ratio", 0.95)
        dup = combine_duplicates(result, result2)
    else:
        result2 = None
    _emit(progress_cb, "busy.ratio", 1.0)
    return {
        "ia": first["ia"],
        "ir": first["ir"],
        "measure_a": first["measure_a"],
        "measure_r": first["measure_r"],
        "result": result,
        "result2": result2,
        "dup": dup,
    }


def _measure_ratio(pat: Any, win_a: tuple[float, float], win_r: tuple[float, float],
                   quantity: str, cb_a: ProgressCb, cb_r: ProgressCb,
                   cancel_cb: Callable[[], bool] | None) -> dict:
    """在一个窗口对上测量两相峰强（A 峰/ R 峰各自独立的子进度区间）。

    ``quantity`` 为峰强口径（``"area"`` 净峰面积 / ``"height"`` 净峰高）。
    两相分别映射到互不重叠的进度区间，保证进度条单调推进、不来回跳动；
    被用户取消时抛 :class:`TaskCanceled`。
    """
    center_a = (win_a[0] + win_a[1]) / 2.0
    center_r = (win_r[0] + win_r[1]) / 2.0
    tol_a = max(0.05, (win_a[1] - win_a[0]) / 2.0)
    tol_r = max(0.05, (win_r[1] - win_r[0]) / 2.0)
    ma = measure_peak(pat, center_a, tol_a, progress_cb=cb_a, cancel_cb=cancel_cb)
    mr = measure_peak(pat, center_r, tol_r, progress_cb=cb_r, cancel_cb=cancel_cb)
    if callable(cancel_cb) and cancel_cb():
        raise TaskCanceled(tr("msg.busy_canceled"))
    if not getattr(ma, "ok", False) or not getattr(mr, "ok", False):
        bad_ma = not getattr(ma, "ok", False)
        bad: Any = ma if bad_ma else mr
        name = "A(锐钛型)" if bad_ma else "R(金红石型)"
        raise ValueError(f"{name}: {getattr(bad, 'message', '')}")
    return {
        "ia": _peak_intensity(ma, quantity),
        "ir": _peak_intensity(mr, quantity),
        "measure_a": ma,
        "measure_r": mr,
    }


# --------------------------------------------------------------------------- #
# K 标定向导用：批量测量标准混合样
# --------------------------------------------------------------------------- #
def measure_calib_rows(rows: list[dict], win_a: tuple[float, float],
                       win_r: tuple[float, float], *,
                       quantity: str = QUANTITY_AREA,
                       progress_cb: ProgressCb = None,
                       cancel_cb: Callable[[], bool] | None = None) -> list[dict]:
    """逐行读取谱图并测量 I(A)/I(R)。

    rows: ``[{"file": str, "wr": float(金红石型质量分数 %)}, ...]``
    ``quantity`` 为峰强口径（``"area"`` 净峰面积 / ``"height"`` 净峰高）。
    返回逐行结果列表（顺序一致）::

        {"file","wr","ratio_m","ratio_i","ia","ir","ok","message"}
    """
    center_a = (win_a[0] + win_a[1]) / 2.0
    center_r = (win_r[0] + win_r[1]) / 2.0
    tol_a = max(0.05, (win_a[1] - win_a[0]) / 2.0)
    tol_r = max(0.05, (win_r[1] - win_r[0]) / 2.0)
    total = len(rows)
    out: list[dict] = []
    for idx, spec in enumerate(rows, start=1):
        if callable(cancel_cb) and cancel_cb():
            raise TaskCanceled(tr("msg.busy_canceled"))
        path = str(spec.get("file", ""))
        wr = float(spec.get("wr", 0.0))
        _emit(progress_cb, "busy.calib_row", (idx - 1) / max(1, total),
              i=idx, n=total)
        row = {"file": path, "wr": wr, "ratio_m": mass_ratio_from_wr(wr),
               "ratio_i": None, "ia": None, "ir": None, "ok": False, "message": ""}
        try:
            pat = load_pattern(path)
            ma = measure_peak(pat, center_a, tol_a)
            mr = measure_peak(pat, center_r, tol_r)
            ia = _peak_intensity(ma, quantity)
            ir = _peak_intensity(mr, quantity)
            if not getattr(ma, "ok", False) or not getattr(mr, "ok", False):
                bad = ma if not getattr(ma, "ok", False) else mr
                row["message"] = str(getattr(bad, "message", ""))
            elif ir <= 0:
                row["message"] = "ir<=0"
            else:
                row.update(ia=ia, ir=ir, ratio_i=ia / ir, ok=True)
        except Exception as exc:  # noqa: BLE001 —— 单行失败不影响整批
            row["message"] = str(exc)
        out.append(row)
        _emit(progress_cb, "busy.calib_row", idx / max(1, total), i=idx, n=total)
    return out


def mass_ratio_from_wr(wr: float) -> float | None:
    """金红石型质量分数 w(R)% -> m(A)/m(R) = (100-wR)/wR。"""
    wr = float(wr)
    if wr <= 0.0 or wr >= 100.0:
        return None
    return (100.0 - wr) / wr


def wr_from_mass_ratio(ratio_m: float) -> float:
    """m(A)/m(R) -> 金红石型质量分数 w(R)% = 100/(1+m(A)/m(R))。"""
    r = float(ratio_m)
    if r < 0:
        return 0.0
    return 100.0 / (1.0 + r)


# --------------------------------------------------------------------------- #
# B 法（Rietveld 全谱拟合）
# --------------------------------------------------------------------------- #
def run_method_b(pat: Any, *, refine_zero: bool = True, refine_uvw: bool = True,
                 refine_eta: bool = True, n_bg: int = 3,
                 extra_cifs: tuple[str, ...] = (), progress_cb: ProgressCb = None,
                 on_iter: Callable[[int, float], None] | None = None,
                 cancel_cb: Callable[[], bool] | None = None) -> dict:
    """B 法全流程：内置两相 + 可选附加 CIF 的 Rietveld 精修。

    返回 ``{"result": RefineResult, "two_theta", "ycalc", "diff", "wa", "wr"}``，
    其中 ycalc/diff 与观测谱同网格，可直接交给画布叠加显示；
    ``wa``/``wr`` 为内置两相的 w(锐钛型)% / w(金红石型)%（Hill–Howard 定量，
    定量失败时为 None，不影响 R 因子结果）。
    """
    parse_cif = _core("profile.cif.parse_cif")
    profile_params = _core("refine.realdata.real_params")
    refine_config = _core("refine.realdata.real_config")
    refine = _core("refine.nonlinear.refine")
    builtin_cif_path = _builtin_cif_path()

    _emit(progress_cb, "busy.refine_start", 0.10)
    cif_paths = [str(builtin_cif_path("anatase")), str(builtin_cif_path("rutile"))]
    cif_paths += [str(p) for p in extra_cifs]
    if callable(cancel_cb) and cancel_cb():
        raise TaskCanceled(tr("msg.busy_canceled"))
    _emit(progress_cb, "busy.load", 0.25)
    phases = [parse_cif(p) for p in cif_paths]

    # v1.0.0: GUI 面向真实粉末谱，默认走 realdata 推荐配置
    # （tent 背景 80 节点 + asym/bfactor/晶胞精修 + 积分强度口径）。
    # 调用方显式传入的开关仍然生效；n_bg=3 视为"未设置"，改用 80。
    prm0 = profile_params()
    cfg_overrides: dict[str, Any] = {
        "refine_zero": refine_zero, "refine_uvw": refine_uvw,
        "refine_eta": refine_eta,
        "n_bg": 80 if int(n_bg) == 3 else int(n_bg)}
    # core 的进度/迭代回调走 RefineConfig 字段（refine() 签名不直接收回调）；
    # 用 real_config 探测能力，旧版 core 不支持时静默降级为不确定模式。
    if progress_cb is not None and supports_param(refine_config, "progress_cb"):
        cfg_overrides["progress_cb"] = sub_progress(progress_cb, 0.30, 1.0)
    if on_iter is not None and supports_param(refine_config, "on_iter"):
        cfg_overrides["on_iter"] = on_iter
    cfg = refine_config(**cfg_overrides)
    kwargs: dict[str, Any] = {}
    if cancel_cb is not None and supports_param(refine, "cancel_cb"):
        kwargs["cancel_cb"] = cancel_cb
    res = refine(phases, pat, prm0, cfg, **kwargs)
    _emit(progress_cb, "busy.refine_start", 1.0)

    two_theta = pat.two_theta
    ycalc = res.ycalc
    wa, wr = _b_qpa(phases, res)
    return {
        "result": res,
        "two_theta": two_theta,
        "ycalc": ycalc,
        "diff": pat.intensity - ycalc,
        "wa": wa,
        "wr": wr,
    }


def _b_qpa(phases: list, res: Any) -> tuple[float | None, float | None]:
    """由精修结果换算内置两相 (w(锐钛型)%, w(金红石型)%)；失败返回 (None, None)。

    Hill–Howard 公式（见 :mod:`rutana.core.refine.qpa`）：W ∝ S·Z·V·M；
    晶胞体积按精修后的晶胞缩放（``cell_scales`` 的 (fa, fc) 作用于 a/c 轴）。
    仅取前两相（内置锐钛/金红石）做相对比率，附加物相不参与；任何定量
    异常都降级为 (None, None)，不阻断 R 因子结果展示。
    """
    try:
        qpa_inputs = _core("refine.qpa.qpa_inputs_from_cif")
        qpa_weights = _core("refine.qpa.qpa_weights")
        to_ratio = _core("refine.qpa.to_ratio")
        st_a, st_r = phases[0], phases[1]
        za, _va0, ma_ = qpa_inputs(st_a, "O2 Ti")
        zr, _vr0, mr_ = qpa_inputs(st_r, "O2 Ti")
        (fa_a, fc_a), (fa_r, fc_r) = res.cell_scales
        va = (st_a.cell[0] * fa_a) ** 2 * (st_a.cell[2] * fc_a)
        vr = (st_r.cell[0] * fa_r) ** 2 * (st_r.cell[2] * fc_r)
        ws = qpa_weights([(st_a.name, float(res.scales[0]), za, va, ma_),
                          (st_r.name, float(res.scales[1]), zr, vr, mr_)])
        return to_ratio(ws, 0, 1)
    except Exception:  # noqa: BLE001 —— 定量失败不阻断 R 因子结果
        return None, None


def _builtin_cif_path():
    """延迟获取 builtin_cif_path（避免模块顶层依赖本包外的资源定位）。"""
    from rutana.gui.resources import builtin_cif_path

    return builtin_cif_path
