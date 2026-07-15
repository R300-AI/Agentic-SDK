# BCI 射箭教練

在 BCI 射箭訓練的場域試行裡，教練與選手最常遇到的問題不是「有沒有資料」，而是「資料能不能在同一輪判讀裡形成可行動建議」。一組失準片段通常同時牽涉腦波、姿態、抖動、心率與主觀回饋，如果這些訊號不能被整合，輸出就會停在零散觀察，無法成為可執行的調整方向。

這篇案例保留完整情境深度，同時提供可復刻路徑。你可以先照著這條 workflow 做出第一版，再把資料來源、術語與輸出格式替換成自己的訓練或教學專案。

## 導入 Agentic SDK 的核心目標

這個案例導入 Agentic SDK 的核心目標，是把訊號整理、歷史回查與建議輸出收斂成同一條 workflow，讓每一輪互動都能沿著同一個判讀結構推進。

重點不是一次把系統做滿，而是先建立可運作骨架，再逐段替換節點能力。只要骨架穩定，新增感測來源或調整教練語言模板都能在原流程上擴展。

## 快速復現前準備

要復刻這個案例，先準備三份最小資料。

1. 一份訓練輸入樣本：腦波、姿態、心率、抖動任選其三。
2. 一份歷史訓練資料：至少包含 3 組過往紀錄。
3. 一個提問句：例如「後三箭為何失穩」。

這三份資料就能支撐第一版 workflow。後續只要擴充資料量與模組能力，不需要改動整體框架。

## 用 Agentic 框架切基本需求

先把需求拆成五節點，讓每個步驟對應清楚責任。

1. `Perceive`: 整理多模態輸入為判讀條件。
2. `Plan`: 決定本輪要先回查哪類歷史資料。
3. `Retrieve`: 取回對應訓練片段與標註內容。
4. `Action`: 生成教練可直接使用的建議。
5. `Reflect`: 統整輸出格式與回應內容。

這種分工方式是可移植的。你在自己的專案裡只需要替換資料與術語，不需要重設流程結構。

## 節點配置

BCI 場景的節點配置重點在交接內容，而不是單看模組名稱。

1. `Perceive` 交付本輪判讀條件，例如「後段專注度下滑 + 放箭抖動上升」。
2. `Plan` 交付回查方向，例如「優先比對相鄰訓練組與同時段歷史」。
3. `Retrieve` 交付可引用片段，例如「歷史事件標註、教練註記、相似型態片段」。
4. `Action` 交付可執行建議，例如「節奏調整、訓練強度調整、回看段落」。
5. `Reflect` 交付最終回應格式，方便教練與系統介面直接使用。

當每層交付內容固定，團隊就能單點調整節點，不會牽動整條流程。

## 最小配置範例

下面是可直接改寫的最小配置。這份配置的用途是先跑通整段判讀，而不是一次覆蓋所有訓練情境。

```yaml
workflow:
  name: bci-archery-coach
  nodes:
	- perceive:
		module: LLMBasedPerceive
		inputs: [sensor_stream, user_question]
		outputs: [session_conditions]

	- plan:
		module: ReActPlan
		inputs: [session_conditions]
		outputs: [history_query]

	- retrieve:
		module: SemanticRetrieve
		inputs: [history_query, training_history]
		outputs: [matched_sessions]

	- action:
		module: CompletionAction
		inputs: [session_conditions, matched_sessions]
		outputs: [coach_advice]

	- reflect:
		module: ReflexionReflect
		inputs: [coach_advice]
		outputs: [final_answer]
```

## 五步驟快速復現

1. 建立一筆多模態訓練輸入和一筆提問。
2. 準備最小歷史資料集（3 組以上）。
3. 先串 `LLMBasedPerceive + SemanticRetrieve + CompletionAction`。
4. 跑第一輪建議輸出，確認回應包含「判讀摘要 + 建議動作」。
5. 再補上 `Plan` 和 `Reflect`，完成完整 workflow。

這五步完成後，你會得到可演示、可擴展的第一版，接著就能換成正式資料來源。

## 實際運作

以「後三箭為何失穩」為例，流程會先整理當組訊號，再回查相似歷史訓練片段，最後生成教練可直接採取的建議。下一輪若改問「如何調整節奏」，workflow 不需要重建，只要替換當輪輸入條件即可。

這種多輪一致性，是訓練判讀流程真正可落地的關鍵。

## 如何換成你的專案

你可以把 BCI 案例視為模板，把欄位與語彙替換成自己的專案。

1. `sensor_stream` 換成你的多來源資料。
2. `training_history` 換成你的歷史知識庫。
3. `coach_advice` 換成你的輸出語言模板。
4. 保留五節點骨架，先求能跑，再調模組。

如果你的資料目前以結構化欄位為主，先用簡單回查方式即可。若你的歷史資料語意複雜、標註文本長，再升級 Retrieve 與 Perceive 會更有效率。

## 模組選型

BCI 場景可以用兩段式起手。

1. 第一段先上 `LLMBasedPerceive + SemanticRetrieve + CompletionAction`，快速產生可閱讀建議。
2. 第二段補上 `ReActPlan + ReflexionReflect`，讓多輪判讀流程更完整。

若你的資料來源已經穩定且欄位完整，可以直接使用 `LLMBasedPerceive + ReActPlan + SemanticRetrieve + CompletionAction + ReflexionReflect` 做完整配置。

## 系統骨架

BCI 案例最有價值的成果，不是單次判讀內容，而是一套可復刻的 workflow 骨架。你可以在保留情境深度的前提下，按步驟快速重建同類型系統。

先跑通流程，再替換資料來源與模組能力，你就能把這套方法直接移轉到自己的訓練或教學專案。
