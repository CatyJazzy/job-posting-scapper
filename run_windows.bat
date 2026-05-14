@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 collect_notices.py --interactive
  goto done
)

where python >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  python collect_notices.py --interactive
  goto done
)

echo Python이 설치되어 있지 않습니다. Python 3을 설치한 뒤 다시 실행해주세요.

:done
echo.
pause
