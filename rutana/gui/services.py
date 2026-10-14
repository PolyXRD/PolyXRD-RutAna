"""GUI → core 薄封装层。

规则（家族约定）：GUI 模块**只许**通过本模块调用 ``rutana.core`` 的算法，
且所有 core 导入都发生在函数体内（延迟导入 + 统一 try/except）。
core 未就绪/缺失时抛 ``CoreUnavailableError``（中文提示），从而保证：

1. GUI 模块本身不依赖 core 即可被导入与构造；
2. 冒烟测试可用 ``unittest.mock.patch`` 桩掉本模块的全部函数。
"""

from __future__ import annotations

from typing import Any

from rutana.i18n import tr

#: 双平行重复性限缺省值（core 未就绪时的兜底；core 内的 DEFAULT_ABS_LIMIT 优先）
FALLBACK_ABS_LIMIT = 0.15


class CoreUnavailableError(RuntimeError):
    """核心算法模块缺失或导入失败（提示文案已本地化）。"""


def _core(key: str) -> Any:
    """按显式静态 import 映射取 core 符号；失败统一抛本地化异常。

    P1-1 修复：原实现用 ``importlib.import_module(f"rutana.core.{module}")``
    的 f-string 动态导入，PyInstaller 静态分析跟不了，导致 exe 里
    A 法测峰与整个 B 法抛 CoreUnavailableError。现改为模块名字面量的
    ``from ... import ...`` 语句，PyInstaller 可完整静态跟踪。
    key 形如 ``"patterns.load_pattern"``（模块点路径.符号名）。
    """
    try:
        if key == "patterns.load_pattern":
            from rutana.core.patterns import load_pattern
            return load_pattern
        if key == "peakmeasure.measure_peak":
            from rutana.core.peakmeasure import measure_peak
            return measure_peak
        if key == "method_a.compute_ratio":
            from rutana.core.method_a import compute_ratio
            return compute_ratio
        if key == "method_a.CalibPoint":
            from rutana.core.method_a import CalibPoint
            return CalibPoint
        if key == "method_a.calibrate_k":
            from rutana.core.method_a import calibrate_k
            return calibrate_k
        if key == "method_a.combine_duplicates":
            from rutana.core.method_a import combine_duplicates
            return combine_duplicates
        if key == "profile.cif.parse_cif":
            from rutana.core.profile.cif import parse_cif
            return parse_cif
        if key == "profile.forward.ProfileParams":
            from rutana.core.profile.forward import ProfileParams
            return ProfileParams
        if key == "refine.nonlinear.RefineConfig":
            from rutana.core.refine.nonlinear import RefineConfig
            return RefineConfig
        if key == "refine.nonlinear.refine":
            from rutana.core.refine.nonlinear import refine
            return refine
    except Exception as exc:  # ImportError / AttributeError / core 内部依赖缺失
        raise CoreUnavailableError(tr("msg.core_unavailable", detail=exc)) from exc
    raise KeyError(f"未注册的 core 符号: {key}")


# --------------------------------------------------------------------------- #
# A 法（强度比值法）
# --------------------------------------------------------------------------- #
def load_pattern(path: str) -> Any:
    """读取谱图文件 -> rutana.core.dtypes.Pattern。"""
    load = _core("patterns.load_pattern")
    return load(path)


def measure_peak(pat: Any, expected: float, tol: float = 0.4) -> Any:
    """在 [expected-tol, expected+tol] 内测量净峰强度 -> PeakMeasure。"""
    measure = _core("peakmeasure.measure_peak")
    return measure(pat, expected, tol)


def compute_ratio(ia: float, ir: float, k: float) -> Any:
    """由净峰强度与 K 计算 w_a/w_r -> RatioResult。"""
    compute = _core("method_a.compute_ratio")
    return compute(ia, ir, k)


def calibrate_from_points(points: list[tuple[float, float]]) -> Any:
    """由标定表 [(ma_over_mr, ia_over_ir), ...] 计算 K -> CalibResult。"""
    point_cls = _core("method_a.CalibPoint")
    calibrate = _core("method_a.calibrate_k")
    return calibrate([point_cls(m, i) for m, i in points])


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
                 win_r: tuple[float, float], k: float) -> dict:
    """A 法全流程：双窗口测峰 + 比率计算。

    返回 ``{"ia", "ir", "measure_a", "measure_r", "result"}``，
    ``result`` 为 RatioResult（含 wa/wr/K/ia/ir）。
    """
    center_a = (win_a[0] + win_a[1]) / 2.0
    center_r = (win_r[0] + win_r[1]) / 2.0
    tol_a = max(0.05, (win_a[1] - win_a[0]) / 2.0)
    tol_r = max(0.05, (win_r[1] - win_r[0]) / 2.0)
    ma = measure_peak(pat, center_a, tol_a)
    mr = measure_peak(pat, center_r, tol_r)
    if not getattr(ma, "ok", False) or not getattr(mr, "ok", False):
        bad = "A(锐钛型)" if not getattr(ma, "ok", False) else "R(金红石型)"
        msg = getattr(ma if not getattr(ma, "ok", False) else mr, "message", "")
        raise ValueError(f"{bad}: {msg}")
    result = compute_ratio(float(ma.net_height), float(mr.net_height), k)
    return {
        "ia": float(ma.net_height),
        "ir": float(mr.net_height),
        "measure_a": ma,
        "measure_r": mr,
        "result": result,
    }


# --------------------------------------------------------------------------- #
# B 法（Rietveld 全谱拟合）
# --------------------------------------------------------------------------- #
def run_method_b(pat: Any, *, refine_zero: bool = True, refine_uvw: bool = True,
                 refine_eta: bool = False, n_bg: int = 3,
                 extra_cifs: tuple[str, ...] = ()) -> dict:
    """B 法全流程：内置两相 + 可选附加 CIF 的 Rietveld 精修。

    返回 ``{"result": RefineResult, "two_theta", "ycalc", "diff"}``，
    其中 ycalc/diff 与观测谱同网格，可直接交给画布叠加显示。
    """
    parse_cif = _core("profile.cif.parse_cif")
    profile_params = _core("profile.forward.ProfileParams")
    refine_config = _core("refine.nonlinear.RefineConfig")
    refine = _core("refine.nonlinear.refine")
    builtin_cif_path = _builtin_cif_path()

    cif_paths = [str(builtin_cif_path("anatase")), str(builtin_cif_path("rutile"))]
    cif_paths += [str(p) for p in extra_cifs]
    phases = [parse_cif(p) for p in cif_paths]

    prm0 = profile_params()
    cfg = refine_config(refine_zero=refine_zero, refine_uvw=refine_uvw,
                        refine_eta=refine_eta, n_bg=int(n_bg))
    res = refine(phases, pat, prm0, cfg)

    two_theta = pat.two_theta
    ycalc = res.ycalc
    return {
        "result": res,
        "two_theta": two_theta,
        "ycalc": ycalc,
        "diff": pat.intensity - ycalc,
    }


def _builtin_cif_path():
    """延迟获取 builtin_cif_path（避免模块顶层依赖本包外的资源定位）。"""
    from rutana.gui.resources import builtin_cif_path

    return builtin_cif_path
