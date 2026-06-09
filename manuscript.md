# 1. 起 Gemma3 上游
conda activate ryzen-ai-1.7.1
cd <amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu

# 2. clone / pull Agentic SDK 最新版
git clone https://github.com/<your-org>/Agentic-SDK.git   # 或 git pull
cd Agentic-SDK
git submodule update --init
uv sync --extra dev
Copy-Item .env.example .env
# 編輯 .env 填 AZURE_FOUNDRY_ENDPOINT / AZURE_FOUNDRY_API_KEY / AZURE_FOUNDRY_DEPLOYMENT

# 3. 跑多基台 demo
uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"

```result
(base) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"
[demo_multi_backend] prompt = '請用一句話自我介紹'
[demo_multi_backend] ryzen_base = http://127.0.0.1:8000/v1
[demo_multi_backend] ryzen_model = gemma3-4b-npu
[demo_multi_backend] ryzen preflight OK — models: ['gemma3-4b-npu']

────────────────────────────────────────────────────────────
  Ryzen    backend  : OK
           reply   : '我是一個 Agentic SDK 內的 Action 節點，目前正在等待真實向量檢索結果，稍後會用一句話自我介紹。'
           elapsed : 5.938 s

  Foundry  backend  : OK
           reply   : '我是 ChatGPT，一個可以用文字協助你解答問題、整理資訊並完成各種任務的 AI 助手。'
           elapsed : 2.031 s
────────────────────────────────────────────────────────────
  report saved   -> docs\quickstart-runs\multi-backend-20260609T095312Z.json
  both backends  : OK
────────────────────────────────────────────────────────────
(base) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> 
```

# 4. 推結果回來給我看