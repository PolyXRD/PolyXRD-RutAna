@echo off
REM 打包 PolyXRD RutAna 为【单文件】免安装 exe（依赖 PySide6/numpy/scipy/matplotlib，
REM 已预装于 D:\Project\XRD\python310）。家族命名习惯与 PolyXRD-SynthPattern 一致：
REM 产物（单文件，拷贝即用）：
REM   dist\PolyXRD-RutAna-vX.Y.Z.exe   <- 带版本号
REM   dist\PolyXRD-RutAna.exe          <- 固定名副本（GitHub Release 资产名）
REM 版本号由本脚本从 rutana/version.py 读取，spec 内 exe 名同步使用该版本。
cd /d %~dp0
set PY=D:\Project\XRD\python310\python.exe
if not exist "%PY%" set PY=python

REM 从源码读取版本号（避免人工改两处）
for /f "delims=" %%v in ('"%PY%" -c "from rutana.version import __version__; print(__version__)"') do set VER=%%v

echo Building PolyXRD RutAna v%VER% ...
"%PY%" -m PyInstaller --noconfirm --clean PolyXRD-RutAna.spec

if exist "dist\PolyXRD-RutAna-v%VER%.exe" copy /Y "dist\PolyXRD-RutAna-v%VER%.exe" "dist\PolyXRD-RutAna.exe"
echo.
echo 完成:
echo   dist\PolyXRD-RutAna-v%VER%.exe
if exist "dist\PolyXRD-RutAna.exe" echo   dist\PolyXRD-RutAna.exe
