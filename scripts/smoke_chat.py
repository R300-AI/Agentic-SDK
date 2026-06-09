"""一鍵 smoke test:呼叫本機 Gateway 的 /v1/chat/completions 並印出回應與遙測 metadata。

預設指向 http://127.0.0.1:8080,使用 OpenAI SDK(相容介面)。
適合本機驗證 WORKFLOW_ACTION_BACKEND=foundry 是否能端到端跑通。

用法:
    uv run python scripts\\smoke_chat.py
    uv run python scripts\\smoke_chat.py "你想問的問題"
"""

from __future__ import annotations

import json
import os
import sys

from openai import OpenAI


def main() -> int:
    base_url = os.environ.get("AGENTIC_GATEWAY_BASE_URL", "http://127.0.0.1:8080/v1")
    prompt = sys.argv[1] if len(sys.argv) > 1 else "用一句話介紹潔淨架構的核心原則。"

    client = OpenAI(base_url=base_url, api_key="local")
    raw = client.with_raw_response.chat.completions.create(
        model="agentic-sdk",
        messages=[{"role": "user", "content": prompt}],
    )
    completion = raw.parse()
    metadata_header = raw.http_response.headers.get("x-agentic-metadata")

    print(f"=== Gateway: {base_url} ===")
    print(f"=== Prompt ===\n{prompt}\n")
    print("=== Response ===")
    print(completion.choices[0].message.content or "(empty)")
    print()
    if metadata_header:
        try:
            meta = json.loads(metadata_header)
            print("=== x-agentic-metadata ===")
            print(json.dumps(meta, indent=2, ensure_ascii=False))
        except json.JSONDecodeError:
            print(f"=== x-agentic-metadata(raw)===\n{metadata_header}")
    if completion.usage:
        print(f"\n=== Usage ===\nprompt={completion.usage.prompt_tokens} "
              f"completion={completion.usage.completion_tokens}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
