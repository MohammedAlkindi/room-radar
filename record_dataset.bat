@echo off
title ESP32-S3 Wi-Fi CSI Dataset Ingestion
cd /d "%~dp0"
set /p LABEL=Enter activity label (e.g. sitting, walking, vacant, typing): 
python python_dsp\dataset_recorder.py --port COM11 --label %LABEL% --duration 60
pause
