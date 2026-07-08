import urllib.request
import json
import sys

url = "https://integrate.api.nvidia.com/v1/models"
headers = {
    "Authorization": "Bearer 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"
}

req = urllib.request.Request(url, headers=headers)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.load(resp)
        print("Status:", resp.status)
        print("Data:", json.dumps(data, indent=2))
except urllib.error.HTTPError as e:
    print("HTTP Error:", e.code, e.reason)
    print("Body:", e.read().decode())
except Exception as e:
    print("Error:", str(e))
