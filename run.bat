@echo off
cd /d "%~dp0"
echo Starting India Tourism Recommender on http://localhost:8000
python -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
