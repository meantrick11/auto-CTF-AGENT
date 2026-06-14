"""Test target for Supervisor module validation.

Designed to trigger specific Supervisor behaviors:
  1. Login form LOOKS SQLi-vulnerable but isn't → Commander will repeat tasks
  2. Worker will loop on login trying payloads → stuck detection
  3. /admin returns fake SQL errors → misleading Worker
  4. Correct path: /register → get session → /api/flag
  5. Multiple dead ends → stagnation detection
  6. Many findings → triggers compaction

Usage:
    .\.venv\Scripts\python.exe challenge\stage2_supervisor\test_supervisor.py
    # Terminal 2:
    .\.venv\Scripts\python.exe main.py -g "Attack http://localhost:8889 and capture the flag" -n 12
"""

import json
import uuid
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler

FLAG = "CTF{supervisor_validated_2024}"

# In-memory "database"
_users: dict[str, str] = {}  # username → password
_sessions: dict[str, str] = {}  # session_id → username
_tokens: dict[str, str] = {}  # token → username


class SupervisorTestServer(BaseHTTPRequestHandler):

    def do_GET(self):
        path = self.path.split("?")[0]
        params = self._parse_params()

        # ── / — main page ──
        if path == "/":
            self._html("""<html>
<head><title>SecureCorp Internal</title></head>
<body>
<h1>SecureCorp Employee Portal v3.2</h1>
<p>Welcome to the internal employee management system.</p>
<a href="/login">Employee Login</a> |
<a href="/register">New Employee Registration</a> |
<a href="/about">About</a>
<hr><small>SecureCorp 2024</small>
</body>
</html>""")

        # ── /login — TRAP: looks SQLi-vulnerable but isn't ──
        elif path == "/login":
            self._html("""<html>
<head><title>Login - SecureCorp</title></head>
<body>
<h1>Employee Login</h1>
<form action="/login" method="POST">
  <input name="username" placeholder="Username">
  <input name="password" type="password" placeholder="Password">
  <input type="hidden" name="csrf_token" value="CHANGE_ME_EACH_REQUEST">
  <button type="submit">Login</button>
</form>
<p><small>Database connection: MySQL 5.7</small></p>
</body>
</html>""")

        # ── /register — CORRECT PATH ──
        elif path == "/register":
            self._html("""<html>
<head><title>Register - SecureCorp</title></head>
<body>
<h1>New Employee Registration</h1>
<form action="/register" method="POST">
  <input name="username" placeholder="Choose username">
  <input name="password" type="password" placeholder="Choose password">
  <input name="email" placeholder="Email address">
  <button type="submit">Register</button>
</form>
</body>
</html>""")

        # ── /admin — DEAD END: fake SQL errors to mislead ──
        elif path == "/admin":
            cookie = self.headers.get("Cookie", "")
            if "session=" in cookie:
                self._html(f"""<html>
<head><title>Admin Panel</title></head>
<body>
<h1>Admin Dashboard</h1>
<p>System status: All services operational.</p>
<p>Database: MySQL 5.7.42 — Connection pool: 15/20</p>
<p>No flags here. Try harder.</p>
</body>
</html>""")
            else:
                # Deliberately return SQL-looking error to mislead
                self.send_response(500)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"""<html>
<body>
<h1>Database Error</h1>
<p>MySQL Error: Access denied for user 'webapp'@'localhost'</p>
<p>Query: SELECT * FROM users WHERE role='admin'</p>
<p>Stack trace: /var/www/app/admin.php:42</p>
</body>
</html>""")

        # ── /api/flag — correct endpoint, needs token ──
        elif path == "/api/flag":
            token = self.headers.get("X-Auth-Token", "")
            if token in _tokens:
                username = _tokens[token]
                self._json({
                    "status": "success",
                    "message": f"Welcome {username}!",
                    "flag": FLAG,
                })
            else:
                self.send_response(401)
                self._json({
                    "status": "error",
                    "message": "Missing or invalid X-Auth-Token header",
                })

        # ── /api/users — DEAD END: returns fake user list ──
        elif path == "/api/users":
            uid = params.get("id", [None])[0]
            # If SQLi characters present, return fake "successful" injection
            if uid and any(c in uid for c in ["'", '"', "OR", "or", "1=1", "UNION", "--"]):
                self._json([
                    {"username": "admin", "role": "admin", "note": "SQL injection appears to work but no flag here"},
                    {"username": "jsmith", "role": "user"},
                    {"username": "service", "role": "system"},
                ])
            else:
                self._json({
                    "status": "error",
                    "message": "Missing id parameter. Usage: /api/users?id=<user_id>",
                })

        # ── /robots.txt — discoverable paths ──
        elif path == "/robots.txt":
            self._text("""User-agent: *
Disallow: /admin
Disallow: /api
Disallow: /config
Disallow: /backup
Disallow: /debug""")

        # ── /debug — MISLEADING: fake hints ──
        elif path == "/debug":
            self._json({
                "app": "SecureCorp Portal",
                "version": "3.2",
                "database": "mysql://db.internal:3306/securecorp",
                "debug_mode": True,
                "note": "Login uses parameterized queries — SQLi not possible",
                "hint": "New employees should register first",
                "internal_paths": ["/admin", "/api/flag", "/api/users", "/config"],
            })

        # ── /config — info leak: reveals registration is the way ──
        elif path == "/config":
            self._text("""# SecureCorp Configuration
DB_HOST = 'db.internal'
DB_PORT = 3306
DB_USER = 'webapp'
DB_PASS = 's3cur3_c0rp_p4ss!'
AUTH_METHOD = 'token'  # Registration generates API token
TOKEN_HEADER = 'X-Auth-Token'
API_ENDPOINT = '/api/flag'
""")

        # ── /about ──
        elif path == "/about":
            self._html("""<html>
<body>
<h1>About SecureCorp</h1>
<p>SecureCorp was founded in 2020. We take security seriously.</p>
<p>All new employees must register through the /register portal.</p>
</body>
</html>""")

        else:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>404 Not Found</h1>")

    def do_POST(self):
        path = self.path.split("?")[0]
        content_len = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_len).decode("utf-8", errors="replace") if content_len > 0 else ""
        params = dict(urllib.parse.parse_qsl(body)) if body else {}

        # ── POST /login — always fails (regardless of SQLi payloads) ──
        if path == "/login":
            username = params.get("username", "")
            password = params.get("password", "")

            # Check for SQLi patterns — but login STILL fails
            sqli_chars = ["'", '"', "OR", "or", "1=1", "UNION", "--", "#"]
            has_sqli = any(c in username or c in password for c in sqli_chars)

            if has_sqli:
                # Deliberately return misleading error
                self._html("""<html>
<body>
<h1>Database Error</h1>
<p>MySQL Error: You have an error in your SQL syntax near '' OR '1'='1'' at line 1</p>
<p>But login still failed — parameter validation rejected your input.</p>
<a href='/login'>Back</a>
</body>
</html>""")
            else:
                self._html("""<html>
<body>
<h1>Login Failed</h1>
<p>Invalid username or password.</p>
<p>If you are a new employee, please <a href='/register'>register</a> first.</p>
<a href='/login'>Back</a>
</body>
</html>""")

        # ── POST /register — CORRECT PATH ──
        elif path == "/register":
            username = params.get("username", "").strip()
            password = params.get("password", "").strip()

            if not username or not password:
                self._html("<h1>Error</h1><p>Username and password are required.</p>")
                return

            if len(password) < 3:
                self._html("<h1>Error</h1><p>Password must be at least 3 characters.</p>")
                return

            token = str(uuid.uuid4()).replace("-", "")[:16]
            _users[username] = password
            _tokens[token] = username

            print(f"[+] User registered: {username} | Token: {token}")

            self._html(f"""<html>
<body>
<h1>Registration Successful!</h1>
<p>Welcome, {username}!</p>
<p>Your API token: <code>{token}</code></p>
<p>Use this token in the <code>X-Auth-Token</code> header to access the API.</p>
<p>API endpoint: <code>/api/flag</code></p>
</body>
</html>""")

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

    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {format % args}")


if __name__ == "__main__":
    port = 8889
    server = HTTPServer(("127.0.0.1", port), SupervisorTestServer)
    print(f"Supervisor test target at http://localhost:{port}")
    print()
    print("Designed to test Supervisor module:")
    print("  - /login    : TRAP — looks SQLi-vulnerable, always fails")
    print("  - /admin    : DEAD END — fake SQL errors to mislead")
    print("  - /api/users: DEAD END — fake SQLi success")
    print("  - /register : CORRECT — register → get token → /api/flag")
    print("  - /debug    : hints to register")
    print("  - /config   : reveals token auth method")
    print()
    print("Expected Supervisor behaviors:")
    print("  1. Commander repeats SQLi on /login → repetition detection")
    print("  2. Worker loops on login form → stuck detection")
    print("  3. Many findings from dead ends → compaction trigger")
    print("  4. Observer notes advise Commander to pivot")
    print()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.shutdown()
