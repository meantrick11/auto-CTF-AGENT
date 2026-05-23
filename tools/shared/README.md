# Shared Tools

Available to all Workers regardless of domain. These are foundational utilities that don't require domain-specific knowledge.

## Tools

### encoding.py

| Function | Input | Output | Description |
|---|---|---|---|
| `base64_encode(data: str)` | Raw string | Base64 string | Encode to base64 |
| `base64_decode(data: str)` | Base64 string | Raw string | Decode from base64 |
| `hex_encode(data: str)` | Raw string | Hex string | Encode to hex |
| `hex_decode(data: str)` | Hex string | Raw string | Decode from hex |
| `url_encode(data: str)` | Raw string | URL-encoded string | Percent-encode |
| `url_decode(data: str)` | URL-encoded string | Raw string | Percent-decode |
| `rot13(data: str)` | Raw string | ROT13 string | ROT13 substitution cipher |

### network.py

| Function | Input | Output | Description |
|---|---|---|---|
| `http_get(url: str, headers: dict\|None)` | URL + optional headers | `{status_code, headers, body}` | Basic HTTP GET |
| `http_post(url: str, data: str\|dict, headers: dict\|None)` | URL + body + optional headers | `{status_code, headers, body}` | Basic HTTP POST |
