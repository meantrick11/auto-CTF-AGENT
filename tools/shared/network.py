"""Shared network utilities. Available to all workers."""

import urllib.request
import urllib.error
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


@register_tool(category="shared", description="Send an HTTP GET request to a URL")
def http_get(url: str, headers: dict | None = None) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "CTFAgent/1.0")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        body = resp.read().decode("utf-8", errors="replace")
        return _build_response(resp, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _build_response(e, body)
    except Exception as exc:
        return {"status_code": 0, "headers": {}, "body": "", "body_length": 0, "error": str(exc)}


@register_tool(category="shared", description="Send an HTTP POST request with a body")
def http_post(url: str, data: str = "", headers: dict | None = None) -> dict:
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    body_bytes = data.encode("utf-8")
    req = urllib.request.Request(url, data=body_bytes, method="POST")
    req.add_header("User-Agent", "CTFAgent/1.0")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    if headers:
        for k, v in headers.items():
            req.add_header(k, v)

    try:
        resp = urllib.request.urlopen(req, timeout=15, context=ctx)
        body = resp.read().decode("utf-8", errors="replace")
        return _build_response(resp, body)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        return _build_response(e, body)
    except Exception as exc:
        return {"status_code": 0, "headers": {}, "body": "", "body_length": 0, "error": str(exc)}
