@echo off
echo === Installing Backend Dependencies ===
cd /d c:\Users\zycus\Desktop\zycusprasad\backend
pip install fastapi "uvicorn[standard]" sqlalchemy pydantic pydantic-settings python-dotenv httpx sse-starlette
echo.
echo === Installing Frontend Dependencies ===
cd /d c:\Users\zycus\Desktop\zycusprasad\frontend
call npm install
echo.
echo === DONE! ===
echo.
echo To start backend: cd backend ^& uvicorn app.main:app --reload
echo To start frontend: cd frontend ^& npm run dev
pause
