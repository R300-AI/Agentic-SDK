# Quickstart Usability Check — 受測者手稿

> 對應:[../quickstart-usability-check.md](../quickstart-usability-check.md)
> 角色:你是受測者(已知是專案內部人,本輪屬「自己跑一遍找文件死角」的 dry-run,不取代 M3-1 真正的外部受測)。
> 環境:Windows + PowerShell + 已安裝好 Ryzen AI Software 1.7.1 的 Ryzen AI PC。

## 一、為什麼要有這份手稿

讓你只需 **照抄、貼上、執行**,所有時間 / log / response metadata 自動存到固定路徑與格式,我事後直接讀檔判讀,不需要你回憶或整理。

## 二、產出目錄

整個受測過程的所有產物,都會落在:

```
docs/quickstart-runs/<YYYY-MM-DD>-self/
├── 00-env.txt              # 受測者環境快照(自動)
├── 01-transcript.log       # PowerShell 整段 transcript(自動)
├── 02-step2-timing.txt     # Step 2 起訖時間戳(自動)
├── 03-gateway-startup.log  # Gateway 啟動前 N 行(手動 tee)
├── 04-step3-call.txt       # OpenAI SDK 呼叫的輸入與輸出(手動,腳本給範本)
├── 05-telemetry.json       # /internal/telemetry/snapshot(自動)
├── 06-blockers.md          # 卡關紀錄(手動填,逐筆)
└── 99-summary.md           # 最後對照 quickstart-usability-check.md §六 的總表(手動填,有範本)
```

跑完整輪後,請把整個資料夾 commit 進 repo 並 push,我會直接讀。

## 三、執行流程

### Step 0:建立產出目錄與 transcript

打開一個全新的 PowerShell 視窗,`cd` 到 repo 根目錄(`Agentic-SDK\`),然後:

```powershell
$RunDate = Get-Date -Format "yyyy-MM-dd"
$RunDir = "docs\quickstart-runs\$RunDate-self"
New-Item -ItemType Directory -Force -Path $RunDir | Out-Null

# 整段操作會被錄到 transcript;之後任何指令的輸出都會自動進去
Start-Transcript -Path "$RunDir\01-transcript.log" -IncludeInvocationHeader

# 環境快照
"=== Host ===" | Out-File "$RunDir\00-env.txt"
Get-ComputerInfo OsName, OsVersion, CsName | Format-List | Out-File "$RunDir\00-env.txt" -Append
"=== Python (system) ===" | Out-File "$RunDir\00-env.txt" -Append
(Get-Command python -ErrorAction SilentlyContinue).Source | Out-File "$RunDir\00-env.txt" -Append
python --version 2>&1 | Out-File "$RunDir\00-env.txt" -Append
"=== uv ===" | Out-File "$RunDir\00-env.txt" -Append
(Get-Command uv -ErrorAction SilentlyContinue).Source | Out-File "$RunDir\00-env.txt" -Append
uv --version 2>&1 | Out-File "$RunDir\00-env.txt" -Append
"=== conda envs ===" | Out-File "$RunDir\00-env.txt" -Append
conda env list 2>&1 | Out-File "$RunDir\00-env.txt" -Append

Write-Host "RunDir = $RunDir" -ForegroundColor Cyan
```

> 若 `python` / `uv` 不在 PATH,輸出會是空 — 那本身就是有用的資訊,**不要手動去裝**,讓 README 引導你怎麼裝。

### Step 1:啟動上游推論伺服器(計時不含此步)

**開另一個 PowerShell 視窗**(以下稱「視窗 U」),依上游 README 啟動 `api.py`:

```powershell
conda activate ryzen-ai-1.7.1
cd <path to amd-ryzen-ai-benchmark>
python api.py --model gemma3-4b-npu
```

確認終端機顯示「listening on http://localhost:8000」之類訊息後,**回到原視窗**(以下稱「視窗 A」)做一次 sanity check:

```powershell
curl http://localhost:8000/v1/models
```

如果這一步失敗,**不是本專案的問題**,請依上游 README 排除後再繼續。

### Step 2:從零裝起並啟動 Gateway + Dashboard(計時)

> 從這裡開始,**完全只看 [../../README.md](../../README.md) 的「三步啟動」第二步**。不要回頭看 docs/ 或 blueprint/。

回到視窗 A,先抓開始時間:

```powershell
$Step2Start = Get-Date
"step2_start: $($Step2Start.ToString('o'))" | Out-File "$RunDir\02-step2-timing.txt"
```

然後 **完全照 README §第二步** 一行一行貼到視窗 A 執行。

> ⚠️ 如果你已經在 repo 根目錄、已經有 `.venv`、已經有 `.env`,**請假裝你沒有**。可以新建一個臨時資料夾重新 clone,或先把 `.venv\` / `.env` 改名:
>
> ```powershell
> Move-Item .venv .venv.bak -ErrorAction SilentlyContinue
> Move-Item .env .env.bak -ErrorAction SilentlyContinue
> ```
>
> 跑完整流程後再改回來。

當 README §第二步 的最後一行 `.\scripts\start.ps1` **啟動 Gateway** 後:

- Gateway 會在視窗 A 前景跑(別關掉)
- 一個新的 PowerShell 視窗會被自動拉起,跑 Dashboard(以下稱「視窗 D」)

**開瀏覽器**到 `http://localhost:8501`,等「節點存活拓樸」面板第一次出現 AMD inference path 健康燈。看到燈的瞬間,**開第三個 PowerShell 視窗**(視窗 X,任何路徑都行),記時間 & 抓 Gateway log:

```powershell
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"
cd C:\path\to\Agentic-SDK     # 改成你 clone 的路徑

$Step2End = Get-Date
"step2_end:   $($Step2End.ToString('o'))" | Out-File "$RunDir\02-step2-timing.txt" -Append

# 從視窗 A 的 transcript 抓 Gateway 啟動前 200 行(transcript 還在寫,先 copy 出來看)
Get-Content "$RunDir\01-transcript.log" -Tail 200 | Out-File "$RunDir\03-gateway-startup.log"
```

> Step 2 elapsed = `Step2End - Step2Start`,稍後 §99-summary 會用到。

### Step 3:用 OpenAI SDK 跑一次五節點工作流(計時)

繼續在視窗 X:

```powershell
$RunDir = "docs\quickstart-runs\$(Get-Date -Format 'yyyy-MM-dd')-self"

# 確認 openai 套件在 .venv(README 沒明說,但 .[dev] 會帶到)
.\.venv\Scripts\python.exe -c "import openai; print(openai.__version__)"

$Step3Start = Get-Date
"step3_start: $($Step3Start.ToString('o'))" | Out-File "$RunDir\02-step2-timing.txt" -Append

# 把 Step 3 範例存成獨立檔,輸出同時印螢幕 + 落地
@'
from openai import OpenAI

client = OpenAI(base_url="http://127.0.0.1:8080/v1", api_key="local")

# 1) /v1/models
print("=== models.list ===")
print(client.models.list())

# 2) /v1/chat/completions(走完整 Workflow)
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

$Step3End = Get-Date
"step3_end:   $($Step3End.ToString('o'))" | Out-File "$RunDir\02-step2-timing.txt" -Append
```

緊接著抓 telemetry snapshot(這是 Dashboard 同源的資料):

```powershell
Invoke-RestMethod "http://127.0.0.1:8080/internal/telemetry/snapshot?limit=200" `
  | ConvertTo-Json -Depth 10 `
  | Out-File "$RunDir\05-telemetry.json"
```

最後切到瀏覽器 Dashboard,**用截圖工具(Win+Shift+S)截下「Workflow 執行進度」面板**,存到 `$RunDir\dashboard-workflow.png`;若有「推論指標時序圖」也存 `$RunDir\dashboard-metrics.png`。

### Step 4:填卡關紀錄

整段過程任何一次「停下來思考 >30 秒、打開瀏覽器搜尋、回頭重看 README 同一段第二次以上」都算一次卡關。把每一次寫進:

```powershell
@'
# 卡關紀錄

> 每一筆格式:`HH:MM:SS | 位置(README 哪段 / 哪個指令) | 看到的錯誤訊息或現象 | 你怎麼解決的`

- 範例:`10:42:13 | README §第二步 "uv pip install -e \".[dev]\"" | error: failed to download httpx-0.x.x.whl | 重試一次後 OK`

(若全程沒卡關,寫一行:`無卡關`)
'@ | Out-File -Encoding utf8 "$RunDir\06-blockers.md"

notepad "$RunDir\06-blockers.md"   # 開 notepad 編輯
```

### Step 5:填總結

```powershell
$Step2Sec = ((Get-Content "$RunDir\02-step2-timing.txt" | Select-String 'step2_').Matches.Value) -join ", "

@"
# Self Run Summary — $RunDate

> 對照 [../quickstart-usability-check.md](../quickstart-usability-check.md) §六 範本。
> **本輪屬內部 dry-run**,不取代 M3-1 真正外部受測。

- 受測者背景: 專案內部成員(<姓名 / 角色>)
- 觀察者: 同受測者(self-run)
- Step 2 實測耗時(計算自 02-step2-timing.txt): <分:秒>
- Step 3 實測耗時(計算自 02-step2-timing.txt): <分:秒>
- 卡關次數: <N>(見 06-blockers.md)
- 三題回答(逐字,即使是自己也照原樣回答):
  1. 時間題(從 git clone 到 Dashboard 第一個面板,主觀感覺): ...
  2. 卡關題(卡關幾次、卡在哪、文件不清還是錯誤訊息不清): ...
  3. 理解題(用一句話說明五節點各自做了什麼): ...
- 對 docs/quickstart-usability-check.md §五 判斷標準的自評:
  - 題 1(Step 2 ≤ 5 分鐘): 通過 / 未通過
  - 題 2(卡關 ≤ 2 且每次都有明確錯誤訊息): 通過 / 未通過
  - 題 3(能對齊 react-workflow-routing.md §二): 通過 / 未通過
- 結論: 通過 / 未通過
- 後續修補追蹤(本輪發現的 README 死角、文件漂移、啟動腳本問題,各開一個 issue 或寫在這): ...

## 附:Step 3 收到的 x-agentic-metadata
(從 04-step3-call.txt 複製那一行)

\`\`\`json
...
\`\`\`

## 附:telemetry snapshot 內 workflow_id 對應的 node.finish 序列
(從 05-telemetry.json 內找出該 workflow_id 的事件序列,確認是
perceive → plan → retrieve → plan → action → reflect)

\`\`\`
[逐筆貼上 6 筆 node.finish 的 (workflow_node, visit) 即可]
\`\`\`
"@ | Out-File -Encoding utf8 "$RunDir\99-summary.md"

notepad "$RunDir\99-summary.md"
```

### Step 6:關閉 transcript 與善後

```powershell
Stop-Transcript

# 還原原本的 .venv / .env(若你在 Step 2 改名過)
Move-Item .venv .venv.runX -ErrorAction SilentlyContinue
Move-Item .venv.bak .venv -ErrorAction SilentlyContinue
Move-Item .env .env.runX -ErrorAction SilentlyContinue
Move-Item .env.bak .env -ErrorAction SilentlyContinue

# 視窗 A(Gateway)、視窗 D(Dashboard)、視窗 U(api.py)按 Ctrl+C 收掉
```

最後在 repo 內 commit 整個 `docs/quickstart-runs/$RunDate-self/` 資料夾並 push。

---

## 四、檢核清單(commit 前自己過一遍)

- [ ] `00-env.txt` 不是空檔
- [ ] `01-transcript.log` 至少數百行(完整紀錄)
- [ ] `02-step2-timing.txt` 有 `step2_start` / `step2_end` / `step3_start` / `step3_end` 四行
- [ ] `03-gateway-startup.log` 看得到 `upstream healthy` 或對應錯誤訊息
- [ ] `04-step3-call.txt` 看得到 `HTTP status: 200` 且 `x-agentic-metadata: {...}` 非空
- [ ] `05-telemetry.json` 內可搜到 `workflow.node.finish` 與該次 `workflow_id`
- [ ] `06-blockers.md` 已填(即使是「無卡關」也要寫)
- [ ] `99-summary.md` 三題回答 + 自評都填了
- [ ] (有則加分)`dashboard-workflow.png` / `dashboard-metrics.png` 截圖

完成後告訴我 commit hash 或直接 push,我會去讀 `docs/quickstart-runs/<date>-self/` 整包並回饋哪些是 README 真死角、哪些是 self-run 才會碰到的偽訊號。

## 五、本輪 dry-run 不能取代外部受測的部分

明確記錄,避免日後誤判:

- ❌ 你已經知道 `.env` 內哪個欄位給誰用 → 不會被「Azure Foundry 欄位看不懂」絆住,但外人會
- ❌ 你已經知道 `start.ps1` 會自動拉起 Dashboard → 不會浪費時間問「Dashboard 怎麼開」,但外人會
- ❌ 你已經知道 `x-agentic-metadata` 存在 → 不會困惑「response.choices 怎麼看不到五節點軌跡」,但外人會

所以即使本輪 99-summary 全通過,M3-1 / M3-3 在 [milestones.md](../../blueprint/milestones.md) 仍維持 🟡,直到找到符合 [../quickstart-usability-check.md](../quickstart-usability-check.md) §二 的外部受測者跑過一輪為止。
