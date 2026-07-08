"""NVIDIA API (OpenAI 兼容格式) 完整测试"""
import json, urllib.request, urllib.error, ssl

API_KEY = "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"
BASE_URL = "https://integrate.api.nvidia.com"
ssl_ctx = ssl.create_default_context()

def make_request(method, path, data=None, custom_headers=None):
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}
    if custom_headers:
        headers.update(custom_headers)
    body = json.dumps(data).encode("utf-8") if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, {"error": e.read().decode("utf-8", errors="replace")}
    except Exception as e:
        return 0, {"error": str(e)}

def safe_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)

def main():
    print("=" * 70)
    print("NVIDIA API (OpenAI 兼容格式) 完整测试报告")
    print("=" * 70)

    # --- 1. 列出模型 ---
    print("\n[1] GET /v1/models - 列出可用模型")
    status, data = make_request("GET", "/v1/models")
    print(f"    状态码: {status}")
    if status == 200:
        models = data.get("data", [])
        print(f"    模型总数: {len(models)}")
        print(f"    前15个模型:")
        for m in models[:15]:
            print(f"      - {m['id']} (owned_by: {m.get('owned_by','?')})")
        if len(models) > 15:
            print(f"      ... 还有 {len(models)-15} 个")
    else:
        print(f"    失败: {safe_json(data)[:500]}")

    # --- 2. 中文对话 ---
    print("\n[2] POST /v1/chat/completions - 中文对话")
    chat_body = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": "你是一个中文助手，请用中文回答。"},
            {"role": "user", "content": "你好！请问英伟达（NVIDIA）是哪家公司？用三句话简单介绍。"}
        ],
        "temperature": 0.7,
        "max_tokens": 300
    }
    status, data = make_request("POST", "/v1/chat/completions", chat_body)
    print(f"    状态码: {status}")
    if status == 200:
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        print(f"    使用模型: {data.get('model', '?')}")
        print(f"    回复内容: {content}")
        print(f"    Token用量: prompt={usage.get('prompt_tokens')} completion={usage.get('completion_tokens')} total={usage.get('total_tokens')}")
    else:
        print(f"    失败: {safe_json(data)[:500]}")

    # --- 3. 多模型测试 ---
    print("\n[3] 测试多个不同模型")
    models_tested = [
        ("mistralai/mistral-7b-instruct-v0.3", "mistral"),
        ("google/gemma-2-27b-it", "gemma"),
        ("deepseek-ai/deepseek-coder-6.7b-instruct", "deepseek coder"),
    ]
    for model_name, label in models_tested:
        body = {
            "model": model_name,
            "messages": [{"role": "user", "content": "Hello! Reply in 5 words max."}],
            "max_tokens": 30
        }
        status, data = make_request("POST", "/v1/chat/completions", body)
        if status == 200:
            msg = data["choices"][0]["message"]["content"]
            print(f"    [+] {label} ({model_name}): {msg[:80]}")
        else:
            print(f"    [X] {label} ({model_name}): HTTP {status}")

    # --- 4. Embedding ---
    print("\n[4] POST /v1/embeddings - Embedding 功能")
    embed_body = {"model": "baai/bge-m3", "input": "Hello world"}
    status, data = make_request("POST", "/v1/embeddings", embed_body)
    if status == 200:
        emb = data.get("data", [{}])[0].get("embedding", [])
        print(f"    [+] 可用! 向量维度: {len(emb)}")
    else:
        print(f"    [X] 不可用: {safe_json(data)[:200]}")

    # --- 5. 错误API Key ---
    print("\n[5] 错误API Key 测试")
    bad_headers = {"Authorization": "Bearer bad_key"}
    status, data = make_request("GET", "/v1/models", custom_headers=bad_headers)
    print(f"    状态码: {status}")
    err_str = safe_json(data)[:300]
    print(f"    错误信息: {err_str}")

    print("\n" + "=" * 70)
    print("全部测试完成!")
    print("=" * 70)

if __name__ == "__main__":
    main()
