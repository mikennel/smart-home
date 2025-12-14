@echo off
cd /d C:\Users\Michael\Documents\Code\smart-home\status_light
start /min cmd /c "set PYTHONIOENCODING=utf-8 && C:\Users\Michael\Documents\Code\smart-home\.venv\Scripts\python.exe -m uvicorn app:app --host 0.0.0.0 --port 5005 > status_light.log 2>&1"
