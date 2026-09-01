@echo off
echo === Starting StockPulse Backend ===
cd /d c:\Users\zycus\Desktop\zycusprasad\backend
start "StockPulse Backend" cmd /k "uvicorn app.main:app --reload"

echo === Starting StockPulse Frontend ===
cd /d c:\Users\zycus\Desktop\zycusprasad\frontend
start "StockPulse Frontend" cmd /k "npm run dev"

echo.
echo Both servers starting in new windows!
echo Backend: http://localhost:8000/docs
echo Frontend: http://localhost:5173
