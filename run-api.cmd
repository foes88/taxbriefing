@echo off
rem TaxBriefing 백엔드 감시 실행기.
rem
rem uvicorn 이 어떤 이유로든 멈추면 5초 뒤 다시 띄운다.
rem 이 PC 가 켜져 있는 동안 사이트가 살아 있게 하는 임시 장치이며,
rem Render 로 옮기면 필요 없어진다 (docs/DEPLOY.md).
rem
rem 부팅할 때마다 뜨게 하려면 이 파일의 바로가기를 아래에 둔다.
rem   Win+R  →  shell:startup
rem
rem 경로는 전부 절대경로다. 상대경로로 두면 어떤 방식으로 띄웠느냐에 따라
rem 작업 디렉터리가 달라져 조용히 실패한다. 실제로 그렇게 실패했다 —
rem cmd 는 살아 있는데 python 이 뜨지 않았고, 로그가 없어 이유를 알 수 없었다.

title TaxBriefing API

set "ROOT=C:\dev\taxbriefing\backend"
set "PY=%ROOT%\.venv\Scripts\python.exe"
set "LOG=%ROOT%\api.log"

cd /d "%ROOT%"

:loop
echo [%date% %time%] uvicorn 기동>>"%LOG%"
"%PY%" -m uvicorn app.main:app --host 0.0.0.0 --port 8000 >>"%LOG%" 2>&1
echo [%date% %time%] 종료됨 - 5초 후 재시작>>"%LOG%"
ping -n 6 127.0.0.1 >nul
goto loop
