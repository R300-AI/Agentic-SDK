# Quickstart Usability Check — M3 收尾驗收腳本

> 對應:[blueprint/target-quickstart.md](../blueprint/target-quickstart.md) §「驗收這個 quickstart 的方法」、[blueprint/tracks.md](../blueprint/tracks.md) I-05
> 本檔只是「驗收的 SOP」,不是驗收結果本身。每執行一輪,在最後一節追加一筆受測者紀錄。

---

## 一、為什麼需要這個流程

PoC 的成敗看「外人能不能跑起來」,不是看「開發者覺得能跑起來」。Phase 3 階段所有 quickstart 文件都已對齊 [target-quickstart.md](../blueprint/target-quickstart.md),但只要找一個沒參與開發的工程師實際跑一次,任何文件死角都會在 5 分鐘內現形。本流程的目的就是製造這個現形機會。

## 二、適用受測者篩選

候選人必須**全部**符合:

- 有 Python 開發背景(看得懂 venv / pip / .env 的概念)
- 從未閱讀本專案任何 README / docs / blueprint
- 對 LangChain / OpenAI SDK 或同類 Agentic 框架有過至少一次實際使用經驗
- 願意把整個 quickstart 過程當作「黑盒」執行,不主動問開發者「這應該怎麼設?」

**不適用**:

- 已參與 amd-ryzen-ai-benchmark 的維護者(會自動跳過上游環境的學習痛點)
- 對本專案 README 結構曾經 review 過的人

## 三、執行前準備

受測者端:

- [ ] 一台已通過上游 Ryzen AI Software 1.7.1 安裝、可成功跑 `python api.py --model gemma3-4b-npu` 的機器
- [ ] Python 3.12 已可從 `uv python install 3.12` 取得(若 uv 未裝,要求受測者依 `https://github.com/astral-sh/uv` 自行安裝,計入耗時)
- [ ] 受測者拿到一份「專案維護者提供的 Azure AI Foundry 認證」(Endpoint / API Key / Deployment)

觀察者端:

- [ ] 開好計時器(分別計 Step 2、Step 3 耗時)
- [ ] 開好一個空白記錄檔(本檔 §六)
- [ ] **承諾整個過程不主動提示**,只在受測者明確發出「我卡住了想求救」訊號時才介入,並記錄卡關點

## 四、執行步驟

讓受測者僅憑 [README.md](../README.md) 操作。觀察者不主動提示,但全程記錄:

| 階段 | 觀察點 | 計時起點 | 計時終點 |
|------|--------|----------|----------|
| Step 2 安裝 + 啟動 | 從 `git clone` 到 Dashboard 第一個面板渲染出來 | 受測者開始輸入 `git clone` | 受測者看見 Dashboard 「節點存活拓樸」面板顯示出 AMD inference path 健康 |
| Step 3 第一次呼叫 | 從打開 Python REPL 到看見 `x-agentic-metadata` header | 受測者開始輸入 OpenAI client 程式碼 | `print(response.response.headers["x-agentic-metadata"])` 印出非空字串 |

期間每次受測者「停下來思考超過 30 秒」、「打開瀏覽器搜尋」、「回頭重看 README 的同一段超過第二次」,都視為**一次卡關**,記錄發生位置。

## 五、結束時的訪談題

完成第三步後,觀察者口頭問下列三題,逐字記錄受測者回答(不要替受測者整理):

1. **時間題**:從你開始輸入 `git clone` 到看見 Dashboard 第一個面板,主觀感覺花了多久?
2. **卡關題**:整個過程你卡關幾次?每次卡在哪?是文件不清還是錯誤訊息不清?
3. **理解題**:第三步「跑一個五節點工作流」之後,請用一句話說明五節點各自做了什麼?

判斷標準(全部需達成,Phase 3 才算驗收通過):

| 題 | 通過門檻 |
|---|---------|
| 1 | Step 2 主觀時間 ≤ 5 分鐘(實測時間亦須 ≤ 5 分鐘) |
| 2 | 卡關次數 ≤ 2 次,且每次卡關當下都有「明確錯誤訊息」可循,不是「不知為何沒反應」 |
| 3 | 受測者能對齊 [docs/03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) §二 的節點描述,即使措辭不同 |

任一題未過,Phase 3 **不算通過**;修補 quickstart 流程後重找一名新受測者重跑,**不是請受測者「再多讀點文件」**。

## 六、受測者紀錄(每次追加)

格式如下,每次驗收結果直接附在本節後:

```
### YYYY-MM-DD 受測者 #N

- 受測者背景: <一句話描述職涯背景,例如「工研院影像 AI 工程師,3 年 PyTorch 經驗,首次接觸 Agentic 框架」>
- 觀察者: <記錄者姓名>
- Step 2 實測耗時: <分:秒>
- Step 3 實測耗時: <分:秒>
- 卡關次數: <N>
- 卡關位置與當時錯誤訊息(逐筆列):
  1. ...
  2. ...
- 三題回答(逐字):
  1. 時間: ...
  2. 卡關: ...
  3. 五節點理解: ...
- 結論: 通過 / 未通過(若未通過,列出待修補項並開 issue)
- 後續修補追蹤: <issue link or 「無」>
```

---

## 七、本流程的失效模式

預期會踩到的雷,事先記錄以免每次驗收都重新發現:

- **受測者其實偷看過 docs/**:訪談一開始先確認「你完全沒看過這個專案任何東西?」,得到肯定才開始計時
- **觀察者忍不住給提示**:可採文字記錄(LINE / Slack 螢幕分享)而非口頭陪同,降低介入誘惑
- **第三題受測者「複述 README」而非「自己理解」**:追問「如果你要把這套講給你同事聽,你會怎麼說?」以區分覆誦與內化
