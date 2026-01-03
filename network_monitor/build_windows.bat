@echo off
setlocal

set PYTHON=python
if not "%~1"=="" set PYTHON=%~1

%PYTHON% -m pip install -r requirements.txt || exit /b 1
%PYTHON% -m pip install pyinstaller || exit /b 1

%PYTHON% -m PyInstaller --clean --noconfirm netmon.spec || exit /b 1

echo.
echo Built: dist\NetMonTUI.exe

endlocal

