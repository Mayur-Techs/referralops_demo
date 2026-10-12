@echo off
setlocal
if not exist .env copy .env.example .env >nul
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
endlocal
