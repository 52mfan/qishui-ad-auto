@echo off
chcp 65001 >nul
title 汽水音乐自动看广告
cd /d "%~dp0"
where python >nul 2>nul
if errorlevel 1 (
    echo 未找到 python，请先安装 Python 并加入 PATH
    pause
    exit /b 1
)
python qishui_ad_gui.py
pause
