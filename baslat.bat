@echo off
REM Hoca'yı başlatır. İlk çalıştırmada sanal ortamı kurar.
cd /d "%~dp0"
where python >nul 2>nul || (
  echo Python bulunamadi. https://www.python.org adresinden Python 3.10 veya ustunu kur
  echo ve kurulumda "Add python.exe to PATH" kutusunu isaretle.
  pause
  exit /b 1
)
if not exist .venv (
  echo Python ortami kuruluyor...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
echo.
echo Sinif hazir: tarayicida http://localhost:8765 adresini ac
echo Kapatmak icin bu pencerede Ctrl+C
echo.
start "" http://localhost:8765
.venv\Scripts\python -m uvicorn server.main:app --port 8765
