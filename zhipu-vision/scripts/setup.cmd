@echo off
setlocal EnableExtensions

rem One-click API key setup for Windows (same interpreter probing as analyze_image.cmd).
rem Order: %ZHIPU_PYTHON% -> python/python3/py -3 -> common install dirs -> Codex runtime.

if defined ZHIPU_PYTHON (
  call :probe "%ZHIPU_PYTHON%" ""
  if defined PY_EXE goto run
  echo [zhipu-vision] ERROR: ZHIPU_PYTHON is set but is not a usable Python interpreter.
  exit /b 1
)

call :probe "python" ""
if defined PY_EXE goto run

call :probe "python3" ""
if defined PY_EXE goto run

call :probe "py" "-3"
if defined PY_EXE goto run

for /d %%D in ("C:\Python3*") do (
  if not defined PY_EXE call :probe "%%~D\python.exe" ""
)
for /d %%D in ("%LOCALAPPDATA%\Programs\Python\Python3*") do (
  if not defined PY_EXE call :probe "%%~D\python.exe" ""
)
for /d %%D in ("%USERPROFILE%\.cache\codex-runtimes\*") do (
  if not defined PY_EXE call :probe "%%~D\dependencies\python\python.exe" ""
)

if defined PY_EXE goto run

echo [zhipu-vision] ERROR: no usable Python 3.10+ interpreter found.
echo Install Python 3.10+ or set ZHIPU_PYTHON to the interpreter path.
exit /b 1

:run
%PY_EXE% %PY_ARGS% "%~dp0setup.py" %*
exit /b %errorlevel%

:probe
set "cand=%~1"
set "extra=%~2"
set "PY_EXE="
"%cand%" %extra% -c "import sys" >nul 2>nul
if not errorlevel 1 (
  set "PY_EXE=%cand%"
  set "PY_ARGS=%extra%"
)
exit /b 0
