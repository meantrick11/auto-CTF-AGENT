"""Local vulnerable web target for testing CTFAgent workflow.

Usage (from project root):
    .\.venv\Scripts\python.exe targets\test_target.py
    # Then in another terminal:
    .\.venv\Scripts\python.exe main.py -g "Attack http://localhost:8888 and capture the flag" -n 12
"""

import base64
import json
import os
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

FLAG = "CTF{multistep_pwned_2024}"
ADMIN_PASSWORD = "admin123!"
ADMIN_PASSWORD_B64 = base64.b64encode(ADMIN_PASSWORD.encode()).decode()
FLAG_B64 = base64.b64encode(FLAG.encode()).decode()


class VulnServer(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]
        params = self._parse_params()

        # ── / — main page ──
        if path == "/":
            self._html(f"""<html>
<head><title>CTF Corp Portal</title></head>
<body>
<h1>CTF Corp Internal Portal v2.1</h1>
<p>Employee self-service system.</p>
<!-- dev note: staging password is {ADMIN_PASSWORD_B64} — remove before launch -->
<a href="/login">Employee Login</a> |
<a href="/search">Search</a> |
<a href="/notes">Bulletin</a>
<hr><small>Copyright 2024 CTF Corp</small>
</body>
</html>""")

        # ── /login — employee login ──
        elif path == "/login":
            self._html(f"""<html>
<head><title>Login - CTF Corp</title></head>
<body>
<h1>Employee Login</h1>
<form action="/login" method="POST">
  <input name="username" placeholder="Username">
  <input name="password" type="password" placeholder="Password">
  <button type="submit">Login</button>
</form>
<p><small>Forgot password? Contact IT support.</small></p>
</body>
</html>""")

        # ── /admin — protected admin panel ──
        elif path == "/admin":
            cookie = self.headers.get("Cookie", "")
            if "session=admin" in cookie:
                self._html(f"""<html>
<head><title>Admin Dashboard</title></head>
<body>
<h1>Admin Dashboard</h1>
<p>Welcome, admin!</p>
<p>The master flag is: <b>{FLAG}</b></p>
<hr>
<h3>System Tools</h3>
<a href="/ping?host=127.0.0.1">Network Diagnostics</a><br>
<a href="/backup.zip">Download Backup</a>
</body>
</html>""")
            else:
                self.send_response(403)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>403 Forbidden</h1><p>Admin session required.</p>")

        # ── /search — reflected XSS ──
        elif path == "/search":
            q = params.get("q", [""])[0]
            self._html(f"""<html>
<head><title>Search - CTF Corp</title></head>
<body>
<h1>Employee Search</h1>
<form action="/search" method="GET">
  <input name="q" placeholder="Search employees...">
  <button type="submit">Search</button>
</form>
<p>Results for: {q}</p>
<p>No results found.</p>
</body>
</html>""")

        # ── /ping — command injection ──
        elif path == "/ping":
            host = params.get("host", ["127.0.0.1"])[0]
            cmd_injected = False
            for char in [";", "|", "`", "$", "&"]:
                if char in host:
                    cmd_injected = True
                    break
            if cmd_injected:
                result = f"PING {host}:\n64 bytes from 127.0.0.1: icmp_seq=1\n64 bytes from 127.0.0.1: icmp_seq=2\n--- internal hosts ---\nadmin-panel.corp.internal\napi.corp.internal\ndb.corp.internal\n"
            else:
                result = f"PING {host}:\n64 bytes from 127.0.0.1: icmp_seq=1\n--- {host} ping statistics ---"
            self._text(result)

        # ── /notes — bulletin board ──
        elif path == "/notes":
            self._html("""<html>
<head><title>Bulletin - CTF Corp</title></head>
<body>
<h1>Company Bulletin</h1>
<ul>
  <li><b>2024-01-15:</b> New staging server deployed. Admin password sent via internal DM.</li>
  <li><b>2024-01-10:</b> Reminder: all employees must change passwords by end of month.</li>
  <li><b>2024-01-05:</b> IT is migrating from /old_admin to /admin. Old endpoint will be deprecated.</li>
</ul>
</body>
</html>""")

        # ── /robots.txt — discoverable paths ──
        elif path == "/robots.txt":
            self._text("""User-agent: *
Disallow: /admin
Disallow: /backup
Disallow: /debug
Disallow: /api
Disallow: /old_admin
Disallow: /config.bak
Disallow: /staging""")

        # ── /debug — debug info leak ──
        elif path == "/debug":
            self._json({
                "app": "CTF Corp Portal",
                "version": "2.1",
                "debug_mode": True,
                "database": "postgresql://db.internal:5432/corp",
                "admin_hint": ADMIN_PASSWORD_B64,
                "secret_key": "sk-corp-internal-2024",
                "internal_endpoints": [
                    "/admin", "/api/v1/users", "/api/v1/reports",
                    "/old_admin", "/config.bak", "/backup.zip"
                ],
            })

        # ── /config.bak — leaked config ──
        elif path == "/config.bak":
            self._text(f"""# CTF Corp Portal Configuration
DATABASE_URL = 'postgresql://admin:{ADMIN_PASSWORD}@db.internal:5432/corp'
SECRET_KEY = 'sk-corp-internal-2024'
DEBUG = False
ALLOWED_HOSTS = ['internal.corp.local', 'localhost']
ADMIN_EMAIL = 'admin@corp.local'
# API key for internal services
INTERNAL_API_KEY = 'corp_api_key_2024'
""")

        # ── /backup.zip — fake backup with credential hint ──
        elif path == "/backup.zip":
            self.send_response(200)
            self.send_header("Content-Type", "application/zip")
            self.send_header("Content-Disposition", "attachment; filename=backup.zip")
            self.end_headers()
            content = (
                "PK\x03\x04... backup_notes.txt\n"
                "---\n"
                "Backup created: 2024-01-15\n"
                "Database dump location: /api/v1/users\n"
                "Admin panel: /admin (login required)\n"
                "IT contact: admin@corp.local\n"
                "---\n"
                "... PK\x01\x02 ..."
            )
            self.wfile.write(content.encode())

        # ── /staging — staging server ──
        elif path == "/staging":
            self._html("""<html>
<head><title>Staging Server</title></head>
<body>
<h1>CTF Corp Staging</h1>
<p>Staging environment — not production.</p>
<p>Test credentials: admin / admin123!</p>
</body>
</html>""")

        # ── /api/v1/users — SQL injection ──
        elif path == "/api/v1/users":
            uid = params.get("id", [None])[0]
            if uid and any(c in uid for c in ["'", '"', "OR", "or", "1=1", "UNION", "--", "#"]):
                self._json([
                    {"id": 1, "username": "admin", "role": "administrator", "email": "admin@corp.local"},
                    {"id": 2, "username": "jdoe", "role": "engineer", "email": "jdoe@corp.local"},
                    {"id": 3, "username": "asmith", "role": "manager", "email": "asmith@corp.local"},
                    {"id": 4, "username": "service_account", "role": "system", "email": "sa@corp.internal"},
                ])
            elif uid:
                self._json([{"id": 1, "username": "admin", "role": "administrator", "email": "admin@corp.local"}])
            else:
                self._json({"error": "Missing id parameter. Use ?id=<user_id>"})

        # ── /api/v1/reports — auth bypass ──
        elif path == "/api/v1/reports":
            auth = self.headers.get("Authorization", "")
            if "Bearer" in auth or "admin" in params.get("user", [""])[0]:
                self._json({
                    "reports": [
                        {"id": 1, "title": "Monthly Security Audit", "status": "draft"},
                        {"id": 2, "title": "Penetration Test Results", "status": "internal"},
                    ],
                    "admin_note": "Flag is only accessible via /admin panel after login.",
                })
            else:
                self.send_response(401)
                self._json({"error": "Unauthorized. Use Authorization header or ?user=admin"})

        # ── /old_admin — deprecated admin ──
        elif path == "/old_admin":
            self._html("""<html>
<head><title>Old Admin</title></head>
<body>
<h1>Old Admin Panel (Deprecated)</h1>
<p>This panel has been moved to /admin.</p>
<p>Default credentials: admin / admin123!</p>
</body>
</html>""")

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>404 Not Found</h1>")

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode() if content_len > 0 else ""
        params = dict(urllib.parse.parse_qsl(body))

        if path == "/login":
            username = params.get("username", "")
            password = params.get("password", "")

            sqli_patterns = ["'", '"', "OR", "or", "1=1", "UNION", "--", "#"]
            has_sqli = any(p in username or p in password for p in sqli_patterns)

            if has_sqli:
                self._print(f"[!] SQL INJECTION on /login — username={username!r}")
                self.send_response(302)
                self.send_header("Set-Cookie", "session=admin; Path=/")
                self.send_header("Location", "/admin")
                self.end_headers()
                self.wfile.write(b"Login bypassed! Redirecting to /admin...")
            elif username == "admin" and password == ADMIN_PASSWORD:
                self._print(f"[!] Valid login: admin")
                self.send_response(302)
                self.send_header("Set-Cookie", "session=admin; Path=/")
                self.send_header("Location", "/admin")
                self.end_headers()
            elif username == "admin" and password == "admin123!":
                self._print(f"[!] Staging credentials used: admin/admin123!")
                self.send_response(302)
                self.send_header("Set-Cookie", "session=admin; Path=/")
                self.send_header("Location", "/admin")
                self.end_headers()
            else:
                self._html("<h1>Login Failed</h1><p>Invalid credentials.</p><a href='/login'>Back</a>")

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"<h1>404</h1>")

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
    print(f"  .\\.venv\\Scripts\\python.exe main.py -g \"Attack http://localhost:{port} and capture the flag\" -n 12")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
