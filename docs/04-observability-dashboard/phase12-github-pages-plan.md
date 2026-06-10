# M12（Phase 12）CI 自動化測試 + 編輯器上架 GitHub Pages 計畫

> 受眾：M12 開發者、決策層
> 目的：(1) 建立 GitHub Actions CI 保護 main branch；(2) 把 `demo/` 變成可公開瀏覽的 demo 站，降低潛在使用者的評估門檻。
> 對應 milestone：[blueprint/milestones.md M12](../../blueprint/milestones.md#m12)
> **前提（已確認）**：repo 遷移至 `R300-AI` org，使用 **GitHub Team** plan，Private repo Pages 已支援。Pages URL：`https://R300-AI.github.io/Agentic-SDK/`。
> 
> **API Key 架構說明**：GH Pages 是純靜態站，本身不持有任何金鑰。使用者在自己本機的 `.env` 填入 Foundry API Key，由本機 Gateway 代為呼叫 Foundry；瀏覽器只對 `http://localhost:8080` 發請求，金鑰不流經 GH Pages 也不需要上傳到 repo。

---

## 一、為什麼是 GitHub Pages 而不是雲端代管

| 候選 | 優點 | 不採用的原因 |
|------|------|--------------|
| **GitHub Pages（採用）** | 與 repo 同生命週期、免費、CI 內建、HTTPS 內建 | — |
| Vercel / Netlify | 自動 preview、邊緣節點 | 需額外帳號治理，跨組織授權路徑長 |
| Azure Static Web Apps | 與 Foundry 同生態 | 為了一個前端編輯器引入 Azure 帳號繫結，過重 |
| 自架 Nginx | 完全可控 | 維運成本與本專案 PoC 階段不相稱 |

**結論**：GitHub Pages 是 PoC / 開源評估階段最低摩擦的選擇。MVP 後若需自訂域名、SSO，再評估遷移。

---

## 二、職責邊界（與 Gateway 的關係）

```
┌──────────────────────────┐         ┌─────────────────────────┐
│  GitHub Pages（靜態）    │         │  本機 Gateway（8080）   │
│  - React + Vite 編輯器   │  CORS   │  - /v1/workflow/run     │
│  - 畫布拖曳、屬性面板    │ ◄─────► │  - /v1/workflow/.../stream │
│  - YAML 下載 / Python 匯出│         │  - /v1/workflow/.../result │
└──────────────────────────┘         └─────────────────────────┘
       使用者瀏覽器                          使用者自己跑
```

**GH Pages 不代管 Gateway**。Gateway 是有狀態服務（持有 Memory Stream、Active Context、Foundry credentials），不適合放公網。使用者打開編輯器後，於 header 欄位填入自己本機 Gateway URL（預設 `http://127.0.0.1:8080`），瀏覽器直接打到本機；Pages 端不轉發任何業務請求。

這條設計同時規避了三件麻煩：
1. 不需要本專案代管 Foundry key
2. 不需要對 GH Pages 做網路代理或 reverse proxy
3. 使用者資料（YAML、對話內容、附件）不流經第三方

---

## 三、六個子項拆解

### M12-0：CI 自動化測試（可立即實作，無前置條件）

這是 M12 中唯一**不受 repo 可見度影響**的子項：GitHub Actions 在 Private repo 的免費方案下也能運行。

**改動**：新增 `.github/workflows/ci.yml`

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  test-python:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with: { python-version: "3.12" }
      - run: uv sync --extra dev
      - name: Run pytest
        env:
          WORKFLOW_FORCE_MOCK_FOUNDRY: "true"
          WORKFLOW_ACTION_BACKEND: "foundry"
          AZURE_FOUNDRY_ENDPOINT: "https://mock.example.com/"
          AZURE_FOUNDRY_API_KEY: "mock-key"
          AZURE_FOUNDRY_DEPLOYMENT: "mock-deployment"
        run: uv run pytest tests --ignore=tests/test_dashboard_app.py

  check-typescript:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - working-directory: demo
        run: |
          npm ci
          npx tsc --noEmit
```

**設計決策**：
- `WORKFLOW_FORCE_MOCK_FOUNDRY=true`：所有測試走 MockFoundryClient，無需儲存真實 Foundry 金鑰於 GitHub Secrets
- `--ignore=tests/test_dashboard_app.py`：Streamlit 在 headless CI 環境需額外設定，暫時排除；其餘 158 項全跑
- `astral-sh/setup-uv@v5`：官方 uv action，自動處理 Python 版本與 cache
- `tsc --noEmit`：只做型別檢查，不實際 build，速度快（約 10 秒）
- `prestart` PowerShell hook **不會在 CI 執行**（只在 `npm start` 時觸發，`npm ci` 與 `tsc` 不觸發）

### M12-1：Vite `base` 子路徑化

GH Pages 的 URL 形態為 `https://<owner>.github.io/<repo>/`。Vite 需要在 build 時知道 asset 的 base path，否則 `index.html` 內的 `/assets/...` 連結會 404。

**改動**：

```ts
// demo/vite.config.ts
export default defineConfig({
  base: process.env.VITE_BASE ?? "/",
  // ... 其餘不變
});
```

CI 部署時設 `VITE_BASE=/Agentic-SDK/`，本機 `npm run dev` 與 `vite build` 不設則保持 `/`。

### M12-2：Runtime Gateway URL 設定

當前 [demo/src/runtime/api.ts](../../demo/src/runtime/api.ts) hardcode `fetch("/v1/workflow/run")`，依賴 Vite dev proxy 把 `/v1/workflow` 轉發到 `http://localhost:8080`。上 GH Pages 後沒有 dev proxy，必須讓使用者自己指 Gateway URL。

> ⚠️ **Mixed Content 問題（重要）**：GH Pages 是 HTTPS，使用者本機 Gateway 是 HTTP。瀏覽器預設會阻擋 HTTPS 頁面對 HTTP 端點的請求（Mixed Content），但有一個例外：`http://localhost`（含 `http://localhost:PORT`）在 Chrome 94+ 與 Firefox 被視為 Potentially Trustworthy Origin，允許從 HTTPS 發起。**`http://127.0.0.1` 不在此例外清單**。
>
> 因此：預設 Gateway URL 必須是 `http://localhost:8080`，不能用 `http://127.0.0.1:8080`；UI 提示文字也應強調使用 `localhost`。

**改動**：

1. `demo/src/runtime/gatewayUrl.ts`（新檔）— 讀寫 `localStorage`，預設 `http://localhost:8080`
2. `demo/src/runtime/api.ts` 改用 `getGatewayUrl()` 拼接
3. `demo/src/App.tsx` 加 header 一行「Gateway URL: [input]」，blur 時寫回 localStorage

### M12-3：Gateway CORS 白名單

瀏覽器從 `https://<owner>.github.io` 打 `http://127.0.0.1:8080` 屬於跨域，需要 Gateway 回正確的 `Access-Control-Allow-Origin`。

**改動**：

```python
# agentic_sdk/config.py
class Settings(BaseSettings):
    gateway_cors_origins: list[str] = ["http://localhost:5173"]
```

```python
# agentic_sdk/gateway/app.py
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.gateway_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)
```

使用者於 `.env` 加：

```ini
GATEWAY_CORS_ORIGINS=["http://localhost:5173","https://R300-AI.github.io"]
```

### M12-4：GitHub Pages 部署 workflow

> repo 已在 `R300-AI` org（GitHub Team plan），private repo Pages 已支援，無需額外前置。

```yaml
# .github/workflows/deploy-pages.yml
name: Deploy demo to GitHub Pages

on:
  push:
    branches: [main]
    paths:
      - "demo/**"
      - ".github/workflows/deploy-pages.yml"

permissions:
  contents: read
  pages: write
  id-token: write

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: "22" }
      - working-directory: demo
        run: |
          npm ci
          VITE_BASE=/Agentic-SDK/ npm run build
      - uses: actions/upload-pages-artifact@v3
        with: { path: demo/dist }
  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
```

**前置**：repo Settings → Pages → Source 改為「GitHub Actions」。

### M12-5：「無 Gateway 也能瀏覽」降級提示

當使用者只想看編輯器長什麼樣、不打算啟 Gateway 時，應允許：

- 畫布拖曳、屬性編輯、YAML 下載、Python 匯出（全部不需要後端）

不允許：

- 「跑一次」按下後，fetch 失敗 → 顯示一條淺色提示「請在本機啟動 Gateway 並於上方填入 `http://localhost:8080`」，不要紅色錯誤訊息淹沒對話框

`runtime/api.ts` 的 `runWorkflow` 在 `TypeError`（CORS 或 ECONNREFUSED）時拋自定義錯誤類型，`App.tsx` 識別後渲染降級提示。

---

## 四、不在 M12 範圍

明確記錄避免日後 scope creep：

- ❌ Pages 端代管 Gateway / 任何 Python 後端
- ❌ 多人協作、線上儲存 YAML（YAML 仍只存使用者本機）
- ❌ Auth / OIDC / SSO（公開頁，不收 user credentials）
- ❌ 自訂域名（用 GH Pages 預設 domain；MVP 後再評估）
- ❌ Mobile / 觸控優化（編輯器假設桌機鍵鼠）
- ❌ `test_dashboard_app.py` 納入 CI（Streamlit 在 headless CI 需額外設定，留待下一個 phase）

---

## 五、驗收 checklist

完成時應全部通過：

**M12-0（CI）**
1. push 到 main 後 Actions 頁面出現 `CI` workflow，`test-python` 與 `check-typescript` 兩個 job 均綠燈
2. PR 頁面顯示 CI status check，未通過不能合併
3. README.md 加上 CI badge

**M12-1~M12-5（GitHub Pages，前提：org 升級至 Team 或 repo 設為 public）**
4. `https://R300-AI.github.io/Agentic-SDK/` 開得起來，畫布顯示預設五節點
5. header 的 Gateway URL 預設值是 `http://localhost:8080`，改值後 fetch 路徑對應變更
6. 本機未起 Gateway 時點「跑一次」→ 顯示引導訊息，畫布不崩
7. 本機起 Gateway + `.env` 加 `GATEWAY_CORS_ORIGINS` 後 → 跑一次 → SSE delta 逐字渲染、節點亮燈、最終訊息正確
8. `.github/workflows/deploy-pages.yml` 於 main push 後 Actions 綠燈
9. 改 `demo/` 任意檔 commit → 部署於 ≤ 5 分鐘內反映於 Pages

---

## 六、可行性分析與已知問題

### 6.1 GitHub Actions CI（M12-0）— ✅ 立即可行

| 檢查項 | 結論 |
|--------|------|
| Private repo 支援 Actions | ✅ 免費方案支援 |
| Python 依賴乾淨（無 torch / onnx） | ✅ 只需 fastapi / uvicorn / pydantic / openai / httpx / streamlit |
| 測試需要 Foundry 金鑰 | ✅ 全程 mock（`WORKFLOW_FORCE_MOCK_FOUNDRY=true`），不需 Secrets |
| `prestart` PowerShell hook 在 CI 執行 | ✅ 不會觸發（只在 `npm start`，不在 `npm ci` 或 `tsc`） |
| `package-lock.json` 存在 | ✅ `npm ci` 可直接用 |
| TypeScript 型別檢查在 Ubuntu | ✅ `tsc --noEmit` 無平台依賴 |

### 6.2 GitHub Pages（M12-1~M12-5）— ⚠️ 有前提條件

#### 前提：Private repo 與 Pages 的限制

| 方案 | 可行性 | 說明 |
|------|--------|------|
| **`R300-AI` org，GitHub Team（已採用）** | ✅ 已確認 | Private repo Pages 已支援；Actions 額度充足 |
| **將 repo 設為 Public** | ✅ 可行 | 免費；但原始碼公開，需確認沒有機密資訊（`.env` 已 gitignore）|
| **延後到決定 repo 策略** | ✅ 可行 | M12-0 CI 先做；M12-1~M12-5 擱置到 repo 升級/公開 |
| 換靜態托管（Vercel/Netlify） | ⚠️ 可評估 | 支援 private repo；但引入第三方帳號治理 |

#### 技術問題：Mixed Content（HTTPS → HTTP）

GH Pages 是 HTTPS 站。瀏覽器對「HTTPS 頁面發起 HTTP 請求」的規則：

| 目標 Host | Chrome 行為 | Firefox 行為 |
|-----------|-------------|--------------|
| `http://localhost:PORT` | ✅ 允許（Potentially Trustworthy） | ✅ 允許 |
| `http://127.0.0.1:PORT` | ❌ 阻擋（Mixed Content） | ❌ 阻擋 |
| `http://任意 IP` | ❌ 阻擋 | ❌ 阻擋 |

**結論**：M12-2 的 Gateway URL 預設值與 UI 提示必須一律使用 `localhost`，不能用 `127.0.0.1`。使用者若要連遠端 Gateway（非 localhost），需在啟動 Gateway 時加上 TLS（超出 M12 範圍）。

#### 技術問題：CORS preflight

瀏覽器從 `https://R300-AI.github.io` 對 `http://localhost:8080` 發 preflight OPTIONS，Gateway 必須在 response header 中回傳正確 `Access-Control-Allow-Origin`。M12-3 的 `CORSMiddleware` 設定即處理此問題，使用者只需在 `.env` 加：

```ini
GATEWAY_CORS_ORIGINS=["http://localhost:5173","https://R300-AI.github.io"]
```
