# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（PolyXRD 家族模板，参照 PolyXRD-SynthPattern spec）。

单文件（onefile）免安装 exe：
- 入口 rutana/gui/__main__.py（python -m rutana.gui 等价）；
- datas 携带 resources/（品牌资产）与 rutana/data/（内置 CIF，B 法用；
  目录尚未就绪时自动跳过，待 T3.1 落库后打包即含）；
- v1.4.0：bootloader Splash 启动画面（resources/splash-screen.png），
  onefile 解压阶段即显示，主窗口就绪后由 __main__._close_boot_splash 关闭；
- 版本号从 rutana/version.py 读取，exe 名与 build_exe.bat 的副本逻辑对应。
"""

import re
from pathlib import Path

_ver = re.search(
    r'__version__\s*=\s*"([^"]+)"',
    Path("rutana/version.py").read_text(encoding="utf-8"),
).group(1)

datas = [("resources", "resources")]
if Path("rutana/data").is_dir():
    datas.append(("rutana/data", "rutana/data"))

a = Analysis(
    ["rutana/gui/__main__.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "rutana",
        "rutana.version",
        "rutana.i18n",
        "rutana.i18n.i18n_manager",
        "rutana.i18n.translations.zh_CN",
        "rutana.i18n.translations.en_US",
        "rutana.i18n.translations.ja_JP",
        # core 算法模块（P1-1：services 已改静态 import，这里再显式补全双保险；
        # 与 rutana/core 下真实模块逐一核对：7 顶层 + 4 profile + 5 refine）
        "rutana.core.background",
        "rutana.core.dtypes",
        "rutana.core.method_a",
        "rutana.core.patterns",
        # v1.6.0：多格式读谱器 vendor 副本（新增模块显式收集）
        "rutana.core.vendor.model",
        "rutana.core.vendor.raw_formats",
        "rutana.core.vendor.text_formats",
        "rutana.core.peakmeasure",
        # v1.7.0：主峰参数表（带 hkl 的反射枚举 + 谢乐晶粒度）
        "rutana.core.phasepeak",
        "rutana.core.plot",
        "rutana.core.smooth",
        "rutana.core.profile.cif",
        "rutana.core.profile.forward",
        "rutana.core.profile.shape",
        "rutana.core.profile.struct",
        "rutana.core.profile.reflections",
        "rutana.core.refine.linear",
        "rutana.core.refine.lm",
        "rutana.core.refine.nonlinear",
        "rutana.core.refine.qpa",
        "rutana.core.refine.rfactors",
        "rutana.core.refine.realdata",
        "rutana.core.kalpha2",
        "rutana.gui.resources",
        "rutana.gui.services",
        # v1.2.0 新增：批量服务层（GUI 静态 import rutana.gui.batch，
        # 这里显式补全，保证 PyInstaller 静态分析可追踪）
        "rutana.gui.batch",
        "rutana.gui.canvas",
        # v1.7.0：谱图下方主峰参数表
        "rutana.gui.peaks_panel",
        "rutana.gui.panels",
        # v1.2.0：B 法面板拆出（同 ≤400 行约束）
        "rutana.gui.panels_b",
        "rutana.gui.dialogs",
        "rutana.gui.report",
        "rutana.gui.exports",
        "rutana.gui.main_window",
        # v1.0.0 新增：后台线程/忙窗/任务编排/结果卡/K 说明与标定向导
        "rutana.gui.workers",
        "rutana.gui.busy",
        "rutana.gui.tasks",
        "rutana.gui.tabs",
        "rutana.gui.resultcard",
        "rutana.gui.corenodes",
        "rutana.gui.calibcanvas",
        "rutana.gui.calibtable",
        "rutana.gui.calibrecord",
        "rutana.gui.khelp",
        "rutana.gui.kwizard",
    ],
    hookspath=[],
    hooksconfig={},
    # v1.5.0：内部评估版 —— 运行时把版次覆写为 internal（状态栏显示
    # 「内部评估版本」），并彻底排除注册模块（exe 不含注册机制）
    runtime_hooks=["installer/rthook_internal.py"],
    excludes=["rutana.gui.registration"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# v1.4.0：bootloader 启动画面 —— onefile 解压阶段（数秒）即显示品牌图，
# 解决 exe 冷启动 >6s 无窗口问题。图上已烙品牌+版本号（v1.4.0），故不
# 附加文本；主窗口 show 后由 rutana/gui/__main__.py 的 _close_boot_splash
# 关闭（pyi_splash.close()），与 QSplashScreen（上层同图）视觉连续。
splash = Splash(
    "resources/splash-screen.png",
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    min_font_color="white",
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    splash,
    # v1.4.0：bootloader splash 的运行时依赖（tcl86t.dll/tk86t.dll 及
    # _tcl_data/_tk_data 脚本树）。PyInstaller 官方模板中 splash.binaries
    # 必须作为独立 TOC 参数传入 EXE，否则 onefile 解压期找不到 Tcl/Tk，
    # 启动画面静默失败。
    splash.binaries,
    [],
    name=f"PolyXRD-RutAna-v{_ver}",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["resources/app-icon.ico"],
)
