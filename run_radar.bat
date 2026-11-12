@echo off
title ESP32-S3 Wi-Fi CSI Radar Monitor
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0radar_monitor.ps1"
pause
