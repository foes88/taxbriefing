@echo off
rem ---------------------------------------------------------------------
rem  Cloudflare quick tunnel for the local backend.
rem
rem  Exposes http://localhost:8000 to the internet so the Vercel site can
rem  reach it. Prints the public address and keeps running.
rem
rem  The address is RANDOM and changes every time this starts. When it
rem  changes, NEXT_PUBLIC_API_BASE on Vercel must be updated and the site
rem  redeployed. That is the price of hosting the backend on this PC.
rem
rem  ASCII only: cmd.exe reads .cmd files in the system code page (949 on
rem  Korean Windows), so non-ASCII text becomes garbage it tries to run.
rem ---------------------------------------------------------------------

title TaxBriefing tunnel

set "ROOT=C:\dev\taxbriefing\backend"
set "CF=C:\Program Files (x86)\cloudflared\cloudflared.exe"

if not exist "%CF%" (
  echo cloudflared not found at:
  echo   %CF%
  pause
  exit /b 1
)

echo Waiting for the backend on port 8000...
:wait
powershell -NoProfile -Command "try{ (Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 3) | Out-Null; exit 0 } catch { exit 1 }" >nul 2>&1
if errorlevel 1 (
  ping -n 3 127.0.0.1 >nul
  goto wait
)
echo Backend is up.
echo.

:loop
"%CF%" tunnel --url http://localhost:8000 --no-autoupdate
echo.
echo Tunnel stopped - restarting in 5s. The address will change.
ping -n 6 127.0.0.1 >nul
goto loop
