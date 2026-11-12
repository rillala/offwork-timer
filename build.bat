@echo off
REM 安裝相依套件並打包成單一 exe（輸出在 dist\OffworkTimer.exe）
py -m pip install -r requirements.txt pyinstaller
py -m PyInstaller --noconfirm --onefile --windowed --name OffworkTimer app.py
echo.
echo 完成：dist\OffworkTimer.exe
pause
