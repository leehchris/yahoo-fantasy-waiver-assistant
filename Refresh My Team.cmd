@echo off
setlocal
pushd "%~dp0"
".venv\Scripts\python.exe" -m yahoo_waiver_assistant refresh --open
if errorlevel 1 pause
popd
