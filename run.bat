@echo off
python -m pip install -r requirements.txt
if not exist .env (
  copy .env.example .env
  echo.
  echo .env created. Open it and paste your MongoDB Atlas MONGO_URI.
  pause
  exit /b
)
python app.py
pause
