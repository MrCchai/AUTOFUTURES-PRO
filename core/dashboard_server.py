import asyncio, json, http.server, threading, websockets
from pathlib import Path
from websockets.server import serve

class DashboardServer:
    def __init__(self, settings, bot):
        self.settings = settings
        self.bot = bot
        self.clients = set()
        bot.register_callback(self._broadcast)
        self.html_path = Path(__file__).parent.parent / "static" / "dashboard.html"

    async def start(self):
        async with serve(self._handle, self.settings.DASHBOARD_HOST, self.settings.DASHBOARD_PORT):
            threading.Thread(target=self._run_http, daemon=True).start()
            await asyncio.Future()

    async def _handle(self, ws):
        self.clients.add(ws)
        try:
            await ws.send(json.dumps(self.bot.get_state(), default=str))
            async for m in ws: pass
        finally: self.clients.discard(ws)

    async def _broadcast(self, data):
        if self.clients: websockets.broadcast(self.clients, json.dumps(data, default=str))

    def _run_http(self):
        path = self.html_path
        class H(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(path.read_bytes())
            def log_message(self, *a): pass
        http.server.HTTPServer(("0.0.0.0", 8081), H).serve_forever()
