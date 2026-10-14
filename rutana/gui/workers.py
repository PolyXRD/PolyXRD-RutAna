"""后台线程：把 core 计算放到 QThread，主线程只刷新 UI（禁止冻屏）。

约定（与 A/B 组 core 的适配契约）：

- core 侧算法**可选**支持 ``progress_cb(msg, pct)``、``on_iter(gen, rwp)``、
  ``cancel_cb()`` 三个回调（参数在最后、默认 None，A/B 两组正在并行加入）；
- 本模块不假设它们一定存在：先用 ``inspect.signature`` 探测，再决定是否注入；
  core 版本不支持时**静默降级为不确定模式**（转圈 + 已用时 + 阶段文案），
  不会因为 core 未升级而阻塞或报错；
- 进度值统一经 :func:`pct_to_percent` 归一化：core 的 **0..1 比例**
  （与 ``rutana.core.peakmeasure`` 一致）转成进度条用的 0..100 整数百分比；
- 异常原样回传主线程（保留 ``CoreUnavailableError`` 语义），由调用端决定文案。
"""

from __future__ import annotations

import inspect
import threading
from typing import Any, Callable, Sequence

from PySide6.QtCore import QObject, QThread, Signal
from PySide6.QtWidgets import QWidget

#: 进度回调签名：core 调用 cb(msg: str, pct: float|None)，pct 为 0..1 比例
ProgressCb = Callable[[str, "float | None"], None]


def pct_to_percent(pct: object) -> int:
    """把 core 的进度值归一化为 0..100 整数百分比（-1 = 不确定）。

    core 契约（``rutana.core.peakmeasure`` / 精修）为 **0..1 比例**；
    为兼容可能出现的百分比写法，约定：``pct <= 1`` 视为比例，否则视为百分比。
    ``None`` / 不可解析 / 负值一律视为不确定。
    """
    if pct is None:
        return -1
    try:
        value = float(pct)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return -1
    if value < 0.0:
        return -1
    out = int(round(value * 100.0)) if value <= 1.0 else int(round(value))
    return max(0, min(100, out))


def supports_param(func: Any, name: str) -> bool:
    """探测可调用对象是否接受名为 name 的形参（含 **kwargs 兜底）。"""
    try:
        sig = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    if name in sig.parameters:
        return True
    return any(p.kind is inspect.Parameter.VAR_KEYWORD
               for p in sig.parameters.values())


def call_with_extras(func: Callable[..., Any], args: Sequence[Any] = (),
                     kwargs: dict | None = None,
                     extras: dict | None = None) -> Any:
    """调用 func 并尽力注入 extras 中的回调；core 不支持则自动降级。

    extras 形如 ``{"progress_cb": callable, "on_iter": callable}``。
    只有被 callee 真实接受的键才会被传入，因此旧版 core 也能正常调用。
    """
    kw: dict[str, Any] = dict(kwargs or {})
    want = {k: v for k, v in (extras or {}).items() if v is not None}
    usable = {k: v for k, v in want.items() if supports_param(func, k)}
    try:
        return func(*tuple(args), **kw, **usable)
    except TypeError as exc:  # 极少数内建/包装函数签名不可信时二次降级
        if usable and any(n in str(exc) for n in usable):
            return func(*tuple(args), **kw)
        raise


class TaskSignals(QObject):
    """跨线程信号集合（主线程连接/处理）。"""

    #: (阶段文案, 百分比) —— pct < 0 表示不确定
    progressed = Signal(str, int)
    #: (代数, Rwp%) —— B 法 LM 迭代实时行
    iterated = Signal(int, float)
    #: 返回值
    succeeded = Signal(object)
    #: 异常对象（原样回传，保留 CoreUnavailableError 语义）
    failed = Signal(object)


class ComputeThread(QThread):
    """在后台线程执行一个 services 函数，并把回调转成 Qt 信号。"""

    def __init__(self, target: Callable[..., Any], *, args: Sequence[Any] = (),
                 kwargs: dict | None = None, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._target = target
        self._args = tuple(args)
        self._kwargs: dict[str, Any] = dict(kwargs or {})
        self._cancel = threading.Event()
        self.signals = TaskSignals()

    # ------------------------------------------------------------------ #
    def run(self) -> None:  # noqa: D102 - Qt 重写
        extras: dict[str, Any] = {
            "progress_cb": lambda msg, pct=None: self.signals.progressed.emit(
                str(msg), pct_to_percent(pct)),
            "on_iter": lambda gen, rwp: self.signals.iterated.emit(int(gen), float(rwp)),
            "cancel_cb": self._cancel.is_set,
        }
        try:
            value = call_with_extras(self._target, self._args, self._kwargs, extras)
        except Exception as exc:  # noqa: BLE001 —— 原样回传，主线程按类型决定文案
            self.signals.failed.emit(exc)
        else:
            self.signals.succeeded.emit(value)

    def request_cancel(self) -> None:
        """标记取消（仅当底层 core 接受 cancel_cb 时才真正生效）。"""
        self._cancel.set()

    @property
    def cancel_event(self) -> threading.Event:
        """供调用端判断是否已请求取消。"""
        return self._cancel


def run_busy_task(parent: QWidget | None, target: Callable[..., Any], *,
                  args: Sequence[Any] = (), kwargs: dict | None = None,
                  title: str | None = None, cancellable: bool = False,
                  degraded: bool = False, history: list | None = None,
                  on_success: Callable[[Any], None] | None = None,
                  on_error: Callable[[Exception], None] | None = None
                  ) -> ComputeThread:
    """前台弹出 BusyDialog + 后台跑 target，二者通过信号解耦。

    ``history`` 接收最后一条阶段文案（可选，便于测试断言）。
    返回已启动的线程对象（测试可用 wait() 等待结束）。
    """
    from rutana.gui.busy import BusyDialog

    dlg = BusyDialog(parent, title=title, cancellable=cancellable)
    dlg.set_degraded(degraded)
    thread = ComputeThread(target, args=args, kwargs=kwargs, parent=parent)

    def _on_progress(text: str, pct: int) -> None:
        if history is not None:
            history.append((text, pct))
        dlg.set_message(text, pct)

    thread.signals.progressed.connect(_on_progress)
    thread.signals.iterated.connect(dlg.set_iteration)
    thread.signals.succeeded.connect(dlg.finish)  # 先收对话框，再回调业务
    thread.signals.failed.connect(lambda exc: (dlg.finish(),
                                               on_error(exc) if on_error else None))

    def _on_success(value: Any) -> None:
        if on_success is not None:
            on_success(value)

    thread.signals.succeeded.connect(_on_success)
    if cancellable:
        dlg.canceled.connect(thread.request_cancel)
        dlg.canceled.connect(dlg.mark_canceling)

    thread.start()
    dlg.start_timer()
    dlg.exec()
    if thread.isRunning():  # 对话框被异常关闭时避免线程悬空
        thread.wait(5000)
    return thread
