# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（PolyXRD 家族模板，参照 PolyXRD-SynthPattern spec）。

单文件（onefile）免安装 exe：
- 入口 rutana/gui/__main__.py（python -m rutana.gui 等价）；
- datas 携带 resources/（品牌资产）与 rutana/data/（内置 CIF，B 法用；
  目录尚未就绪时自动跳过，待 T3.1 落库后打包即含）；
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
        "rutana.core.peakmeasure",
        "rutana.core.plot",
        "rutana.core.smooth",
        "rutana.core.profile.cif",
        "rutana.core.profile.forward",
        "rutana.core.profile.shape",
        "rutana.core.profile.struct",
        "rutana.core.refine.linear",
        "rutana.core.refine.lm",
        "rutana.core.refine.nonlinear",
        "rutana.core.refine.qpa",
        "rutana.core.refine.rfactors",
        "rutana.core.refine.realdata",
        "rutana.core.kalpha2",
        "rutana.gui.resources",
        "rutana.gui.services",
        "rutana.gui.canvas",
        "rutana.gui.panels",
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
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
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
