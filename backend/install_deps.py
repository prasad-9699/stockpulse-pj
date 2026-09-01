import subprocess
import sys
import os

# Install backend dependencies
print("=== Installing Backend Dependencies ===")
subprocess.run([sys.executable, "-m", "pip", "install", 
    "fastapi", "uvicorn[standard]", "sqlalchemy", "pydantic", 
    "pydantic-settings", "python-dotenv", "httpx", "sse-starlette"],
    check=True)

print("\n=== Dependencies installed successfully! ===")
print("Now run: uvicorn app.main:app --reload")
