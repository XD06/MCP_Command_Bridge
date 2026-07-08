import urllib.request
import urllib.error

url = "https://www.bing.com"
try:
    req = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(req, timeout=10) as resp:
        print(f"Status: {resp.status} {resp.reason}")
        print(f"Bing 连通成功！")
except urllib.error.URLError as e:
    print(f"连接失败: {e.reason}")
except Exception as e:
    print(f"错误: {e}")
