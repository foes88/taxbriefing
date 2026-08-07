@echo off
rem TaxBriefing 백엔드 감시 실행기.
rem
rem uvicorn 이 어떤 이유로든 멈추면 5초 뒤 다시 띄운다.
rem 이 PC 가 켜져 있는 동안 사이트가 살아 있게 하는 임시 장치이며,
rem Render 로 옮기면 필요 없어진다 (docs/DEPLOY.md).
rem
rem 부팅할 때마다 뜨게 하려면 이 파일의 바로가기를 아래에 둔다.
rem   Win+R  →  shell:startup

title TaxBriefing API
cd /d "%~dp0backend"

:loop
echo [%date% %time%] uvicorn 기동
".venv\Scripts\python.exe" -m uvicorn app.main:app --host 0.0.0.0 --port 8000
echo [%date% %time%] 종료됨 - 5초 후 재시작
timeout /t 5 /nobreak >nul
goto loop
