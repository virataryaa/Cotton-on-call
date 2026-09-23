@echo off
setlocal
cd /d "%~dp0..\Code"
python ingest_coc.py >> "%~dp0..\Automator\coc_update.log" 2>&1
endlocal
