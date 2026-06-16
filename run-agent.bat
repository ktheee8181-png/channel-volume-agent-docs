@echo off
setlocal

set "PYTHON_EXE=C:\Users\user\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
set "SCRIPT_DIR=%~dp0"

if not exist "%PYTHON_EXE%" (
  echo Python runtime not found.
  exit /b 1
)

"%PYTHON_EXE%" "%SCRIPT_DIR%main.py" %*
