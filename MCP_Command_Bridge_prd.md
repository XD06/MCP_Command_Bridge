# Mobile MCP Command Bridge 技术设计文档

## 1. 背景

手机端 AI Agent 运行在受限环境中，通常无法直接执行本地命令、访问电脑上的本地端口，或调用只监听 `127.0.0.1` 的桌面应用 API。

例如：

- 思源笔记桌面端 API：`http://127.0.0.1:6806`
- 本地草稿本 API
- 本地脚本
- 项目中的 `npm` / `node` / `python` 命令

在电脑上，Agent 可以直接执行命令或调用 API；但在手机上，Agent 只能通过远程 MCP 服务调用工具。

本项目目标是实现一个本地运行的 MCP 服务器，作为手机 Agent 与局域网电脑之间的安全跳板。

## 2. 目标

本项目提供一个远程 MCP Server，使手机端 Agent 可以通过 MCP 调用电脑上的受控程序。

核心目标：

- 支持 RikkaHub 等手机端 MCP 客户端通过 SSE / Streamable HTTP 连接
- 支持局域网访问
- 支持执行受控命令
- 支持调用本机 API，例如思源笔记 API
- 支持执行本地脚本
- 不暴露裸 shell
- 不接受完整命令字符串
- 通过结构化参数执行程序
- 对危险命令、危险参数、危险路径进行拦截
- 提供超时、输出截断、审计日志等基础安全能力

## 3. 非目标

第一版不做以下能力：

- 不做公网服务
- 不做多用户系统
- 不做 Web UI
- 不做完整远程 shell
- 不支持交互式命令
- 不支持 `sudo`
- 不支持任意二进制执行
- 不支持任意 shell 字符串
- 不默认允许删除、清理、系统级修改等破坏性操作

## 4. 整体架构

```text
手机端 RikkaHub / Agent
        |
        | MCP over SSE / Streamable HTTP
        v
Mobile MCP Command Bridge
        |
        | subprocess, shell=false
        v
受控程序:
  - curl
  - npm
  - node
  - python3
  - 其他白名单程序
        |
        v
本机 API / 本地脚本 / 项目命令
```

典型使用场景：

```text
用户在手机上说：
“把这段内容保存到思源笔记”

Agent 根据 MCP 工具 schema 构造工具调用：

{
  "program": "curl",
  "args": [
    "-X",
    "POST",
    "http://127.0.0.1:6806/api/filetree/createDocWithMd",
    "-H",
    "Authorization: Token ${SIYUAN_TOKEN}",
    "-H",
    "Content-Type: application/json",
    "-d",
    "{\"notebook\":\"...\",\"path\":\"/Inbox/test\",\"markdown\":\"hello\"}"
  ]
}

MCP Server 校验参数、替换 secret、执行 curl，并返回结果。
```

## 5. MCP 传输协议

服务端应支持远程 MCP 连接。

优先支持：

- SSE
- Streamable HTTP

RikkaHub 官方支持远程 MCP Server，传输方式包括：

- SSE
- StreamableHttp

推荐连接地址示例：

```text
http://192.168.1.23:8765/sse
```

或：

```text
http://192.168.1.23:8765/mcp
```

具体 endpoint 根据所使用的 MCP SDK 和传输实现确定。

## 6. 鉴权

MCP 服务必须启用 token 鉴权。

推荐使用 HTTP Header：

```http
Authorization: Bearer <bridge-token>
```

配置示例：

```yaml
server:
  host: "0.0.0.0"
  port: 8765
  token: "change-this-token"
```

安全要求：

- 默认不允许无 token 访问
- token 不应写入日志
- token 不应返回给模型
- 若 RikkaHub 支持自定义 headers，应使用 header 鉴权
- 若客户端不支持 header，可考虑 query token，但不推荐

## 7. 核心 MCP 工具

第一版只提供两个核心工具：

```text
run_program
get_policy
```

### 7.1 run_program

执行一个白名单程序。

该工具不接受完整 shell 命令，只接受结构化参数。

#### 输入 schema

```json
{
  "type": "object",
  "properties": {
    "program": {
      "type": "string",
      "description": "Program name to execute. Must be in server allowlist.",
      "enum": ["curl", "npm", "node", "python3"]
    },
    "args": {
      "type": "array",
      "description": "Program arguments. Each argument must be a separate string.",
      "items": {
        "type": "string"
      }
    },
    "cwd": {
      "type": "string",
      "description": "Working directory. Must be inside allowed roots."
    },
    "timeout_seconds": {
      "type": "integer",
      "description": "Execution timeout in seconds.",
      "default": 30,
      "minimum": 1,
      "maximum": 300
    }
  },
  "required": ["program", "args"]
}
```

#### 调用示例：curl 调用思源 API

```json
{
  "program": "curl",
  "args": [
    "-X",
    "POST",
    "http://127.0.0.1:6806/api/notebook/lsNotebooks",
    "-H",
    "Authorization: Token ${SIYUAN_TOKEN}",
    "-H",
    "Content-Type: application/json"
  ],
  "timeout_seconds": 20
}
```

#### 调用示例：npm test

```json
{
  "program": "npm",
  "args": ["test"],
  "cwd": "/Users/me/projects/demo",
  "timeout_seconds": 60
}
```

#### 调用示例：运行 Python 脚本

```json
{
  "program": "python3",
  "args": [
    "/Users/me/agent-scripts/sync_daily_note.py",
    "--date",
    "2026-06-02"
  ],
  "cwd": "/Users/me/agent-scripts",
  "timeout_seconds": 30
}
```

#### 返回格式

成功或失败都返回结构化结果：

```json
{
  "ok": true,
  "program": "curl",
  "args": ["-X", "POST", "..."],
  "cwd": "/Users/me/agent-workspace",
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "duration_ms": 532,
  "truncated": false
}
```

策略拦截示例：

```json
{
  "ok": false,
  "error": "Program argument denied",
  "reason": "curl output flag is not allowed",
  "program": "curl",
  "denied_arg": "-o"
}
```

### 7.2 get_policy

返回当前 MCP Server 支持的程序、限制和能力。

该工具用于让 Agent 理解服务器允许什么，不允许什么。

#### 输入 schema

```json
{
  "type": "object",
  "properties": {}
}
```

#### 返回示例

```json
{
  "programs": {
    "curl": {
      "enabled": true,
      "allowed_methods": ["GET", "POST", "PUT", "PATCH"],
      "denied_methods": ["DELETE"],
      "allowed_url_prefixes": [
        "http://127.0.0.1:6806/",
        "http://127.0.0.1:7777/"
      ],
      "denied_args": [
        "-o",
        "--output",
        "-O",
        "--remote-name",
        "-T",
        "--upload-file",
        "--config",
        "-K"
      ]
    },
    "npm": {
      "enabled": true,
      "allowed_subcommands": ["test", "run", "install", "ci"],
      "denied_args": ["exec", "x"]
    },
    "node": {
      "enabled": true,
      "denied_args": ["-e", "--eval"],
      "allowed_script_roots": ["/Users/me/agent-scripts", "/Users/me/projects"]
    },
    "python3": {
      "enabled": true,
      "denied_args": ["-c", "-m"],
      "allowed_script_roots": ["/Users/me/agent-scripts", "/Users/me/projects"]
    }
  }
}
```

## 8. 执行模型

服务端必须使用 argv 模式执行程序。

允许：

```python
subprocess.run([program, *args], shell=False)
```

禁止：

```python
subprocess.run(" ".join([program, *args]), shell=True)
```

原因：

- 避免 shell 注入
- 避免 `&&`
- 避免 `;`
- 避免 `|`
- 避免重定向
- 避免命令拼接

即使参数中包含 `&&` 或 `|`，在 `shell=false` 下也只会作为普通参数传给程序，而不会被 shell 解释。

## 9. 配置文件

推荐使用 YAML 配置。

示例：

```yaml
server:
  host: "0.0.0.0"
  port: 8765
  token: "change-this-token"

execution:
  default_cwd: "/Users/me/agent-workspace"
  allowed_roots:
    - "/Users/me/agent-workspace"
    - "/Users/me/projects"
    - "/Users/me/agent-scripts"
  timeout_seconds: 30
  max_output_bytes: 200000

secrets:
  SIYUAN_TOKEN: "your-siyuan-token"
  DRAFT_TOKEN: "your-draft-token"

programs:
  curl:
    enabled: true
    allowed_methods:
      - GET
      - POST
      - PUT
      - PATCH
    denied_methods:
      - DELETE
    allowed_url_prefixes:
      - "http://127.0.0.1:6806/"
      - "http://127.0.0.1:7777/"
      - "https://api.example.com/"
    denied_schemes:
      - "file"
      - "ftp"
    denied_args:
      - "-o"
      - "--output"
      - "-O"
      - "--remote-name"
      - "-T"
      - "--upload-file"
      - "--config"
      - "-K"
    timeout_seconds: 30

  npm:
    enabled: true
    allowed_subcommands:
      - "test"
      - "run"
      - "install"
      - "ci"
    denied_args:
      - "exec"
      - "x"
    timeout_seconds: 120

  node:
    enabled: true
    denied_args:
      - "-e"
      - "--eval"
    allowed_script_roots:
      - "/Users/me/agent-scripts"
      - "/Users/me/projects"
    timeout_seconds: 60

  python3:
    enabled: true
    denied_args:
      - "-c"
      - "-m"
    allowed_script_roots:
      - "/Users/me/agent-scripts"
      - "/Users/me/projects"
    timeout_seconds: 60
```

## 10. 参数校验流程

每次调用 `run_program` 时，服务端按以下顺序校验：

```text
1. 校验 MCP 请求 token
2. 校验 program 是否在 allowlist
3. 校验 program 是否 enabled
4. 校验 args 是否为字符串数组
5. 校验 cwd 是否在 allowed_roots 内
6. 应用全局 denied_args
7. 应用 program 专属策略
8. 对 curl 校验 URL、method、scheme、危险 flag
9. 对 npm 校验 subcommand
10. 对 node/python 校验脚本路径
11. 替换 ${SECRET_NAME}
12. 设置 timeout
13. 执行程序，shell=false
14. 截断 stdout/stderr
15. 写入审计日志
16. 返回结构化结果
```

## 11. curl 策略

`curl` 是主要 API 调用工具，但需要额外限制。

### 11.1 URL 限制

只允许访问配置中的 URL 前缀：

```yaml
allowed_url_prefixes:
  - "http://127.0.0.1:6806/"
  - "http://127.0.0.1:7777/"
```

禁止访问：

```text
file://
ftp://
未配置的公网地址
局域网内未配置地址
```

### 11.2 Method 限制

允许：

```text
GET
POST
PUT
PATCH
```

默认禁止：

```text
DELETE
```

### 11.3 Flag 限制

默认禁止会写文件、上传文件或读取额外配置的参数：

```text
-o
--output
-O
--remote-name
-T
--upload-file
--config
-K
```

### 11.4 Secret 替换

允许 args 中使用 secret 占位符：

```text
${SIYUAN_TOKEN}
```

服务端在执行前替换为配置中的真实值。

注意：

- secret 不应出现在日志中
- secret 不应返回给模型
- 返回结果中的 stdout/stderr 应进行 secret 脱敏

## 12. npm 策略

`npm` 允许执行常见开发命令，但限制危险子命令。

允许：

```text
npm test
npm run <script>
npm install
npm ci
```

禁止：

```text
npm exec
npm x
```

注意：

- `npm run` 本质上可能执行项目内任意脚本
- 因此 cwd 必须限制在 allowed_roots 内
- 建议第一版仅允许可信项目目录

## 13. node / python 策略

`node` 和 `python3` 可以执行任意代码，因此必须限制。

默认禁止：

```text
node -e
node --eval
python3 -c
python3 -m
```

只允许执行位于指定目录下的脚本：

```yaml
allowed_script_roots:
  - "/Users/me/agent-scripts"
  - "/Users/me/projects"
```

示例允许：

```text
python3 /Users/me/agent-scripts/task.py
node /Users/me/agent-scripts/task.js
```

示例禁止：

```text
python3 -c "import shutil; shutil.rmtree('/Users/me')"
node -e "require('fs').rmSync('/Users/me', {recursive:true})"
python3 /tmp/unknown.py
```

## 14. 工作目录限制

所有命令必须在允许目录内执行。

配置：

```yaml
execution:
  allowed_roots:
    - "/Users/me/agent-workspace"
    - "/Users/me/projects"
```

规则：

- 如果未传 `cwd`，使用 `default_cwd`
- 如果传了 `cwd`，必须位于 `allowed_roots` 内
- 必须解析真实路径，避免 `../` 绕过
- 禁止使用不存在的目录
- 禁止使用 `/`、`~`、系统目录作为工作目录

## 15. 输出限制

命令输出需要限制大小，避免模型上下文爆炸。

配置：

```yaml
execution:
  max_output_bytes: 200000
```

规则：

- stdout 和 stderr 分别截断或合并计数
- 返回 `truncated: true`
- 保留前半部分和后半部分，或只保留前 N bytes
- 不应无限制返回长日志

## 16. 审计日志

每次调用都应记录审计日志。

日志内容：

```json
{
  "time": "2026-06-02T12:00:00Z",
  "program": "curl",
  "args": ["-X", "POST", "..."],
  "cwd": "/Users/me/agent-workspace",
  "exit_code": 0,
  "duration_ms": 532,
  "allowed": true
}
```

要求：

- secret 必须脱敏
- token 必须脱敏
- 可记录被拒绝的调用
- 日志用于排查 Agent 行为

## 17. 安全原则

本项目采用以下安全原则：

```text
1. 默认拒绝
2. 程序白名单
3. 参数结构化
4. 不执行 shell 字符串
5. cwd 限制
6. URL 限制
7. method 限制
8. dangerous args 拦截
9. secrets 服务端托管
10. stdout/stderr 脱敏
11. 超时限制
12. 输出截断
13. 审计日志
```

## 18. 推荐 MVP

第一版实现：

```text
MCP Server:
  - SSE 或 Streamable HTTP
  - token 鉴权

Tools:
  - run_program
  - get_policy

Programs:
  - curl
  - npm
  - node
  - python3

Security:
  - shell=false
  - program allowlist
  - cwd allowed_roots
  - curl URL/method/flag policy
  - node/python script root policy
  - npm subcommand policy
  - timeout
  - output limit
  - audit log
  - secret replacement and masking
```

## 19. 示例：思源笔记

思源 API：

```text
Base URL: http://127.0.0.1:6806
Header: Authorization: Token <token>
Method: usually POST
```

配置：

```yaml
secrets:
  SIYUAN_TOKEN: "your-siyuan-api-token"

programs:
  curl:
    allowed_url_prefixes:
      - "http://127.0.0.1:6806/"
```

调用：

```json
{
  "program": "curl",
  "args": [
    "-X",
    "POST",
    "http://127.0.0.1:6806/api/filetree/createDocWithMd",
    "-H",
    "Authorization: Token ${SIYUAN_TOKEN}",
    "-H",
    "Content-Type: application/json",
    "-d",
    "{\"notebook\":\"20210817205410-xxxx\",\"path\":\"/Inbox/hello\",\"markdown\":\"# Hello\\n\\nCreated from mobile agent.\"}"
  ]
}
```

## 20. 后续增强

后续可以加入：

- Streamable HTTP + SSE 双传输支持
- 配置热重载
- 二维码显示连接地址
- policy 分 profile
- 临时授权
- destructive 操作二次确认
- 更严格的 curl 参数解析
- 更细粒度的 npm script 限制
- Web UI 查看日志和启停服务
- Tailscale / Cloudflare Tunnel 访问方案

## 21. 总结

本项目不是一个远程 shell，而是一个面向手机 Agent 的受控程序执行 MCP Bridge。

核心设计是：

```text
不要完整命令字符串
只接受 program + args + cwd
只执行白名单程序
只在允许目录执行
对每类程序施加独立策略
通过 MCP schema 约束 Agent 的调用方式
```

这样既保留了通用性，又能避免手机 Agent 获得不受限制的电脑执行能力。