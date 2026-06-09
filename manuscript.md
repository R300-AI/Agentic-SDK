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
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"                                                                           
[demo_multi_backend] prompt = '請用一句話自我介紹'
[demo_multi_backend] ryzen_base = http://127.0.0.1:8000/v1
[demo_multi_backend] ryzen_model = gemma-3-4b-it

────────────────────────────────────────────────────────────
  Ryzen    backend  : FAIL
           error   : RuntimeError: Ryzen 端點有回應,但 model 'gemma-3-4b-it' 不在可用清單中。
可用 models: ['gemma3-4b-npu']
請確認 api.py --model 參數與 RYZEN_MODEL 是否一致。

  Foundry  backend  : FAIL
           error   : OSError: .env 缺少必填項目: AZURE_FOUNDRY_ENDPOINT, AZURE_FOUNDRY_API_KEY。請複製 .env.example 並填入 Azure Foundry 憑證後重跑。
────────────────────────────────────────────────────────────
  report saved   -> docs\quickstart-runs\multi-backend-20260609T092525Z.json
  both backends  : PARTIAL / FAIL
────────────────────────────────────────────────────────────
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> 
```

# 4. 推結果回來給我看