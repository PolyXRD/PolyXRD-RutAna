"""资源路径定位：开发态用 ``<root>/resources``，PyInstaller 打包态用 ``sys._MEIPASS``。

所有 GUI 代码获取图标/启动图/内置 CIF 等静态资源都必须经由本模块，
使同一份代码在源码运行与 onefile 打包两种形态下都能正确定位。
"""

from __future__ import annotations

import sys
from pathlib import Path


def app_root() -> Path:
    """项目根目录（开发态）。rutana/gui/resources.py -> 根目录上溯三级。"""
    return Path(__file__).resolve().parent.parent.parent


def _base() -> Path:
    """资源基目录：打包态为解压目录 sys._MEIPASS，开发态为项目根目录。"""
    meipass = getattr(sys, "_MEIPASS", None)
    if getattr(sys, "frozen", False) and meipass:
        return Path(meipass)
    return app_root()


def resources_dir() -> Path:
    """品牌资源目录（build_artwork.py 的产物）。"""
    return _base() / "resources"


def resource_path(name: str) -> Path:
    """返回 resources/ 下指定文件名的路径。"""
    return resources_dir() / name


def data_dir() -> Path:
    """内置 CIF 数据目录（rutana/data，B 法用）。"""
    return _base() / "rutana" / "data"


def builtin_cif_path(phase: str) -> Path:
    """返回内置物相 CIF 路径；phase 取 "anatase" 或 "rutile"。"""
    return data_dir() / f"{phase}.cif"
