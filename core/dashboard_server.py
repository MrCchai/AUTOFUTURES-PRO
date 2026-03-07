import asyncio, json, logging, http.server, threading
from pathlib import Path
from urllib.parse import urlparse, parse_qs

logger = logging.getLogger(__name__)

class DashboardServer:
    def __init__(self, settings, bot):
        self.settings = settings
        self.bot = bot
        self.html_path = Path(__file__).parent.parent / 'static' / 'dashboard.html'

    async def start(self):
        host = '0.0.0.0'
        port = 8080
        logger.info('Starting Professional Dashboard on Port ' + str(port))
        threading.Thread(target=self._run_http, args=(host, port), daemon=True).start()
        await asyncio.Future()

    def _run_http(self, host, port):
        bot = self.bot
        html_path = self.html_path
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                parsed_path = urlparse(self.path)
                if parsed_path.path == '/api/data':
                    params = parse_qs(parsed_path.query)
                    symbol = params.get('symbol', [None])[0]
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    try:
                        self.wfile.write(json.dumps(bot.get_state(full=True, symbol=symbol), default=str).encode())
                    except:
                        self.wfile.write(b'{}')
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'text/html; charset=utf-8')
                    self.end_headers()
                    self.wfile.write(html_path.read_bytes())
            def log_message(self, *args): pass
        http.server.HTTPServer((host, port), Handler).serve_forever()
