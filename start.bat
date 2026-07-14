@echo off
cd /d "%~dp0"
echo.
echo  RoadWatch PH
echo  ============
echo  Web UI:  http://localhost:8090
echo  API:     http://localhost:5000
echo.
echo  Keep both windows open while using the app.
echo.

start "RoadWatch API" cmd /k "cd /d %~dp0 && python api.py"
timeout /t 2 /nobreak >nul
start "RoadWatch Web" cmd /k "cd /d %~dp0\web && python -m http.server 8090"
timeout /t 2 /nobreak >nul
start "" "http://localhost:8090"
