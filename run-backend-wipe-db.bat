@echo off
REM Rebuilds and starts the backend stack from a clean state.
REM WARNING: This removes Docker volumes and wipes database data.
REM WARNING: This also removes stopped Docker containers via `docker system prune -f`.

cd /d "%~dp0"

docker compose down -v
docker system prune -f
powershell -NoProfile -Command "Get-ChildItem -Path services -Filter __pycache__ -Recurse -Directory | Remove-Item -Recurse -Force"
docker compose build --no-cache
docker compose up
