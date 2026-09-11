# Agentic SDK 開發者文件站

說明如何使用 Agentic SDK 建立 Python 應用程式，涵蓋工作流程的組成方式、五類工作各自使用的模組、模組參數與資料傳遞方式，以及工作流程如何保存對話內容。

這一版文件聚焦公開 SDK 規格、模組參數與文件站導覽。所有需要模型的模組，都使用 OpenAI 相容介面作為統一接入方式。

## 這個文件站回答什麼

### 組合工作流程

說明 `Workflow` 如何承接五類工作，並定義模組在流程中的位置與責任。

### 可以直接跑的範例

[`examples/`](https://github.com/R300-AI/Agentic-SDK/tree/main/examples) 放的是完整、能執行的程式，補足文件說明不到的組裝細節。

### 模組與設定值

列出目前文件涵蓋的模組、其初始化參數與適用情境。

### 對話記憶

說明 `Workflow` 如何用 `MemoryStore` 保存模組可讀的共同對話資料，並以 `InContextMemory` 與 `PersistentMemory` 提供不同的記憶方式。

### 技術 Blog

用三篇設計文章說明 AI Hub 的模型卡與硬體服務，如何透過 Agentic SDK 變成長期記憶、電腦操作與角色化回覆。

## 主要入口

- [工作流程](workflow/index.md)：先理解公開組裝入口、五大功能角色與資料如何沿流程傳遞。
- [模組家族](modules/index.md)：查看目前文件涵蓋的模組總表，再分流到各功能頁查規格。
- [記憶類型](workflow/memory-types.md)：查 `Workflow` 如何分工 `memory_type`、`MemoryStore`、`InContextMemory`、`PersistentMemory` 與 `WorkflowState`。
- [技術 Blog](blog/index.md)：查看 Letta、Fara 與 MatrAIx 的整合設計，理解模型卡、推論服務與工作流程之間的關係。

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
      <td rowspan="3">Perceive</td>
      <td><a href="modules/perceive-modules.md#passthroughperceive">PassThroughPerceive</a></td>
      <td>no</td>
      <td>--</td>
      <td>保留最新一輪使用者輸入，並把它送進同一個 session 的對話上下文。</td>
    </tr>
    <tr>
      <td><a href="modules/perceive-modules.md#textperceive">TextPerceive / TextImagePerceive</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>根據完整對話歷史整理最新需求，必要時也把圖片一併納入理解。</td>
    </tr>
    <tr>
      <td><a href="modules/perceive-modules.md#voicetextperceive">VoiceTextPerceive</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>把說出來的話轉成這一輪的輸入，安靜時不上傳；偵測到使用者開口時中止進行中的回答。</td>
    </tr>
    <tr>
      <td rowspan="2">Plan</td>
      <td><a href="modules/plan-modules.md#passthroughplan">PassThroughPlan</a></td>
      <td>no</td>
      <td>--</td>
      <td>不呼叫模型，先檢索一次、掛了反思模組時送反思一次，再行動。沒有指定規劃模組時使用。</td>
    </tr>
    <tr>
      <td><a href="modules/plan-modules.md#nextstepplan">NextStepPlan</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>根據完整對話、目前中繼結果與反思回報，決定下一步要 Retrieve、Reflect 還是 Action。</td>
    </tr>
    <tr>
      <td rowspan="3">Retrieve</td>
      <td><a href="modules/retrieve-modules.md#passthroughretrieve">PassThroughRetrieve</a></td>
      <td>no</td>
      <td>--</td>
      <td>不查任何資料，直接把前一步的結果往下送。</td>
    </tr>
    <tr>
      <td><a href="modules/retrieve-modules.md#keywordretrieve">KeywordRetrieve</a></td>
      <td>no</td>
      <td>--</td>
      <td>直接用關鍵字去找既有知識內容，適合資料量不大、條目結構明確的情境。</td>
    </tr>
    <tr>
      <td><a href="modules/retrieve-modules.md#semanticretrieve">SemanticRetrieve</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>用語意相似度找出相關內容，適合需要提高召回率與理解能力的情境。</td>
    </tr>
    <tr>
      <td rowspan="4">Action</td>
      <td><a href="modules/action-modules.md#directansweraction">DirectAnswerAction</a></td>
      <td>no</td>
      <td>--</td>
      <td>把前面找到的內容直接整理成答案，適合以固定文字回覆的情況。</td>
    </tr>
    <tr>
      <td><a href="modules/action-modules.md#generativeaction">GenerativeAction</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>根據前面整理好的內容重新生成自然語言回答，適合需要較完整表達與文字潤飾的情況。</td>
    </tr>
    <tr>
      <td><a href="modules/action-modules.md#toolcallaction">ToolCallAction</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>使用 OpenAI 標準 tools schema 讓模型產生 tool calls，適合外部 API 或後端函式由應用層執行的情境。</td>
    </tr>
    <tr>
      <td><a href="modules/action-modules.md#voiceansweraction">VoiceAnswerAction</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>同時產出說出口與顯示在畫面上的兩個頻道，前者一寫完就送去合成，不等整段回覆結束。</td>
    </tr>
    <tr>
      <td rowspan="2">Reflect</td>
      <td><a href="modules/reflect-modules.md#plancheckreflect">PlanCheckReflect</a></td>
      <td>yes</td>
      <td>OpenAI</td>
      <td>在行動前用模型確認規劃選的步驟能不能執行、檢索有沒有正常完成，回報交給規劃模組。</td>
    </tr>
    <tr>
      <td><a href="modules/reflect-modules.md#evidencecheckreflect">EvidenceCheckReflect</a></td>
      <td>no</td>
      <td>--</td>
      <td>在行動前用規則確認最近一次檢索有沒有找到內容，回報交給規劃模組。</td>
    </tr>
  </tbody>
</table>

首頁提供文件導覽與目前文件範圍；各模組的詳細設定請進對應頁面查看。