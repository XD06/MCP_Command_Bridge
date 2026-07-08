#!/usr/bin/env python3
"""
MCP Command Bridge — Full Integration Test Suite
Run: python tests/integration_test.py
Requires: requests (pip install requests)
"""
import json
import sys
import time
import requests

# Fix Windows console encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

BASE_URL = "https://gemini.203065.xyz/mcp"
TOKEN = "123456"
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Content-Type": "application/json",
    "Accept": "application/json, text/event-stream",
}
SESSION_ID = None
PASSED = 0
FAILED = 0


def init():
    global SESSION_ID
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "integration-test", "version": "1.0"},
        },
    }
    resp = requests.post(BASE_URL, headers=HEADERS, json=payload, timeout=30)
    SESSION_ID = resp.headers.get("Mcp-Session-Id")
    if not SESSION_ID:
        print("FAIL: No session ID returned")
        sys.exit(1)
    print(f"OK   Session: {SESSION_ID}")


def call(tool_name, arguments, rid=None):
    payload = {
        "jsonrpc": "2.0", "id": rid or 99,
        "method": "tools/call",
        "params": {"name": tool_name, "arguments": arguments},
    }
    resp = requests.post(
        BASE_URL, headers={**HEADERS, "Mcp-Session-Id": SESSION_ID},
        json=payload, timeout=300,
    )
    text = resp.text
    # Parse SSE response
    for line in text.split("\n"):
        if line.startswith("data: "):
            data = json.loads(line[6:])
            if "result" in data and "structuredContent" in data["result"]:
                return data["result"]["structuredContent"]
            if "result" in data:
                content = data["result"].get("content", [])
                if content and content[0].get("type") == "text":
                    return json.loads(content[0]["text"])
                return data["result"]
            if "error" in data:
                return data["error"]
    return {"raw": text}


def run_program(program, args, cwd=None, timeout=None):
    arguments = {"program": program, "args": args}
    if cwd:
        arguments["cwd"] = cwd
    if timeout:
        arguments["timeout_seconds"] = timeout
    return call("run_program", arguments)


def test(name, result, check_fn=None):
    global PASSED, FAILED
    ok = result.get("ok", False) if isinstance(result, dict) else False
    if check_fn:
        ok = check_fn(result)
    status = "PASS" if ok else "FAIL"
    if ok:
        PASSED += 1
    else:
        FAILED += 1
    # Extract key info
    detail = ""
    if isinstance(result, dict):
        if "stdout" in result:
            detail = result["stdout"][:200].replace("\n", " | ")
        elif "error" in result:
            detail = f"{result.get('error','')}: {result.get('reason','')}"
        elif "content" in result:
            detail = str(result["content"])[:200]
        elif "status" in result:
            detail = f"HTTP {result['status']}"
    try:
        print(f"{status:4} {name:50s} {detail}")
    except Exception:
        print(f"{status:4} {name:50s} (output truncated)")


def main():
    print("=" * 80)
    print("  MCP Command Bridge — Full Integration Test Suite")
    print("=" * 80)
    print()

    # === 0. Initialize ===
    init()
    print()

    # === 1. get_policy ===
    print("--- 1. Policy & System ---")
    r = call("get_policy", {})
    test("get_policy", r, lambda x: "capabilities" in x)
    
    r = call("system_snapshot", {})
    test("system_snapshot", r, lambda x: x.get("ok"))
    print()

    # === 2. Bash commands (via run_shell) ===
    print("--- 2. Bash Commands (via run_shell) ---")
    r = run_shell("echo 'Hello from container!'")
    test("run_shell echo", r, lambda x: x.get("ok") and "Hello from container" in x.get("stdout",""))

    r = run_shell("whoami && id && hostname")
    test("run_shell whoami/id/hostname", r, lambda x: x.get("ok") and "root" in x.get("stdout",""))

    r = run_shell("uname -a && cat /etc/os-release | head -3")
    test("run_shell system info", r, lambda x: x.get("ok"))

    r = run_shell("df -h / && free -m && nproc")
    test("run_shell disk/mem/cpu", r, lambda x: x.get("ok"))

    r = run_shell("ls -la /app/")
    test("run_shell ls /app", r, lambda x: x.get("ok"))

    r = run_shell("echo 'pipe test' | rev")
    test("run_shell pipe", r, lambda x: x.get("ok") and "tset" in x.get("stdout",""))

    r = run_shell("echo 'redirect test' > /app/agent_workspace/redirect_out.txt && cat /app/agent_workspace/redirect_out.txt")
    test("run_shell redirect", r, lambda x: x.get("ok") and "redirect test" in x.get("stdout",""))
    print()

    # === 2b. Chinese / UTF-8 encoding ===
    print("--- 2b. Chinese / UTF-8 Encoding ---")
    r = run_shell("echo '你好世界'")
    test("run_shell chinese echo", r, lambda x: x.get("ok") and "你好世界" in x.get("stdout",""))

    r = run_shell("echo '你好，容器！' > /app/agent_workspace/chinese.txt && cat /app/agent_workspace/chinese.txt")
    test("run_shell chinese file", r, lambda x: x.get("ok") and "你好" in x.get("stdout",""))

    r = run_shell("python3 -c \"print('中文输出测试')\"")
    test("run_shell python chinese", r, lambda x: x.get("ok") and "中文" in x.get("stdout",""))

    r = run_shell("echo 'Hello 🌍 World 🚀'")
    test("run_shell emoji", r, lambda x: x.get("ok") and "🌍" in x.get("stdout",""))
    print()

    # === 3. Python3 (via run_shell) ===
    print("--- 3. Python3 (via run_shell) ---")
    r = run_shell("python3 -c \"print('Python inline OK'); import sys; print(sys.version)\"")
    test("python3 -c inline", r, lambda x: x.get("ok") and "Python inline OK" in x.get("stdout",""))

    r = run_shell("python3 -c \"import json,os,platform; print(json.dumps({'cwd':os.getcwd(),'platform':platform.system(),'pid':os.getpid()}))\"")
    test("python3 -c json info", r, lambda x: x.get("ok"))
    print()

    # === 4. Workspace file operations ===
    print("--- 4. Workspace File Operations ---")
    r = call("write_file", {"path": "test_script.py", "content": "#!/usr/bin/env python3\nimport os, socket, platform\nprint(f'Hello from script!')\nprint(f'Host: {socket.gethostname()}')\nprint(f'OS: {platform.system()} {platform.release()}')\nprint(f'CWD: {os.getcwd()}')\nprint(f'Files: {os.listdir(\".\")}')\n", "overwrite": True})
    test("write_file test_script.py", r, lambda x: x.get("ok"))

    r = call("read_file", {"path": "test_script.py"})
    test("read_file test_script.py", r, lambda x: x.get("ok") and "Hello from script" in x.get("content",""))

    r = call("write_file", {"path": "test_node.js", "content": "console.log('Node.js script OK'); console.log('Platform:', process.platform); console.log('Node version:', process.version);\n", "overwrite": True})
    test("write_file test_node.js", r, lambda x: x.get("ok"))

    r = call("list_files", {"path": "."})
    test("list_files", r, lambda x: x.get("ok"))
    print()

    # === 5. Run scripts ===
    print("--- 5. Run Scripts ---")
    r = run_program("python3", ["agent_workspace/test_script.py"])
    test("python3 run script", r, lambda x: x.get("ok") and "Hello from script" in x.get("stdout",""))

    r = run_program("node", ["agent_workspace/test_node.js"])
    test("node run script", r, lambda x: x.get("ok") and "Node.js script OK" in x.get("stdout",""))

    r = call("run_workspace_script", {"runtime": "python3", "path": "test_script.py"})
    test("run_workspace_script python3", r, lambda x: x.get("ok"))
    print()

    # === 6. pip install / uninstall (via run_shell) ===
    print("--- 6. pip Install / Uninstall (via run_shell) ---")
    r = run_shell("pip install requests", timeout=120)
    test("pip install requests", r, lambda x: x.get("ok"))

    r = run_shell("python3 -c 'import requests; print(\"requests version:\", requests.__version__)'")
    test("python3 import requests", r, lambda x: x.get("ok") and "requests version" in x.get("stdout",""))

    r = run_shell("pip uninstall -y requests", timeout=60)
    test("pip uninstall requests", r, lambda x: x.get("ok"))

    r = run_shell("python3 -c \"try:\n    import requests\n    print('STILL INSTALLED')\nexcept ImportError:\n    print('UNINSTALLED OK')\"")
    test("python3 verify uninstalled", r, lambda x: x.get("ok") and "UNINSTALLED OK" in x.get("stdout",""))
    print()

    # === 7. apt-get install / remove (via run_shell) ===
    print("--- 7. apt-get Install / Remove (via run_shell) ---")
    r = run_shell("which jq || echo 'jq not installed'")
    test("check jq before install", r, lambda x: x.get("ok"))

    r = run_shell("apt-get update", timeout=120)
    test("apt-get update", r, lambda x: x.get("ok"))

    r = run_shell("apt-get install -y jq", timeout=120)
    test("apt-get install jq", r, lambda x: x.get("ok"))

    r = run_shell('echo \'{"key":"value"}\' | jq .key')
    test("jq works", r, lambda x: x.get("ok") and "value" in x.get("stdout",""))

    r = run_shell("apt-get remove -y jq", timeout=60)
    test("apt-get remove jq", r, lambda x: x.get("ok"))

    r = run_shell("which jq && echo 'STILL INSTALLED' || echo 'REMOVED OK'")
    test("verify jq removed", r, lambda x: x.get("ok") and "REMOVED OK" in x.get("stdout",""))
    print()

    # === 8. git clone (via run_shell) ===
    print("--- 8. Git Clone (via run_shell) ---")
    r = run_shell("git clone https://github.com/octocat/Hello-World.git /app/projects/Hello-World", timeout=60)
    test("git clone Hello-World", r, lambda x: x.get("ok"))

    r = run_shell("ls /app/projects/Hello-World/ && cat /app/projects/Hello-World/README")
    test("verify clone contents", r, lambda x: x.get("ok"))

    r = run_shell("cd /app/projects/Hello-World && git log --oneline -3")
    test("git log in clone", r, lambda x: x.get("ok"))
    print()

    # === 9. Network tools ===
    print("--- 9. Network Tools ---")
    r = call("http_probe", {"url": "https://api.github.com/"})
    test("http_probe api.github.com", r, lambda x: x.get("ok") and x.get("status") == 200)

    r = call("ping_host", {"host": "8.8.8.8", "count": 2})
    test("ping_host 8.8.8.8", r, lambda x: x.get("ok"))

    r = call("dns_lookup", {"host": "github.com"})
    test("dns_lookup github.com", r, lambda x: x.get("ok") and len(x.get("addresses",[])) > 0)

    r = call("tcp_probe", {"host": "github.com", "port": 443})
    test("tcp_probe github.com:443", r, lambda x: x.get("ok") and x.get("open"))
    print()

    # === 10. curl (via run_shell) ===
    print("--- 10. curl (via run_shell) ===")
    r = run_shell('curl -s -o /dev/null -w "%{http_code}" https://www.baidu.com/')
    test("curl baidu status", r, lambda x: x.get("ok") and "200" in x.get("stdout",""))

    r = run_shell("curl -s https://api.github.com/")
    test("curl api.github.com", r, lambda x: x.get("ok"))
    print()

    # === 11. File persistence & audit trail ===
    print("--- 11. File Persistence & Audit Trail ---")
    r = call("write_file", {"path": "persistence_test.txt", "content": f"Persistence test at {time.time()}\nThis file should be visible on the host at data/workspace/\n", "overwrite": True})
    test("write persistence_test.txt", r, lambda x: x.get("ok"))

    r = call("append_file", {"path": "persistence_test.txt", "content": "Appended line — check host data/workspace/persistence_test.txt\n"})
    test("append to persistence_test.txt", r, lambda x: x.get("ok"))

    r = call("read_file", {"path": "persistence_test.txt"})
    test("read persistence_test.txt", r, lambda x: x.get("ok") and "Appended line" in x.get("content",""))

    # Verify audit log is accessible and contains run_shell entries
    r = call("read_file", {"path": "../logs/audit.jsonl"})
    test("audit log readable", r, lambda x: x.get("ok") and "run_shell" in x.get("content",""))
    print()

    # === Summary ===
    print("=" * 80)
    total = PASSED + FAILED
    print(f"  Results: {PASSED} passed, {FAILED} failed, {total} total")
    if FAILED == 0:
        print("  ALL TESTS PASSED!")
    else:
        print(f"  {FAILED} test(s) failed — review above")
    print("=" * 80)
    
    sys.exit(0 if FAILED == 0 else 1)


if __name__ == "__main__":
    main()
