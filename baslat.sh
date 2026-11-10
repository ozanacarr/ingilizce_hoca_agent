#!/usr/bin/env bash
# Hoca'yı macOS / Linux'ta başlatır. İlk çalıştırmada Python ortamını kurar.
#   chmod +x baslat.sh && ./baslat.sh
set -e
cd "$(dirname "$0")"
PY=$(command -v python3 || command -v python)
if [ -z "$PY" ]; then
  echo "Python bulunamadi. https://www.python.org adresinden Python 3.10 veya ustunu kur."
  exit 1
fi
if [ ! -d .venv ]; then
  echo "Python ortami kuruluyor..."
  "$PY" -m venv .venv
  .venv/bin/python -m pip install -r requirements.txt
fi
echo
echo "Sinif hazir: tarayicida http://localhost:8765 adresini ac (kapatmak icin Ctrl+C)"
echo
( sleep 2; (open http://localhost:8765 || xdg-open http://localhost:8765) >/dev/null 2>&1 ) &
exec .venv/bin/python -m uvicorn server.main:app --port 8765
