@echo off
rem ---------------------------------------------------------------------
rem  Starts the whole local stack in two windows:
rem
rem    "TaxBriefing API"     backend on port 8000, restarts itself
rem    "TaxBriefing tunnel"  public address for the Vercel site
rem
rem  KEEP BOTH WINDOWS OPEN. Closing either one takes the site down.
rem  The tunnel window prints the public address - copy it from there.
rem
rem  Earlier this file ran both commands with nested quotes inside a
rem  single start line. cmd could not parse it - it printed a syntax
rem  error - and the backend never launched, so the tunnel came up with
rem  nothing behind it and every request returned 530.
rem  One window per job now.
rem
rem  ASCII only: cmd.exe reads .cmd files in the system code page (949 on
rem  Korean Windows), so non-ASCII text becomes garbage it tries to run.
rem ---------------------------------------------------------------------

title TaxBriefing launcher

start "TaxBriefing API" "C:\dev\taxbriefing\run-api.cmd"
start "TaxBriefing tunnel" "C:\dev\taxbriefing\run-tunnel.cmd"

echo Two windows were opened:
echo   - TaxBriefing API      (backend)
echo   - TaxBriefing tunnel   (public address)
echo.
echo Keep both open. The tunnel window shows the address to put in
echo Vercel as NEXT_PUBLIC_API_BASE, with /api/v1 on the end.
echo.
echo This launcher window can be closed.
ping -n 4 127.0.0.1 >nul
