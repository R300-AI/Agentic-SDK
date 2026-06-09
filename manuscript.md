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
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> uv run python scripts\demo_multi_backend.py "請用一句話自我介紹"
[demo_multi_backend] prompt = '請用一句話自我介紹'
[demo_multi_backend] ryzen_base = http://127.0.0.1:8000/v1
[demo_multi_backend] ryzen_model = gemma-3-4b-it

────────────────────────────────────────────────────────────
  Ryzen    backend  : FAIL
           error   : ImportError cannot import name 'UpstreamCompletionAction' from partially initialized module 'agentic_sdk.workflow.nodes.action' (most likely due to a circular import) (C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK\agentic_sdk\workflow\nodes\action\__init__.py)
           abort   : None

  Foundry  backend  : FAIL
           error   : ImportError cannot import name 'UpstreamCompletionAction' from partially initialized module 'agentic_sdk.workflow.nodes.action' (most likely due to a circular import) (C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK\agentic_sdk\workflow\nodes\action\__init__.py)
           abort   : None
────────────────────────────────────────────────────────────
  report saved   -> docs\quickstart-runs\multi-backend-20260609T085724Z.json
  both backends  : PARTIAL / FAIL
────────────────────────────────────────────────────────────
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> git checkout -b verify/m4-multi-backend-$(Get-Date -Format yyyyMMdd)
Switched to a new branch 'verify/m4-multi-backend-20260609'
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> git add docs\quickstart-runs\multi-backend-*.json
(base) (agentic-sdk) PS C:\Users\eosl1\OneDrive\文件\GitHub\Agentic-SDK> git commit -m "M4 multi-backend verification run"
[verify/m4-multi-backend-20260609 91dacc9] M4 multi-backend verification run
 1 file changed, 26 insertions(+)
 create mode 100644 docs/quickstart-runs/multi-backend-20260609T085724Z.json
```

# 4. 推結果回來給我看