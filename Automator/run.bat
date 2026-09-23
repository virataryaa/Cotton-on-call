@echo off
setlocal EnableDelayedExpansion
set REPO=C:\Users\virat.arya\ETG\SoftsDatabase - Documents\Database\Hardmine\Fundamental\Cotton_Calls
set LOG="%REPO%\Automator\run_log.txt"
set INGEST_STATUS=ok
set GIT_STATUS=skipped

:: Prevent Git Credential Manager from showing an interactive dialog in unattended runs.
:: If credentials are cached it pushes silently; if not, it fails immediately instead of hanging.
set GCM_INTERACTIVE=never
set GIT_TERMINAL_PROMPT=0
echo. >> %LOG%
echo ============================= >> %LOG%
echo Run started: %date% %time% >> %LOG%
echo ============================= >> %LOG%

:: Step 1 - Ingest new Cotton On-Call reports (also runs the data health check)
echo [1] Running ingest_coc.py... >> %LOG%
python "%REPO%\Code\ingest_coc.py" >> %LOG% 2>&1

if %ERRORLEVEL% NEQ 0 (
    echo ERROR: ingest_coc.py failed >> %LOG%
    set INGEST_STATUS=error
    goto notify
)

:: Step 2 - Push updated database to GitHub
echo [2] Pushing to GitHub... >> %LOG%
cd /d "%REPO%"
git add "Database\Cotton_On_Call_Database.csv" >> %LOG% 2>&1
git diff --cached --quiet
if %ERRORLEVEL% NEQ 0 (
    git commit -m "Auto update: Cotton On-Call %date%" >> %LOG% 2>&1
    git push >> %LOG% 2>&1
    if !ERRORLEVEL! EQU 0 (
        set GIT_STATUS=pushed
        echo Git push done. >> %LOG%
    ) else (
        set GIT_STATUS=failed
        echo ERROR: git push failed >> %LOG%
    )
) else (
    echo No changes to commit. >> %LOG%
    set GIT_STATUS=skipped
)

:notify
echo [3] Sending email notification... >> %LOG%
python "%REPO%\Automator\notify.py" %INGEST_STATUS% %GIT_STATUS% >> %LOG% 2>&1

echo Run finished: %date% %time% >> %LOG%
