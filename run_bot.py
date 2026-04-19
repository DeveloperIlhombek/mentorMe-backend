"""
run_bot.py — Bot polling rejimida ishga tushirish (development uchun).

Ishlatish:
    cd backend
    python run_bot.py

Production (webhook rejimi):
    - BOT_WEBHOOK_URL ni .env ga qo'shing (ngrok yoki real domain)
    - FastAPI ishga tushirilganda webhook avtomatik o'rnatiladi
    - uvicorn app.main:app --reload
"""
import asyncio
import logging
import sys
import os

# Backend root'ni Python path'ga qo'shish
sys.path.insert(0, os.path.dirname(__file__))

from bot.main import main

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    print("🤖 EduSaaS Bot — polling rejimi")
    print("   Token:", os.getenv("BOT_TOKEN", "")[:20] + "...")
    print("   Ctrl+C — to'xtatish")
    print()
    asyncio.run(main())
