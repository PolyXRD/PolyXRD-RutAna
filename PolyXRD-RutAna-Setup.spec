# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置 —— 注册版（Setup 安装包用 onedir，v1.5.0 新增）。

与 PolyXRD-RutAna.spec（内部评估版 onefile）的差异：
- onedir 目录版（COLLECT），供 Inno Setup 打成安装包（installer/PolyXRD-RutAna.iss）；
- 含注册机制模块 rutana.gui.registration（hiddenimports 显式补全）；
- 不加 runtime_hook：版次保持 rutana/edition.py 默认 registered；
- exe 名不带版本号（dist/PolyXRD-RutAna/PolyXRD-RutAna.exe），
  版本号烙在安装包文件名与 version.py 里；
- bootloader Splash 启动画面与内部版一致保留。
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
        "rutana.edition",
        "rutana.i18n",
        "rutana.i18n.i18n_manager",
        "rutana.i18n.translations.zh_CN",
        "rutana.i18n.translations.en_US",
        "rutana.i18n.translations.ja_JP",
        # core 算法模块（与内部版 spec 保持一致：7 顶层 + 4 profile + 5 refine）
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
        "rutana.gui.batch",
        "rutana.gui.canvas",
        "rutana.gui.panels",
        "rutana.gui.panels_b",
        "rutana.gui.dialogs",
        "rutana.gui.report",
        "rutana.gui.exports",
        "rutana.gui.main_window",
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
        # v1.5.0：注册机制（注册版必含；内部评估版 spec excludes 排除）
        "rutana.gui.registration",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# bootloader 启动画面：与内部版一致（图已烙品牌+版本号，不附加文本）。
# onedir 模板：EXE 只挂 splash 对象；splash.binaries 归入 COLLECT。
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
    splash,
    [],
    exclude_binaries=True,
    name="PolyXRD-RutAna",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=["resources/app-icon.ico"],
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="PolyXRD-RutAna",
)
