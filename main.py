import asyncio, logging
from config.settings import Settings
from core.bot_realtime import RealtimeBot
from core.dashboard_server import DashboardServer

logging.basicConfig(level=logging.INFO)

async def main():
    settings = Settings()
    bot = RealtimeBot(settings)
    
    # Dashboard Server (Reuse logic from V12)
    from core.dashboard_server import DashboardServer
    dashboard = DashboardServer(settings, bot)
    
    await asyncio.gather(
        bot.start(),
        dashboard.start()
    )

if __name__ == "__main__":
    asyncio.run(main())
