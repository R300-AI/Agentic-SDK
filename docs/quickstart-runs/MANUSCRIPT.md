# Quickstart Usability Check — 受測者手稿(單檔自含)

> 前提:Ryzen AI PC 已跑著 `python api.py --model gemma3-4b-npu`,`curl http://localhost:8000/v1/models` 回 200。
> 本檔自含所有指令,**不必去看 README 或其他文件**。完成後 commit & push,把 commit hash 貼回來。

---

## 你會用到三個 PowerShell 視窗

| 視窗 | 用途 | 何時關 |
|------|------|--------|
| **A** | 跑 Gateway(會被前景占住) | 全部結束才 Ctrl+C |
| **D** | 跑 Dashboard(由腳本自動拉起,Streamlit 在前景) | 全部結束才 Ctrl+C |
| **X** | 跑收尾、Step 3 呼叫、git push | 收尾完關掉 |

---

## 視窗 A:準備 + 啟動(整段貼上)

開一個新的 PowerShell,`cd` 到你 clone 的 repo 根目錄,然後整段貼:

```powershell
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

Start-Transcript -Path "$RunDir\01-transcript.log" -IncludeInvocationHeader
"step2_start: $((Get-Date).ToString('o'))" | Out-File "$RunDir\02-timing.txt"

# 1) 建環境(uv 會自動裝 Python 3.12、建 .venv、依 pyproject.toml 裝相依)
uv sync --extra dev

# 2) .env(預設 UPSTREAM_API_BASE_URL 已指向 localhost:8000;
#    Azure Foundry 沒填時 Plan/Reflect 會自動降為 Mock,本輪不影響)
if (-not (Test-Path .env)) { Copy-Item .env.example .env }

# 3) 啟動 Gateway(前景)+ Dashboard(新視窗自動拉起)
.\scripts\start.ps1
```

`start.ps1` 跑起來後:
- 視窗 A 留在前景,看到「Uvicorn running on http://127.0.0.1:8080」即可
- 視窗 D 會被自動拉起,看到「You can now view your Streamlit app at http://localhost:8501」即可
- 開瀏覽器 `http://localhost:8501`,等「節點存活拓樸」面板顯示 AMD inference path 健康燈

看到燈以後 → 切到 **視窗 X**。

> 中途任何步驟卡住或報錯,**直接停下來**,把訊息留在視窗 A 不要動;到視窗 X 跑收尾後再到 `06-blockers.md` 記錄。

---

## 視窗 X:Step 3 + 收尾 + 提交(整段貼上)

開第三個 PowerShell,`cd` 到同一個 repo 根目錄,然後整段貼:

```powershell
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"
"step2_end:   $((Get-Date).ToString('o'))" | Out-File "$RunDir\02-timing.txt" -Append
"step3_start: $((Get-Date).ToString('o'))" | Out-File "$RunDir\02-timing.txt" -Append

# ── Step 3:用 OpenAI SDK 打 Gateway,完整跑一次五節點工作流 ──
@'
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")

print("=== models.list ===")
print(client.models.list())

print("\n=== chat.completions ===")
resp = client.with_raw_response.chat.completions.create(
    model="gemma3-4b-npu",
    messages=[{"role": "user", "content": "幫我查 2024Q4 的銷售報表並摘要"}],
)
print("HTTP status:", resp.http_response.status_code)
print("x-agentic-metadata:", resp.http_response.headers.get("x-agentic-metadata"))
completion = resp.parse()
print("model:", completion.model)
print("finish_reason:", completion.choices[0].finish_reason)
print("content:", completion.choices[0].message.content)
print("usage:", completion.usage)
'@ | Out-File -Encoding utf8 "$RunDir\step3.py"

uv run python "$RunDir\step3.py" 2>&1 | Tee-Object -FilePath "$RunDir\04-step3-call.txt"

"step3_end:   $((Get-Date).ToString('o'))" | Out-File "$RunDir\02-timing.txt" -Append

# ── 抓 Dashboard 同源遙測資料(我事後讀這份驗證五節點序列) ──
Invoke-RestMethod "http://127.0.0.1:8080/internal/telemetry/snapshot?limit=200" `
  | ConvertTo-Json -Depth 10 `
  | Out-File "$RunDir\05-telemetry.json"

# ── 建立卡關與總結範本,開 notepad 填寫 ──
@'
# 卡關紀錄

> 每筆:`HH:MM:SS | 在哪個指令 | 看到什麼錯誤/現象 | 怎麼解決`
> 完全沒卡關就寫一行:無卡關
'@ | Out-File -Encoding utf8 "$RunDir\06-blockers.md"

@'
# Self Run Summary

- 受測者: <姓名 / 角色>
- 三題回答(逐字):
  1. 時間題(從開始到看見 Dashboard 第一個面板,主觀感覺): ...
  2. 卡關題(幾次、卡在哪、文件不清還是錯誤訊息不清): ...
  3. 理解題(用一句話說明 Perceive / Plan / Retrieve / Action / Reflect 五節點各自做了什麼): ...
- 結論: 通過 / 未通過
- README 死角候選(本輪你覺得外人會踩雷的地方): ...
'@ | Out-File -Encoding utf8 "$RunDir\99-summary.md"

notepad "$RunDir\06-blockers.md"
notepad "$RunDir\99-summary.md"
```

填完兩個 notepad、關掉視窗即可。接著繼續在視窗 X 整段貼:

```powershell
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"

# ── 關掉 Gateway 與 Dashboard ──
# 切到視窗 A 與視窗 D 各按一次 Ctrl+C(本檔不幫你殺,以免誤殺其他行程)

Stop-Transcript

# ── 提交 ──
git add $RunDir
git status
Write-Host ">>> 確認以上都是 quickstart-runs/ 下的檔案後,執行:" -ForegroundColor Cyan
Write-Host ">>> git commit -m 'docs(quickstart-run): self dry-run'" -ForegroundColor Cyan
Write-Host ">>> git push" -ForegroundColor Cyan
Write-Host ">>> 然後把 commit hash 貼回對話" -ForegroundColor Cyan
```

---

## 產物清單(commit 前自己掃一眼)

`docs\quickstart-runs\<日期>-self\` 內應該有:

- `01-transcript.log` — 視窗 A 的完整 PowerShell 紀錄(含 uv sync、start.ps1 全部輸出)
- `02-timing.txt` — `step2_start` / `step2_end` / `step3_start` / `step3_end` 四行 ISO 時間戳
- `step3.py` — Step 3 用的 Python 腳本
- `04-step3-call.txt` — 含 `HTTP status: 200` 與非空的 `x-agentic-metadata: {...}`
- `05-telemetry.json` — 內可搜到 `workflow.node.finish` 事件
- `06-blockers.md` — 即使沒卡關也要明寫「無卡關」
- `99-summary.md` — 三題回答 + 結論

(可選加分:Dashboard 截圖,直接拖進該資料夾,檔名隨意)

---

## 為什麼本輪不能取代外部受測

你已知 `.env` 內容、知道 `start.ps1` 會自動拉 Dashboard、知道 `x-agentic-metadata` header 存在 — 這些對外人都是潛在卡關點。因此 [milestones.md](../../blueprint/milestones.md) M3-1 / M3-3 在本輪後仍維持 🟡,要等真正的外部受測者跑完才轉 ✅。
