"""Local vulnerable web target for testing CTFAgent workflow.

Usage:
    .\.venv\Scripts\python.exe test_target.py
    # Then in another terminal:
    .\.venv\Scripts\python.exe main.py -g "Attack http://localhost:8888 and capture the flag" -n 8
"""

import base64
import json
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

FLAG = "CTF{localtest_flag_2024}"
FLAG_B64 = base64.b64encode(FLAG.encode()).decode()


class VulnServer(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]
        params = self._parse_params()

        # ── / — main page with hidden base64 flag ──
        if path == "/":
            self._html(f"""<html>
<head><title>Welcome to TestApp</title></head>
<body>
<h1>Welcome to TestApp v1.0</h1>
<p>This is a simple web application for testing.</p>
<!-- TODO: remove debug info: admin password in base64: {FLAG_B64} -->
<a href="/login">Login</a> | <a href="/admin">Admin Panel</a>
<!-- /source_backup -->
</body>
</html>""")

        # ── /login — login page ──
        elif path == "/login":
            self._html(f"""<html>
<head><title>Login - TestApp</title></head>
<body>
<h1>Login</h1>
<form action="/login" method="POST">
  <input name="username" placeholder="Username">
  <input name="password" type="password" placeholder="Password">
  <button type="submit">Login</button>
</form>
<p>Hint: admin account exists</p>
</body>
</html>""")

        # ── /admin — protected admin panel ──
        elif path == "/admin":
            cookie = self.headers.get("Cookie", "")
            if "admin=true" in cookie:
                self._html(f"""<html>
<head><title>Admin Panel</title></head>
<body>
<h1>Admin Panel</h1>
<p>Welcome, administrator!</p>
<p>The secret flag is: <b>{FLAG}</b></p>
</body>
</html>""")
            else:
                self.send_response(403)
                self._html("<h1>403 Forbidden</h1><p>Admin access only.</p>")

        # ── /robots.txt — discoverable path ──
        elif path == "/robots.txt":
            self._text("User-agent: *\nDisallow: /admin\nDisallow: /backup\nDisallow: /debug")

        # ── /debug — debug info leak ──
        elif path == "/debug":
            self._json({
                "app": "TestApp",
                "version": "1.0",
                "debug_mode": True,
                "database": "sqlite:///app.db",
                "admin_hint": FLAG_B64,
                "internal_paths": ["/admin", "/backup", "/api/v1/users"]
            })

        # ── /source_backup — source code leak ──
        elif path == "/source_backup":
            self._text(f"""# config.py
SECRET_KEY = '{FLAG}'
DATABASE_URL = 'sqlite:///app.db'
DEBUG = False
# Admin credentials (hashed): admin / admin123
            """)

        # ── /api/v1/users — API endpoint ──
        elif path == "/api/v1/users":
            uid = params.get("id", [None])[0]
            if uid and "'" in uid:
                # Simulate SQL injection: return all users
                self._json([
                    {"id": 1, "username": "admin", "role": "administrator"},
                    {"id": 2, "username": "user1", "role": "user"},
                    {"id": 3, "username": "guest", "role": "guest"},
                ])
            else:
                self._json([{"id": 1, "username": "admin", "role": "administrator"}])

        else:
            self.send_response(404)
            self._html("<h1>404 Not Found</h1>")

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode() if content_len > 0 else ""
        params = dict(urllib.parse.parse_qsl(body))

        if path == "/login":
            username = params.get("username", "")
            password = params.get("password", "")

            # SQL injection check
            sqli_patterns = ["'", '"', "OR", "or", "1=1", "UNION", "--", "#"]
            has_sqli = any(p in username or p in password for p in sqli_patterns)

            if has_sqli:
                # SQLi bypass successful — set admin cookie
                self.send_response(302)
                self.send_header("Set-Cookie", "admin=true; Path=/")
                self.send_header("Location", "/admin")
                self.end_headers()
                self.wfile.write(b"SQLi success! Redirecting to /admin...")
                self._print(f"[!] SQL INJECTION on /login — username={username!r}")
            elif username == "admin" and password == "admin123":
                self.send_response(302)
                self.send_header("Set-Cookie", "admin=true; Path=/")
                self.send_header("Location", "/admin")
                self.end_headers()
            else:
                self._html("<h1>Login Failed</h1><p>Invalid credentials.</p><a href='/login'>Back</a>")

        else:
            self.send_response(404)
            self._html("<h1>404</h1>")

    def _parse_params(self):
        qs = self.path.split("?")[1] if "?" in self.path else ""
        return urllib.parse.parse_qs(qs)

    def _html(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _text(self, content):
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(content.encode())

    def _json(self, data):
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.end_headers()
        self.wfile.write(json.dumps(data, indent=2).encode())

    def _print(self, msg):
        print(msg)

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {format % args}")


if __name__ == "__main__":
    port = 8888
    server = HTTPServer(("127.0.0.1", port), VulnServer)
    print(f"Vuln server running at http://localhost:{port}")
    print(f"Attack it with:")
    print(f"  .\\.venv\\Scripts\\python.exe main.py -g \"Attack http://localhost:{port} and capture the flag\" -n 8")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
