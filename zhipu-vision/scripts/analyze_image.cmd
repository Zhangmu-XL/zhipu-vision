@echo off
setlocal EnableExtensions

rem Windows launcher for analyze_image.py (portable; no machine-specific paths).
rem Python resolution order:
rem   1. %ZHIPU_PYTHON% - explicit user override (absolute path to a real interpreter)
rem   2. python / python3 / py -3 on PATH (validated: Store stub exits 9009 and is skipped)
rem   3. common install dirs: C:\Python3*, %%LOCALAPPDATA%%\Programs\Python\Python3*
rem   4. Codex desktop bundled runtime: %%USERPROFILE%%\.cache\codex-runtimes\*
rem ASCII-only messages to avoid codepage issues in cmd.

if defined ZHIPU_PYTHON (
  call :probe "%ZHIPU_PYTHON%" ""
  if defined PY_EXE goto run
  echo [zhipu-vision] ERROR: ZHIPU_PYTHON is set but is not a usable Python 3.10+ interpreter.
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
echo Install Python 3.10+, add it to PATH, or set ZHIPU_PYTHON to the interpreter path.
exit /b 1

:run
%PY_EXE% %PY_ARGS% "%~dp0analyze_image.py" %*
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
