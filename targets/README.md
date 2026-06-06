# Targets — 自建本地漏洞靶场

为 CTFAgent 端到端测试提供本地攻击目标。所有靶场均使用 Python 标准库实现，零外部依赖。

## 靶场列表

| 靶场 | 文件 | 端口 | 难度 | 漏洞类型 |
|---|---|---|---|---|
| CTF Corp Portal | `test_target.py` | 8888 | 中等 | SQLi, XSS, 命令注入, 信息泄露, 认证绕过 |

### CTF Corp Portal (`test_target.py`)

模拟企业内部门户系统，包含 14 个端点，需多步攻击链才能获取 flag。

**漏洞覆盖：**
- `/login` — SQL 注入绕过登录（POST）
- `/search` — 反射型 XSS
- `/ping` — 命令注入（模拟）
- `/api/v1/users` — SQL 注入（GET，id 参数）
- `/api/v1/reports` — 认证绕过（Authorization header / user 参数）
- `/debug` — 调试信息泄露（数据库连接串、密钥）
- `/config.bak` — 配置文件泄露（数据库密码）
- `/robots.txt` — 路径发现（Disallow 字段泄露内部端点）
- `/staging` — 测试环境弱口令（admin/admin123!）
- `/old_admin` — 已废弃管理面板（默认凭证）
- `/admin` — Cookie 会话伪造（session=admin）

**攻击链路（预期）：**
1. `/robots.txt` 或 `/debug` → 发现隐藏端点
2. `/debug` 或 `/config.bak` → 获取 admin 密码（base64 编码）
3. 解码密码 → `/login` POST 登录 → 获取 session cookie
4. 携带 cookie 访问 `/admin` → 获取 flag

**运行方式：**
```powershell
# Terminal 1 — 启动靶场（先激活虚拟环境）
.\.venv\Scripts\Activate.ps1
python targets\test_target.py

# Terminal 2 — 启动 CTFAgent 攻击（先激活虚拟环境）
.\.venv\Scripts\Activate.ps1
python main.py -g "Attack http://localhost:8888 and capture the flag" -n 12
```

## 添加新靶场

1. 在 `targets/` 目录下新建 `.py` 文件
2. 使用 Python 标准库实现（`http.server` 推荐）
3. 在本文档的靶场列表中登记
4. 明确标注 flag 获取条件与预期攻击链路
