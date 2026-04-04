@echo off
REM Rebuilds and starts the backend stack.
REM WARNING: This removes stopped Docker containers via `docker system prune -f`.
REM This does NOT wipe named volumes / database data.

cd /d "%~dp0"

docker compose down
docker system prune -f
powershell -NoProfile -Command "Get-ChildItem -Path services -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force"
docker compose build --no-cache
docker compose up
