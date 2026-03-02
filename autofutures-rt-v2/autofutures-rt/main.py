"""
main.py — AutoFutures Real-time Bot
รัน: python main.py

สิ่งที่ทำงานพร้อมกัน (asyncio):
  1. WebSocket → รับ price/kline จาก Binance แบบ real-time
  2. Strategy Engine → วิเคราะห์ signal ทุก tick
  3. Order Manager → execute order ทันที
  4. Web Dashboard → ส่งข้อมูลไปยัง browser ผ่าน WebSocket
  5. Telegram → แจ้งเตือนทุก event
"""
import asyncio
import logging
from core.bot_realtime import RealtimeBot
from core.dashboard_server import DashboardServer
from utils.logger import setup_logger
from config.settings import Settings


async def main():
    logger = setup_logger()
    logger.info("🚀 AutoFutures REALTIME Bot starting...")

    settings = Settings()
    settings.validate()

    # สร้าง Bot และ Dashboard
    bot       = RealtimeBot(settings)
    dashboard = DashboardServer(settings, bot)

    # รันทั้งคู่พร้อมกัน
    await asyncio.gather(
        bot.start(),           # WebSocket bot loop
        dashboard.start(),     # Web dashboard server
    )


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n🛑 Bot stopped")
