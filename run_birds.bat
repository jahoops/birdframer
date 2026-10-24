@echo off
cd /d "%~dp0"
call .venv\Scripts\activate
python pick_best_bird_frames.py
