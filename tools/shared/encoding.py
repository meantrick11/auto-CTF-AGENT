"""Shared encoding/decoding utilities. Available to all workers."""

import base64
import codecs
import urllib.parse

from tools.registry import register_tool


@register_tool(category="shared", description="Encode a string to base64")
def base64_encode(data: str) -> str:
    return base64.b64encode(data.encode("utf-8")).decode("utf-8")


@register_tool(category="shared", description="Decode a base64 string")
def base64_decode(data: str) -> str:
    return base64.b64decode(data.encode("utf-8")).decode("utf-8")


@register_tool(category="shared", description="Encode a string to hexadecimal")
def hex_encode(data: str) -> str:
    return data.encode("utf-8").hex()


@register_tool(category="shared", description="Decode a hexadecimal string")
def hex_decode(data: str) -> str:
    return bytes.fromhex(data).decode("utf-8")


@register_tool(category="shared", description="URL-encode a string")
def url_encode(data: str) -> str:
    return urllib.parse.quote(data, safe="")


@register_tool(category="shared", description="URL-decode a percent-encoded string")
def url_decode(data: str) -> str:
    return urllib.parse.unquote(data)


@register_tool(category="shared", description="Apply ROT13 substitution cipher")
def rot13(data: str) -> str:
    return codecs.encode(data, "rot_13")
