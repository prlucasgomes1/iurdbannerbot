@echo off
echo ================================
echo   Bot Universal Long Branch
echo ================================
echo.
echo Instalando dependencias (so na primeira vez)...
pip install python-telegram-bot==20.7 Pillow==10.2.0 rembg==2.0.57 numpy==1.26.4 onnxruntime==1.17.1

echo.
echo Iniciando o bot...
set TELEGRAM_BOT_TOKEN=8900059263:AAGBgtwiZtDEmISxeLkNRHyb0ef3PMh-YYs
python bot.py

echo.
echo Bot encerrado. Pressione qualquer tecla para fechar.
pause
