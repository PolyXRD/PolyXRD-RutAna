"""core 符号加载器（从 services 拆出以控制单文件规模）。

**唯一职责**：把 ``rutana.core`` 的符号按显式静态 import 取出来，
并把「导入失败」统一翻译成 :class:`CoreUnavailableError`。GUI 模块仍然
**只许**通过 :mod:`rutana.gui.services` 调 core；本模块是 services 的实现细节。

为什么用字面量 ``from ... import ...`` 而不是 ``importlib``：
PyInstaller 只跟踪静态 import，动态导入会被裁掉，导致 exe 里 core 全丢
（P1-1 历史缺陷）。
"""

from __future__ import annotations

import inspect
from typing import Any

from rutana.i18n import tr


class CoreUnavailableError(RuntimeError):
    """核心算法模块缺失或导入失败（提示文案已本地化）。"""


def supports_param(func: Any, name: str) -> bool:
    """探测可调用对象是否接受名为 name 的形参（含 **kwargs 兜底）。

    用于「core 是否已支持 ``progress_cb`` / ``on_iter`` / ``cancel_cb``」的
    能力探测：不支持时上层静默降级，不报错。
    """
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if name in sig.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in sig.parameters.values())


def core_symbol(key: str) -> Any:
    """按显式静态 import 映射取 core 符号；失败统一抛本地化异常。

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
        if key == "refine.realdata.real_params":
            from rutana.core.refine.realdata import real_params
            return real_params
        if key == "refine.realdata.real_config":
            from rutana.core.refine.realdata import real_config
            return real_config
        if key == "refine.nonlinear.RefineConfig":
            from rutana.core.refine.nonlinear import RefineConfig
            return RefineConfig
        if key == "refine.nonlinear.refine":
            from rutana.core.refine.nonlinear import refine
            return refine
        if key == "refine.qpa.qpa_inputs_from_cif":
            from rutana.core.refine.qpa import qpa_inputs_from_cif
            return qpa_inputs_from_cif
        if key == "refine.qpa.qpa_weights":
            from rutana.core.refine.qpa import qpa_weights
            return qpa_weights
        if key == "refine.qpa.to_ratio":
            from rutana.core.refine.qpa import to_ratio
            return to_ratio
    except Exception as exc:  # ImportError / AttributeError / core 内部依赖缺失
        raise CoreUnavailableError(tr("msg.core_unavailable", detail=exc)) from exc
    raise KeyError(f"未注册的 core 符号: {key}")
