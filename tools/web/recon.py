"""Web reconnaissance tools for the Web Worker."""

import re
from html.parser import HTMLParser
from urllib.parse import urljoin

from tools.registry import register_tool
from tools.shared.network import http_get


# ── Common directory wordlist ────────────────────────────────────

_COMMON_PATHS = [
    "admin", "login", "wp-admin", "administrator", "panel",
    "api", "api/v1", "api/debug", "debug", "test", "dev",
    "backup", "backup.zip", "backup.tar.gz", ".git", ".env",
    "config", "config.php", "config.php.bak", "phpinfo.php",
    "robots.txt", "sitemap.xml", ".htaccess", "nginx.conf",
    "upload", "uploads", "images", "static", "assets",
    "console", "dashboard", "shell", "cmd", "exec",
    "flag", "flag.txt", "secret", "hidden", "private",
    "source", "src", "www", "old", "new", "v1", "v2",
    ".git/HEAD", ".git/config", ".svn/entries", ".DS_Store",
]


class _FormExtractor(HTMLParser):
    """Parse HTML and extract form elements."""

    def __init__(self):
        super().__init__()
        self.forms: list[dict] = []
        self._current_form: dict | None = None
        self._in_form = False

    def handle_starttag(self, tag, attrs):
        attrs_dict = dict(attrs)
        if tag == "form":
            self._current_form = {
                "action": attrs_dict.get("action", ""),
                "method": attrs_dict.get("method", "GET").upper(),
                "inputs": [],
            }
            self._in_form = True
        elif self._in_form and tag == "input":
            self._current_form["inputs"].append({
                "name": attrs_dict.get("name", ""),
                "type": attrs_dict.get("type", "text"),
                "value": attrs_dict.get("value", ""),
            })
        elif self._in_form and tag == "textarea":
            self._current_form["inputs"].append({
                "name": attrs_dict.get("name", ""),
                "type": "textarea",
                "value": "",
            })
        elif self._in_form and tag == "select":
            self._current_form["inputs"].append({
                "name": attrs_dict.get("name", ""),
                "type": "select",
                "value": "",
            })

    def handle_endtag(self, tag):
        if tag == "form" and self._current_form:
            self.forms.append(self._current_form)
            self._current_form = None
            self._in_form = False


# ── Tools ────────────────────────────────────────────────────────

@register_tool(category="web", description="Scan a target URL for common directories and files")
def web_directory_scan(url: str, wordlist: str = "common") -> dict:
    base_url = url.rstrip("/")
    found: list[dict] = []
    paths = _COMMON_PATHS

    for path in paths:
        target = f"{base_url}/{path}"
        resp = http_get(target)
        if resp.get("status_code", 0) in (200, 301, 302, 403):
            found.append({
                "path": f"/{path}",
                "full_url": target,
                "status_code": resp.get("status_code", 0),
                "content_length": resp.get("body_length", 0),
            })

    return {
        "base_url": base_url,
        "wordlist": wordlist,
        "total_scanned": len(paths),
        "found_paths": found,
    }


@register_tool(category="web", description="Extract all HTML form elements from a URL")
def web_extract_forms(url: str) -> dict:
    resp = http_get(url)
    if resp.get("status_code", 0) != 200:
        return {"url": url, "forms": [], "error": f"HTTP {resp.get('status_code')}"}

    parser = _FormExtractor()
    parser.feed(resp.get("body", ""))

    # Resolve relative form actions
    for form in parser.forms:
        if form["action"] and not form["action"].startswith("http"):
            form["action"] = urljoin(url, form["action"])

    return {"url": url, "forms": parser.forms}


@register_tool(category="web", description="Analyze security-relevant HTTP response headers")
def web_analyze_headers(url: str) -> dict:
    resp = http_get(url)
    headers = resp.get("headers", {})
    issues: list[str] = []

    security_headers = {
        "Content-Security-Policy": "CSP not set — XSS risk",
        "X-Frame-Options": "Clickjacking protection missing",
        "X-Content-Type-Options": "MIME sniffing protection missing",
        "Strict-Transport-Security": "HSTS not set",
        "X-XSS-Protection": "XSS filter not configured",
    }

    missing = []
    for header, desc in security_headers.items():
        if header not in headers:
            missing.append({"header": header, "issue": desc})

    # Check for info disclosure
    server_header = headers.get("Server", "")
    powered_by = headers.get("X-Powered-By", "")

    return {
        "url": url,
        "status_code": resp.get("status_code"),
        "server": server_header,
        "powered_by": powered_by,
        "missing_security_headers": missing,
        "all_headers": headers,
    }
