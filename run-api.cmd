@echo off
rem ---------------------------------------------------------------------
rem  TaxBriefing backend supervisor.
rem
rem  Restarts uvicorn 5 seconds after it stops, for any reason.
rem  Temporary measure so the site stays up while this PC is on.
rem  Goes away once the backend moves to Render (see docs/DEPLOY.md).
rem
rem  To start it on every boot, put a shortcut to this file in:
rem      Win+R  ->  shell:startup
rem
rem  ASCII only, on purpose. cmd.exe reads .cmd files in the system code
rem  page (949 on Korean Windows), not UTF-8. Korean comments in this file
rem  turned into garbage bytes that cmd then tried to run as commands.
rem  All paths are absolute for the same class of reason: with relative
rem  paths the working directory depends on how the file was launched,
rem  and it failed silently when that differed.
rem ---------------------------------------------------------------------

title TaxBriefing API

set "ROOT=C:\dev\taxbriefing\backend"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "LOG=%ROOT%\api.log"

cd /d "%ROOT%"

echo TaxBriefing API - keep this window open.
echo Log: %LOG%
echo.

:loop
echo [%date% %time%] starting uvicorn>>"%LOG%"
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >>"%LOG%" 2>&1
echo [%date% %time%] stopped - restarting in 5s>>"%LOG%"
echo [%date% %time%] stopped - restarting in 5s
ping -n 6 127.0.0.1 >nul
goto loop
