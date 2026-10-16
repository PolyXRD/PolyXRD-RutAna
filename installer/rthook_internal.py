"""PyInstaller runtime_hook：内部评估版（单文件 exe，PolyXRD-RutAna.spec）。

在应用代码运行前把版次标识覆写为 internal；注册版（Setup 安装包，
PolyXRD-RutAna-Setup.spec）不加本 hook，保持默认 registered。
"""

import rutana.edition as _edition

_edition.EDITION = "internal"
_edition.IS_INTERNAL = True
