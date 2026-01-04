@echo off
setlocal enabledelayedexpansion

REM Build a standalone EXE with PyInstaller (Windows).

if "%PYTHON%"=="" set PYTHON=py

echo Creating venv...
%PYTHON% -m venv .venv || exit /b 1

echo Activating venv...
call .venv\Scripts\activate.bat || exit /b 1

echo Installing runtime deps...
pip install -r controller_turbo_windows\requirements.txt || exit /b 1

echo Installing build deps...
pip install -r controller_turbo_windows\requirements-build.txt || exit /b 1

echo Building exe with PyInstaller...
pyinstaller --noconfirm --clean --onefile --name turbo_pad_win --hidden-import inputs --hidden-import vgamepad controller_turbo_windows\main.py || exit /b 1

echo.
echo Built: dist\turbo_pad_win.exe

endlocal

