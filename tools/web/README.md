# Web Domain Tools

Available only to the Web Worker. These tools perform web-specific reconnaissance and exploitation.

## Reconnaissance Tools (recon.py)

| Function | Input | Output | Description |
|---|---|---|---|
| `web_directory_scan(url: str, wordlist: str)` | Target URL + wordlist name | `{found_paths: [{path, status_code, size}]}` | Brute-force common directory names |
| `web_extract_forms(url: str)` | Target URL | `{forms: [{action, method, inputs: [{name, type, value}]}]}` | Parse HTML, extract all forms |
| `web_analyze_headers(url: str)` | Target URL | `{headers: {key: value}, security_issues: [...]}` | Check for missing security headers |

## Exploitation Tools (exploit.py)

| Function | Input | Output | Description |
|---|---|---|---|
| `web_sqli_test(url: str, param: str, method: str)` | URL + injectable param | `{vulnerable: bool, payload: str, evidence: str}` | Test single param for SQL injection |
| `web_xss_test(url: str, param: str, method: str)` | URL + injectable param | `{vulnerable: bool, payload: str, evidence: str}` | Test single param for XSS |
| `web_command_injection_test(url: str, param: str)` | URL + injectable param | `{vulnerable: bool, payload: str, evidence: str}` | Test for command injection |
