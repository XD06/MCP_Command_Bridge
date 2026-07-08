import urllib.request
import json

url = "https://integrate.api.nvidia.com/v1/chat/completions"
headers = {
    "Authorization": "Bearer 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",
    "Content-Type": "application/json"
}
payload = {
    "model": "meta/llama-3.2-1b-instruct",
    "messages": [
        {"role": "user", "content": "Hello, how are you?"}
    ],
    "max_tokens": 50
}

req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.load(resp)
        print("Status:", resp.status)
        print("Response:", json.dumps(data, indent=2))
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.reason)
    print("Body:", e.read().decode())
except Exception as e:
    print("Error:", str(e))
