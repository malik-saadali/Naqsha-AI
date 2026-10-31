@echo off
title Naqsha AI
cd /d "%~dp0"
echo ============================================
echo   Naqsha AI - starting on http://localhost:8000
echo ============================================

where python >nul 2>nul
if errorlevel 1 (
  echo Python is not installed. Install it from https://www.python.org/downloads/ ^(tick "Add to PATH"^) and run this again.
  pause
  exit /b 1
)

if not exist .env (
  copy .env.example .env >nul
  echo.
  echo A settings file .env was created. Notepad will open:
  echo   paste your GROQ_API_KEY ^(free at console.groq.com^) and TELEGRAM_BOT_TOKEN ^(from @BotFather^)
  echo   then SAVE, close Notepad, and this window will continue.
  notepad .env
)

echo Installing packages (first time only takes a minute)...
python -m pip install -q -r requirements.txt

if not "%TELEGRAM_SKIP%"=="1" (
  findstr /r /c:"^TELEGRAM_BOT_TOKEN=..*" .env >nul && start "Naqsha Telegram bot" cmd /k "ping -n 9 127.0.0.1 >nul & python bot.py"
)

rem open the browser once the server has had a few seconds to start
start "" /b cmd /c "ping -n 6 127.0.0.1 >nul & start "" http://localhost:8000"
echo Server window: keep it open. Close it (or press Ctrl+C) to stop Naqsha AI.
python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
pause
