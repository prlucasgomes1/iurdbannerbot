#!/bin/bash
cd "$(dirname "$0")"

echo "================================"
echo "  Bot Universal Long Branch"
echo "================================"
echo ""
echo "Instalando dependencias (so na primeira vez)..."
pip3 install "python-telegram-bot>=20.7" "Pillow>=10.3.0" "numpy>=1.26" "requests>=2.31"

echo ""
echo "Iniciando o bot..."
export TELEGRAM_BOT_TOKEN="8900059263:AAGBgtwiZtDEmISxeLkNRHyb0ef3PMh-YYs"
export REMOVEBG_API_KEY="bMLLmHdjuQWw3Vnvuy1785Bm"
python3 bot.py

echo ""
echo "Bot encerrado."
