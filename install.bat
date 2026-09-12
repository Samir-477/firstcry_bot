@echo off
REM Clone-and-run setup for Windows.
cd /d "%~dp0"

echo ==^> Creating virtualenv
python -m venv venv
venv\Scripts\python.exe -m pip install --quiet --upgrade pip
venv\Scripts\python.exe -m pip install --quiet -r requirements.txt

if not exist ".env" (
    echo.
    echo     No .env found. Copy .env.example to .env and fill it in,
    echo     or run:  venv\Scripts\python.exe setup_telegram.py
    pause
    exit /b 1
)

echo.
echo ==^> Checking your FirstCry session
venv\Scripts\python.exe check_session.py
if errorlevel 1 (
    echo.
    echo     Session has expired. Run:  venv\Scripts\python.exe import_cookies.py
    pause
    exit /b 1
)

echo.
echo ==^> Ready. Start the bots with:
echo       venv\Scripts\python.exe run_all.py
pause
