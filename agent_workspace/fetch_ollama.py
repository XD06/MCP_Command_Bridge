import urllib.request
import json

url = "https://api.ollama.com/v1/models"
try:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = resp.read().decode('utf-8')
        # 尝试格式化 JSON
        try:
            parsed = json.loads(data)
            print(json.dumps(parsed, indent=2, ensure_ascii=False))
        except:
            print(data)
except Exception as e:
    print(f"请求失败: {e}")
