# Quickstart Usability Check — 受測者手稿(精簡版)

> 對應:[../quickstart-usability-check.md](../quickstart-usability-check.md)
> 前提:Ryzen AI PC 已跑著 `python api.py --model gemma3-4b-npu`,`curl http://localhost:8000/v1/models` 回 200。
> 本輪屬內部 dry-run,先把 README 明顯死角洗掉。

## 你只需要做三件事

1. 在 **視窗 A** 跑「準備」一段
2. **照 [../../README.md](../../README.md) §三步啟動 第二、三步** 操作(碰到任何卡關停下來記到 `06-blockers.md`)
3. 在 **視窗 X** 跑「收尾」一段 → commit & push

中間不要去翻 docs/、blueprint/ 任何檔案。如果 README 沒寫清楚而你回頭翻了,**那就是死角,記下來**。

---

## 視窗 A:準備(在 repo 根目錄,新開的 PowerShell)

直接整段貼進去執行:

```powershell
cd C:\Users\B20447\Desktop\GitHub\Agentic-SDK   # ← 改成你 clone 後的路徑

$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

Start-Transcript -Path "$RunDir\01-transcript.log" -IncludeInvocationHeader

Get-Date -Format 'o' | Out-File "$RunDir\02-timing.txt"   # step2_start
Write-Host ">>> 接著去看 README §第二步,照抄。RunDir = $RunDir" -ForegroundColor Cyan
```

接著 **照 README §第二步** 在這個視窗一行一行貼。`.\scripts\start.ps1` 啟動後,Gateway 留在這個視窗前景,Dashboard 會被自動拉到新視窗(視窗 D)。

打開瀏覽器 `http://localhost:8501`,看到「節點存活拓樸」面板顯示 AMD inference path 健康燈,就可以進下一步。

---

## 視窗 X:收尾(任何新開的 PowerShell)

```powershell
cd C:\Users\B20447\Desktop\GitHub\Agentic-SDK   # ← 改成同一個路徑
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"

Get-Date -Format 'o' | Out-File "$RunDir\02-timing.txt" -Append   # step2_end / step3_start

# ── Step 3:照 README §第三步 用 OpenAI SDK 呼叫 ──
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

.\.venv\Scripts\python.exe "$RunDir\step3.py" 2>&1 | Tee-Object -FilePath "$RunDir\04-step3-call.txt"

Get-Date -Format 'o' | Out-File "$RunDir\02-timing.txt" -Append   # step3_end

# ── 抓 Dashboard 同源遙測資料 ──
Invoke-RestMethod "http://127.0.0.1:8080/internal/telemetry/snapshot?limit=200" `
  | ConvertTo-Json -Depth 10 `
  | Out-File "$RunDir\05-telemetry.json"

# ── 開記事本填卡關與總結 ──
@'
# 卡關紀錄

> 每筆:`HH:MM:SS | README 哪段或哪個指令 | 看到什麼錯誤/現象 | 怎麼解決`
> 完全沒卡關就寫一行:無卡關
'@ | Out-File -Encoding utf8 "$RunDir\06-blockers.md"

@'
# Self Run Summary

- 受測者: <姓名 / 角色>
- 三題回答(逐字):
  1. 時間題(從 git clone 到 Dashboard 第一個面板,主觀感覺): ...
  2. 卡關題(幾次、卡在哪、文件不清還是錯誤訊息不清): ...
  3. 理解題(用一句話說明五節點各自做了什麼): ...
- 結論: 通過 / 未通過
- README 死角候選(本輪你覺得外人會踩雷的地方): ...
'@ | Out-File -Encoding utf8 "$RunDir\99-summary.md"

notepad "$RunDir\06-blockers.md"
notepad "$RunDir\99-summary.md"

# ── 收尾 ──
Stop-Transcript

git add $RunDir
git status
Write-Host ">>> 確認檔案都進去後,git commit -m 'docs(quickstart-run): self dry-run' && git push" -ForegroundColor Cyan
```

填完兩個 notepad、`git commit` + `git push`,把 commit hash 貼給我即可。

---

## 產物清單(commit 前自己掃一眼,缺哪個補哪個)

`docs\quickstart-runs\<日期>-self\` 內應該有:

- `01-transcript.log` — 視窗 A 的完整 PowerShell 紀錄
- `02-timing.txt` — 四個 ISO 時間戳(step2 起訖、step3 起訖)
- `04-step3-call.txt` — 含 `HTTP status: 200` 與非空的 `x-agentic-metadata: {...}`
- `05-telemetry.json` — 內可搜到 `workflow.node.finish` 事件
- `06-blockers.md` — 即使沒卡關也要明寫「無卡關」
- `99-summary.md` — 三題回答 + 結論

(可選加分:Dashboard 截圖直接拖進資料夾)

---

## 為什麼本輪不能取代外部受測

你已知 `.env` 欄位、知道 `start.ps1` 會拉 Dashboard、知道 `x-agentic-metadata` header 存在 — 這些對外人都是潛在卡關點。因此 [milestones.md](../../blueprint/milestones.md) M3-1 / M3-3 在本輪後仍維持 🟡,要等真正的外部受測者跑完才轉 ✅。
