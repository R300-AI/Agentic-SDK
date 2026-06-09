# 1. 起 Gemma3 上游
conda activate ryzen-ai-1.7.1
cd <amd-ryzen-ai-benchmark>
python api.py --model gemma-3-4b-it

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
[demo_multi_backend] ryzen_model = gemma-3-4b-it
action upstream call failed: Internal Server Error
action upstream call failed: Internal Server Error
workflow aborted: node 'plan' 重訪次數 3 已達上限 3

────────────────────────────────────────────────────────────
  Ryzen    backend  : FAIL
           error   : None None
           abort   : node 'plan' 重訪次數 3 已達上限 3

  Foundry  backend  : FAIL
           error   : KeyError 'AZURE_FOUNDRY_ENDPOINT'
           abort   : None
────────────────────────────────────────────────────────────
  report saved   -> docs\quickstart-runs\multi-backend-20260609T090841Z.json
  both backends  : PARTIAL / FAIL
────────────────────────────────────────────────────────────
(base) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> 
```

# 4. 推結果回來給我看