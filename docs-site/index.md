# Agentic SDK 開發者文件站

這套文件站以 SDK reference 為主，目標是讓進階開發者快速查到 `Workflow` 的公開組裝模型、五大功能的模組分類、各模組的參數與輸入輸出契約，以及 `Workflow` 在執行時可以搭配哪些引擎選項。

這一版文件只聚焦 README 已定稿的公開敘事，不展開 deployment、demo 操作導覽或內部替身實作。所有需要模型的模組，都以 `OpenAI SDK form` 作為統一接入規格。

## 這個文件站回答什麼

### 公開組裝模型

說明 `Workflow` 如何承接五大功能，並定義模組在流程中的位置與責任。

### 模組與參數

列出目前文件涵蓋的模組、其初始化參數與適用情境。

### Workflow 引擎選項

說明 `Workflow` 預設如何用 `InContextMemory` 承接執行中的狀態資料，以及之後可替換或注入哪些引擎層。

### Use Case 實施例

用三個具體場景說明如何把 `Workflow`、`Module Family` 與資料來源組合成可落地的 agent 實施例。

## 主要入口

- [Workflow Overview](workflow-overview.md)：先理解公開組裝入口、五大功能角色與資料如何沿流程傳遞。
- [Module Family](modules/index.md)：查看目前文件涵蓋的模組總表，再分流到各功能頁查規格。
- [Workflow 引擎選項](workflow-engines.md)：查 `Workflow` 預設使用的 `InContextMemory`，以及可注入的其他引擎層。
- [Use Case](use-cases/index.md)：查看 LaNew 售鞋顧問、BCI 射箭教練與 ICOPE 六力評估助手三個實施例，理解場景拆法與模組組合。

## 模組總表

<table>
  <thead>
    <tr>
      <th>五大功能</th>
      <th>模組名稱</th>
      <th>是否需要模型</th>
      <th>SDK 規格</th>
      <th>功能說明</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td rowspan="2">Perceive</td>
      <td><a href="modules/perceive-modules.md#inputperceive">InputPerceive</a></td>
      <td>no</td>
      <td>--</td>
      <td>先接住使用者輸入，讓 workflow 可以從最基本的一條路徑開始往下跑。</td>
    </tr>
    <tr>
      <td><a href="modules/perceive-modules.md#llm-perceive">LLM Perceive</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>先把使用者輸入整理成較清楚的理解結果，必要時也能順手產生後續檢索要用的查詢內容。</td>
    </tr>
    <tr>
      <td rowspan="3">Plan</td>
      <td><a href="modules/plan-modules.md#chain-of-thought-planner">Chain-of-Thought Planner</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>先把問題想一遍，再整理成一條清楚的處理步驟，適合當成最基本的規劃方式。</td>
    </tr>
    <tr>
      <td><a href="modules/plan-modules.md#react-planner">ReAct Planner</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>一邊思考一邊決定下一步要查什麼、做什麼，適合需要動態調整流程方向的情境。</td>
    </tr>
    <tr>
      <td><a href="modules/plan-modules.md#plan-and-solve-planner">Plan-and-Solve Planner</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>先把大問題拆成幾個小步驟，再把這些步驟交給後續檢索或回答流程逐步完成。</td>
    </tr>
    <tr>
      <td rowspan="2">Retrieve</td>
      <td><a href="modules/retrieve-modules.md#keywordretrieve">KeywordRetrieve</a></td>
      <td>no</td>
      <td>--</td>
      <td>直接用關鍵字去找既有知識內容，適合資料量不大、條目結構明確的情境。</td>
    </tr>
    <tr>
      <td><a href="modules/retrieve-modules.md#semantic-search-retrieve">Semantic Search Retrieve</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>用語意去找真正相關的內容，不只看字面相同，較適合需要提高召回率與理解能力的情境。</td>
    </tr>
    <tr>
      <td rowspan="2">Action</td>
      <td><a href="modules/action-modules.md#directansweraction">DirectAnswerAction</a></td>
      <td>no</td>
      <td>--</td>
      <td>把前面已找到的內容直接整理成答案，適合不需要模型重新生成文字的情況。</td>
    </tr>
    <tr>
      <td><a href="modules/action-modules.md#completionaction">CompletionAction</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>根據前面整理好的內容重新生成自然語言回答，適合需要較完整表達與文字潤飾的情況。</td>
    </tr>
    <tr>
      <td>Reflect</td>
      <td><a href="modules/reflect-modules.md#reflexion-reflect">Reflexion Reflect</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>回頭檢查目前答案夠不夠好，若不夠就提出修正方向，讓下一輪流程可以繼續改進。</td>
    </tr>
  </tbody>
</table>

這一版首頁只負責文件站導覽與目前文件範圍，模組細節請進各功能頁查看。