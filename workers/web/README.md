# Web Worker — Web Security Domain Specialist

## Role

Executes web security tasks: reconnaissance, vulnerability probing, and exploitation against HTTP-based targets. Receives natural language instructions from Commander, translates them into tool invocations, and extracts structured findings.

## Files

| File | Role | Input | Output |
|---|---|---|---|
| `agent.py` | WebWorker class extending BaseWorker | Task (from blackboard) | TaskResult + Findings (to blackboard) |
| `prompts/system_prompt.txt` | System prompt for web security persona | — | — |

## Input

A `Task` object from the blackboard:
```python
Task(
    id="task-001",
    type="web_recon",             # or "web_exploit"
    instruction="扫描 http://target.com 的目录结构，识别所有可达路径",
    input_data={"url": "http://target.com", "method": "GET"}
)
```

## Output

```python
{
    "task_id": "task-001",
    "status": "completed",
    "output_data": {
        "summary": "发现 3 个可访问路径",
        "raw_result": {...}
    },
    "findings": [
        {
            "type": "asset",
            "title": "发现管理后台 /admin",
            "data": {"url": "http://target.com/admin", "status_code": 200},
            "confidence": 1.0
        },
        {
            "type": "asset",
            "title": "发现API端点 /api/debug",
            "data": {"url": "http://target.com/api/debug", "status_code": 200},
            "confidence": 1.0
        }
    ]
}
```

## Available Tools

### Shared (all workers)
- `encoding` — base64, hex, URL encode/decode, ROT13
- `network` — HTTP GET/POST, basic socket

### Web Domain
- `web_directory_scan` — Brute-force directory enumeration
- `web_extract_forms` — Parse HTML, extract all `<form>` elements with inputs
- `web_analyze_headers` — Analyze security-relevant response headers
- `web_sqli_test` — Test parameters for SQL injection vulnerabilities
- `web_xss_test` — Test input points for XSS vulnerabilities
- `web_command_injection_test` — Test parameters for command injection vulnerabilities

## System Prompt Principles

1. You are a web security specialist — focus on HTTP/HTTPS targets
2. Follow the Commander's instruction precisely
3. Use the right tool for each sub-step
4. Always extract structured findings (URL, vulnerability type, evidence)
5. Report confidence level for each finding
6. If a tool fails, report the error and continue with other approaches
