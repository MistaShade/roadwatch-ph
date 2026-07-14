@echo off
cd /d "%~dp0"
echo.
echo  RoadWatch PH - starting local server...
echo  Open http://localhost:8080 in your browser
echo  Press Ctrl+C to stop
echo.
start "" "http://localhost:8080"
python -m http.server 8080
