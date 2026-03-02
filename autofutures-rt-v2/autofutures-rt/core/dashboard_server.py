"""
core/dashboard_server.py — Web Dashboard Server

ทำงาน 2 อย่างพร้อมกัน:
  1. HTTP server → serve dashboard HTML (port 8080)
  2. WebSocket server → push real-time data ไป browser

เปิด browser แล้วไป: http://YOUR_EC2_IP:8080
"""
import asyncio
import json
import logging
import os
from http.server import BaseHTTPRequestHandler
from pathlib import Path

import websockets
from websockets.server import serve

logger = logging.getLogger(__name__)


class DashboardServer:
    def __init__(self, settings, bot):
        self.settings = settings
        self.bot      = bot
        self.clients: set = set()  # browser connections ทั้งหมด

        # Register ตัวเองเป็น callback ของ bot
        bot.register_dashboard_callback(self._broadcast)

        # Path ไปยัง HTML dashboard
        self.html_path = Path(__file__).parent.parent / "static" / "dashboard.html"

    async def start(self):
        """เริ่ม WebSocket server และ HTTP server พร้อมกัน"""
        host = self.settings.DASHBOARD_HOST
        ws_port   = self.settings.DASHBOARD_PORT       # 8080 — WebSocket
        http_port = self.settings.DASHBOARD_PORT + 1   # 8081 — HTTP (serve HTML)

        logger.info(f"📊 Dashboard WebSocket: ws://{host}:{ws_port}")
        logger.info(f"🌐 Dashboard HTTP:      http://{host}:{http_port}")

        await asyncio.gather(
            self._run_ws_server(host, ws_port),
            self._run_http_server(host, http_port),
        )

    # ──────────────────────────────────────────────────────
    # WEBSOCKET SERVER
    # ──────────────────────────────────────────────────────
    async def _run_ws_server(self, host: str, port: int):
        async with serve(self._handle_client, host, port, ping_interval=20):
            logger.info(f"✅ WS server running on {host}:{port}")
            await asyncio.Future()  # รันตลอดไป

    async def _handle_client(self, websocket):
        """จัดการ browser connection แต่ละราย"""
        self.clients.add(websocket)
        logger.info(f"Dashboard client connected ({len(self.clients)} total)")

        try:
            # ส่ง state ปัจจุบันให้ทันทีที่เชื่อมต่อ
            await websocket.send(json.dumps({"type": "full_state", **self.bot.get_state()}))

            # รอรับ command จาก browser (เช่น stop bot)
            async for raw in websocket:
                await self._handle_command(json.loads(raw))

        except websockets.ConnectionClosed:
            pass
        finally:
            self.clients.discard(websocket)
            logger.info(f"Dashboard client disconnected ({len(self.clients)} remaining)")

    async def _handle_command(self, cmd: dict):
        """รับคำสั่งจาก Dashboard browser"""
        action = cmd.get("action")
        logger.info(f"Dashboard command: {action}")

        if action == "stop_bot":
            self.bot.is_running = False
            self.bot.telegram.send("🛑 Bot stopped via Dashboard")

        elif action == "start_bot":
            self.bot.is_running = True
            self.bot.telegram.send("▶️ Bot started via Dashboard")

        elif action == "close_position":
            if self.bot.current_position:
                await asyncio.to_thread(
                    self.bot._close_position, "Manual close via Dashboard"
                )

        elif action == "ping":
            await self._broadcast({"type": "pong"})

    async def _broadcast(self, data: dict):
        """ส่งข้อมูลไปยัง browser ทุก tab ที่เปิดอยู่"""
        if not self.clients:
            return
        msg = json.dumps(data, default=str)
        disconnected = set()
        for ws in self.clients.copy():
            try:
                await ws.send(msg)
            except websockets.ConnectionClosed:
                disconnected.add(ws)
        self.clients -= disconnected

    # ──────────────────────────────────────────────────────
    # HTTP SERVER (serve dashboard.html)
    # ──────────────────────────────────────────────────────
    async def _run_http_server(self, host: str, port: int):
        """Simple HTTP server ให้ browser โหลด dashboard.html"""
        import http.server
        import threading

        html_path = self.html_path
        ws_port   = self.settings.DASHBOARD_PORT

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path in ("/", "/index.html"):
                    try:
                        content = html_path.read_bytes()
                        # แทนที่ WS_PORT placeholder ใน HTML
                        content = content.replace(b"__WS_PORT__", str(ws_port).encode())
                        self.send_response(200)
                        self.send_header("Content-Type", "text/html; charset=utf-8")
                        self.end_headers()
                        self.wfile.write(content)
                    except FileNotFoundError:
                        self.send_error(404, "dashboard.html not found")
                else:
                    self.send_error(404)

            def log_message(self, format, *args):
                pass  # suppress HTTP logs

        server = http.server.HTTPServer((host, port), Handler)
        loop   = asyncio.get_event_loop()
        await loop.run_in_executor(None, server.serve_forever)
