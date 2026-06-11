@echo off
title SOC Automation - HUE
cd /d E:\soc-hue
call venv\Scripts\activate

echo ========================================
echo  SOC Alert Automation - Chi nhanh HUE
echo ========================================
echo.
echo [1/2] Khoi dong Streamlit App...
start "SOC App" cmd /k "cd /d E:\soc-hue && venv\Scripts\activate && streamlit run app.py"

timeout /t 3 /nobreak >nul

echo [2/2] Khoi dong Scheduler + Watchdog...
start "SOC Watchdog" cmd /k "cd /d E:\soc-hue && venv\Scripts\activate && python watchdog.py"

echo.
echo Tat ca da khoi dong!
echo - App: http://localhost:8501
echo - Watchdog tu dong giam sat va restart scheduler neu crash
echo.