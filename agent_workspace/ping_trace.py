import subprocess
import sys
import re

target = sys.argv[1] if len(sys.argv) > 1 else "8.8.8.8"
print(f"通过递增 TTL 探测到 {target} 的路由...\n")
print(f"{'跳数':>4}  {'IP地址':<20} {'延迟':<10}")
print("-" * 40)

for ttl in range(1, 31):
    try:
        # Windows ping -i 设置 TTL
        result = subprocess.run(
            ["ping", "-n", "1", "-i", str(ttl), "-w", "1500", target],
            capture_output=True,
            text=True,
            timeout=5
        )
        output = result.stdout
        
        # 提取 IP 地址
        ip_match = re.search(r'来自 (\d+\.\d+\.\d+\.\d+) 的回复', output)
        time_match = re.search(r'时间[=<](\d+)ms', output)
        
        if ip_match:
            ip = ip_match.group(1)
            time_str = time_match.group(1) + " ms" if time_match else "?"
            print(f"  {ttl:2d}.  {ip:<20} {time_str:<10}")
            
            if ip == target:
                print(f"\n✅ 到达目标 {target}")
                break
        elif "TTL 过期" in output or "超时" in output:
            # TTL 过期说明经过了该路由但没返回 ping
            # 提取"来自"的地址
            from_match = re.search(r'来自 (\d+\.\d+\.\d+\.\d+)', output)
            if from_match:
                print(f"  {ttl:2d}.  {from_match.group(1):<20} 超时")
            else:
                print(f"  {ttl:2d}.  * * *  (超时)")
        elif "请求超时" in output:
            print(f"  {ttl:2d}.  * * *  (请求超时)")
        elif "无法访问目标" in output:
            print(f"  {ttl:2d}.  * * *  (无法访问)")
        else:
            print(f"  {ttl:2d}.  * * *")
            
    except subprocess.TimeoutExpired:
        print(f"  {ttl:2d}.  * * *  (超时)")
    except Exception as e:
        print(f"  {ttl:2d}.  * * *  (错误: {e})")

print("\n探测完成")
