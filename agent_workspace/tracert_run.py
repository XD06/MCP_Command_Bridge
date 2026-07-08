import subprocess
import sys

target = sys.argv[1] if len(sys.argv) > 1 else "8.8.8.8"
print(f"正在对 {target} 执行路由追踪...\n")

try:
    # Windows 上用 tracert，缩短等待时间
    result = subprocess.run(
        ["tracert", "-d", "-h", "20", "-w", "2000", target],
        capture_output=True,
        text=True,
        timeout=45
    )
    print(result.stdout)
    if result.stderr:
        print("错误信息:", result.stderr)
except FileNotFoundError:
    try:
        result = subprocess.run(
            ["traceroute", "-n", "-m", "20", target],
            capture_output=True,
            text=True,
            timeout=45
        )
        print(result.stdout)
    except FileNotFoundError:
        print("系统中未找到 tracert 或 traceroute 命令")
except subprocess.TimeoutExpired:
    print("路由追踪超时（可能是权限问题）")
except Exception as e:
    print(f"执行出错: {e}")
