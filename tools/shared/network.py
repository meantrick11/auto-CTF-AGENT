"""Shared network utilities. Available to all workers."""

import urllib.request
import urllib.error
import socket
import json
import ssl

from tools.registry import register_tool


def _build_response(resp, body: str) -> dict:
    return {
        "status_code": resp.status,
        "headers": dict(resp.headers),
        "body": body[:5000],
        "body_length": len(body),
    }


def _build_opener():
    """Create an opener that does NOT follow redirects.

    Workers need to see Set-Cookie headers on 302 responses and manually
    forward cookies to subsequent requests. Auto-redirect would lose cookies.
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    return urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx))


_opener = _build_opener()


@register_tool(category="shared", description="Send an HTTP GET request to a URL. Supports custom headers and cookies.")
def http_get(url: str, headers: dict | None = None,
             cookies: dict | None = None) -> dict:
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "CTFAgent/1.0")

    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req.add_header("Cookie", cookie_str)

    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = _opener.open(req, timeout=15)
        body = resp.read().decode("utf-8", errors="replace")
        return _build_response(resp, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _build_response(e, body)
    except urllib.error.URLError as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "connection_error"}
    except socket.timeout as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "timeout"}
    except Exception as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "unknown"}


@register_tool(category="shared", description="Send an HTTP POST request. Returns ALL response headers including Set-Cookie (redirects are NOT followed).")
def http_post(url: str, data: str = "", headers: dict | None = None,
              cookies: dict | None = None) -> dict:
    body_bytes = data.encode("utf-8")
    req = urllib.request.Request(url, data=body_bytes, method="POST")
    req.add_header("User-Agent", "CTFAgent/1.0")

    has_content_type = headers is not None and any(
        k.lower() == "content-type" for k in headers
    )
    if not has_content_type:
        req.add_header("Content-Type", "application/x-www-form-urlencoded")

    if cookies:
        cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
        req.add_header("Cookie", cookie_str)

    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = _opener.open(req, timeout=15)
        body = resp.read().decode("utf-8", errors="replace")
        return _build_response(resp, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _build_response(e, body)
    except urllib.error.URLError as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "connection_error"}
    except socket.timeout as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "timeout"}
    except Exception as exc:
        return {"status_code": 0, "headers": {}, "body": "",
                "body_length": 0, "error": str(exc), "error_type": "unknown"}
