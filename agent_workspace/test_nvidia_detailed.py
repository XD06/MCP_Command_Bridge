#!/usr/bin/env python3
"""NVIDIA API 详细功能测试"""
import json
import urllib.request
import urllib.error
import ssl
import sys
import io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

API_KEY = "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"
BASE_URL = "https://integrate.api.nvidia.com"
ssl_ctx = ssl.create_default_context()

def make_request(method, path, data=None, extra_headers=None):
    url = f"{BASE_URL}{path}"
    headers = {"Authorization": f"Bearer {API_KEY}"}
    if extra_headers:
        headers.update(extra_headers)
    
    data_bytes = json.dumps(data).encode("utf-8") if data else None
    if data:
        headers["Content-Type"] = "application/json"
    
    req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, context=ssl_ctx, timeout=30) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
            return resp.status, response_data, dict(resp.headers)
    except urllib.error.HTTPError as e:
        error_body = e.read().decode("utf-8", errors="replace")
        return e.code, {"error": error_body}, dict(e.headers)
    except Exception as e:
        return 0, {"error": str(e)}, {}

def safe_json(obj):
    return json.dumps(obj, indent=2, ensure_ascii=False)

def main():
    print("=" * 70)
    print("NVIDIA API (OpenAI 兼容格式) 详细测试报告")
    print("=" * 70)
    
    # ========== Test 1: List models ==========
    print("\n[测试1] GET /v1/models - 列出可用模型")
    status, data, headers = make_request("GET", "/v1/models")
    print(f"   状态码: {status}")
    if status == 200:
        models = data.get("data", [])
        print(f"   模型数量: {len(models)} 个")
        print(f"   前20个模型:")
        for m in models[:20]:
            owned_by = m.get("owned_by", "?")
            print(f"     [+] {m['id']} (by {owned_by})")
        if len(models) > 20:
            print(f"     ... 还有 {len(models)-20} 个模型")
    else:
        print(f"   失败: {safe_json(data)[:500]}")
    
    # ========== Test 2: Chinese chat ==========
    print("\n[测试2] POST /v1/chat/completions - 中文对话")
    chat_body = {
        "model": "meta/llama-3.1-70b-instruct",
        "messages": [
            {"role": "system", "content": "你是一个中文助手，请用中文回答。"},
            {"role": "user", "content": "你好！请问英伟达（NVIDIA）是哪家公司？用三句话简单介绍。"}
        ],
        "temperature": 0.7,
        "max_tokens": 300,
        "top_p": 0.95
    }
    status, data, headers = make_request("POST", "/v1/chat/completions", chat_body)
    print(f"   状态码: {status}")
    if status == 200:
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage", {})
        model_used = data.get("model", "unknown")
        print(f"   使用模型: {model_used}")
        print(f"   回复内容: {content}")
        print(f"   Token用量: 输入={usage.get('prompt_tokens')} 输出={usage.get('completion_tokens')} 总计={usage.get('total_tokens')}")
        print(f"   响应ID: {data.get('id', 'N/A')}")
    else:
        print(f"   失败: {safe_json(data)[:500]}")

    # ========== Test 3: Different models ==========
    print("\n[测试3] 尝试多个模型")
    models_to_try = [
        "mistralai/mistral-7b-instruct-v0.3",
        "google/gemma-2-27b-it",
        "deepseek-ai/deepseek-coder-6.7b-instruct",
    ]
    for model in models_to_try:
        body = {
            "model": model,
            "messages": [{"role": "user", "content": "Say 'hello' in one word."}],
            "max_tokens": 20
        }
        status, data, _ = make_request("POST", "/v1/chat/completions", body)
        if status == 200:
            content = data["choices"][0]["message"]["content"]
            print(f"   [+] {model}: {content[:80]}")
        else:
            err = safe_json(data)[:200]
            print(f"   [X] {model}: HTTP {status} - {err}")

    # ========== Test 4: Embeddings ==========
    print("\n[测试4] POST /v1/embeddings (Embedding 功能)")
    embed_body = {
        "model": "baai/bge-m3",
        "input": "Hello world",
    }
    status, data, _ = make_request("POST", "/v1/embeddings", embed_body)
    if status == 200:
        emb_len = len(data.get("data", [{}])[0].get("embedding", []))
        print(f"   可用! Embedding维度: {emb_len}")
    else:
        print(f"   不可用: {safe_json(data)[:200]}")
    
    # ========== Test 5: Error handling ==========
    print("\n[测试5] 错误处理（无效API Key）")
    bad_headers = {"Authorization": "Bearer invalid_key"}
    status, data, _ = make_request("GET", "/v1/models", extra_headers=bad_headers)
    print(f"   状态码: {status}")
    print(f"   错误信息: {safe_json(data)[:300]}")
    
    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)

if __name__ == "__main__":
    main()
