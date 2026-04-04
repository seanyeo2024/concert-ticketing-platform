@echo off
REM Starts the static frontend at http://localhost:8080/
REM Run this from anywhere; the script jumps to the repo's frontend folder.

cd /d "%~dp0frontend"
python -m http.server 8080
