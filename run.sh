#!/bin/bash
# nanobot 快速启动脚本

source venv/Scripts/activate
python -m nanobot.cli.commands "$@"
