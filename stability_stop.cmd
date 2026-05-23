@echo off
setlocal
chcp 65001>nul
set "PYTHONIOENCODING=UTF-8"
set "SCRIPT_DIR=%~dp0"
if not defined PYTHON_EXE set "PYTHON_EXE=python"
"%PYTHON_EXE%" "%SCRIPT_DIR%scripts\x_monitorplus_stability.py" --python-exe "%PYTHON_EXE%" safe-stop %*

