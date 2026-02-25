@echo off
REM nanobot 快速启动脚本

call venv\Scripts\activate.bat
python -m nanobot.cli.commands %*
