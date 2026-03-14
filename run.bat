@echo off
chcp 65001 >nul
echo ========================================
echo   Upbit Auto Trading Dashboard
echo ========================================
echo.

echo [1] 기존 프로세스 정리 중...
taskkill /F /IM streamlit.exe >nul 2>&1
taskkill /F /IM "streamlit.cmd" >nul 2>&1

REM 포트 8501 사용 중인 python 프로세스 종료
powershell -Command "Get-NetTCPConnection -LocalPort 8501 -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }"

timeout /t 2 /nobreak >nul

echo [2] Streamlit 시작 중...
echo.
streamlit run app.py --server.port 8501
pause
