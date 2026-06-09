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

# 4. 推結果回來給我看
git checkout -b verify/m4-multi-backend-$(Get-Date -Format yyyyMMdd)
git add docs\quickstart-runs\multi-backend-*.json
git commit -m "M4 multi-backend verification run"
git push origin HEAD