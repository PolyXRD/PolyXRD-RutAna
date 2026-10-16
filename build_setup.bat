@echo off
REM Build PolyXRD RutAna REGISTERED EDITION (v1.5.0+):
REM   1. PyInstaller onedir build from PolyXRD-RutAna-Setup.spec
REM      -> dist\PolyXRD-RutAna\PolyXRD-RutAna.exe (+ support files)
REM   2. Inno Setup installer from installer\PolyXRD-RutAna.iss
REM      -> dist\PolyXRD-RutAna-vX.Y.Z-Setup.exe
REM Version is read from rutana/version.py (single source of truth).
REM NOTE: keep comments ASCII-only to stay safe under any cmd codepage.
cd /d %~dp0
set PY=D:\Project\XRD\python310\python.exe
if not exist "%PY%" set PY=python
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=ISCC.exe

REM Read version from source
for /f "delims=" %%v in ('"%PY%" -c "from rutana.version import __version__; print(__version__)"') do set VER=%%v

echo [1/2] Building onedir (registered edition) v%VER% ...
"%PY%" -m PyInstaller --noconfirm --clean PolyXRD-RutAna-Setup.spec
if errorlevel 1 goto :fail
if not exist "dist\PolyXRD-RutAna\PolyXRD-RutAna.exe" goto :fail

echo [2/2] Building installer with Inno Setup ...
"%ISCC%" /DAPP_VER=v%VER% installer\PolyXRD-RutAna.iss
if errorlevel 1 goto :fail

echo.
echo Done:
echo   dist\PolyXRD-RutAna\PolyXRD-RutAna.exe          (onedir, registered edition)
echo   dist\PolyXRD-RutAna-v%VER%-Setup.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
