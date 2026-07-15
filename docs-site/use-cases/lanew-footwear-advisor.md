# LaNew 售鞋顧問

在 LaNew 的場域試行裡，導購互動通常發生在消費者完成足測之後。消費者第一個問題是「這份報告在講什麼」，第二個問題是「這跟我實際要買的鞋有什麼關係」。如果系統只能回一段鞋款清單，沒有把足測數據轉成可理解的足型意義，導購流程就會中斷在資訊層，無法進入決策層。

真正有效的流程，是把報告解讀、條件追問、商品回查、推薦說明接成同一條互動線。這樣消費者每一次追問都能回到同一份上下文，知道系統是根據哪些足測條件與商品特徵給出建議。這也是這篇案例的核心：先讓讀者完整理解情境，再把同一套流程復刻到自己的專案。

## 導入 Agentic SDK 的核心目標

這個案例導入 Agentic SDK 的核心目標，是把足測解讀、條件補問、商品回查與推薦輸出收斂成一條可持續運作的 workflow。它解決的不是單次回答品質，而是整段導購互動的連續性。

當這四段工作放在同一條流程裡，團隊可以在不重做全系統的前提下，逐段替換節點能力。你可以先用最小模組組合跑通，再按需求把 Perceive 或 Retrieve 升級，而 Action 的對外輸出格式維持一致，前端與服務流程就不會被反覆打斷。

## 快速復現前準備

要復刻這個案例，不需要先準備完整資料平台。先備齊下列內容即可進入第一版。

本案例可直接使用專案內建樣本：`assets/lanew-sample.png`。

1. 一份足測輸入樣本：至少包含足弓、受力、尺寸差異。
2. 一份商品知識清單：至少包含鞋款名稱、支撐特性、尺寸建議。
3. 一份使用者提問：例如「我久站通勤，該選哪款」。

這三份內容對應 workflow 的三個基礎責任：理解輸入、回查知識、生成建議。當你把資料來源換成自己的領域時，也只需要替換這三個入口。

## 用 Agentic 框架切基本需求

先把需求拆成五個節點，讓每段責任有固定邊界，後續才容易維護與替換。

1. `Perceive`: 把足測欄位與提問轉成條件清單。
2. `Plan`: 判斷下一步是補問條件還是直接回查。
3. `Retrieve`: 從商品知識中取回候選鞋款與對應資訊。
4. `Action`: 生成可理解的推薦說明。
5. `Reflect`: 在送出前做最後整理，確保回答格式完整。

這個拆法的價值在於它是可移植的。你把「足測欄位」換成「你的專業輸入」，把「鞋款資料」換成「你的知識來源」，整體流程仍然成立。

## 節點配置

在 LaNew 這類導購場景裡，關鍵不只是節點名稱，而是節點交接內容。

1. `Perceive` 交付的是條件化語意，例如「低足弓 + 久站 + 通勤」。
2. `Plan` 交付的是查詢意圖，例如「優先查穩定支撐 + 通勤舒適」。
3. `Retrieve` 交付的是可引用商品證據，例如「支撐結構、尺寸建議、材質特性」。
4. `Action` 交付的是可閱讀推薦文本，必須把足測條件與商品證據連起來。
5. `Reflect` 交付的是統一回應格式，讓前端或客服流程容易接入。

當每一層都只交付下一層需要的資訊，團隊在調整任一節點時，不會牽連整個系統。

## 最小配置範例

下面是可直接改寫的最小配置。這份配置的重點不是覆蓋全部需求，而是先讓整段導購流程可運行。

```yaml
workflow:
  name: lanew-shoe-advisor
  nodes:
	- perceive:
		module: InputPerceive
		inputs: [foot_report, user_question]
		outputs: [conditions]

	- plan:
		module: ReActPlan
		inputs: [conditions]
		outputs: [retrieve_query]

	- retrieve:
		module: KeywordRetrieve
		inputs: [retrieve_query, product_catalog]
		outputs: [candidate_products]

	- action:
		module: CompletionAction
		inputs: [conditions, candidate_products]
		outputs: [recommendation_text]

	- reflect:
		module: RuleBasedReflect
		inputs: [recommendation_text]
		outputs: [final_answer]
```

## 五步驟快速復現

1. 直接使用 `assets/lanew-sample.png` 作為足測樣本，並建立一筆提問文字。
2. 準備最小商品清單（3 到 5 款即可）。
3. 先接上 `InputPerceive + KeywordRetrieve + CompletionAction`。
4. 跑第一輪輸出，確認回應能包含「足測解讀 + 推薦理由 + 款式名稱」。
5. 再加入 `Plan` 和 `Reflect`，把流程補成完整五層。

這五步完成後，你會得到一個可演示、可擴展的骨架版本。後續只要替換資料來源與模組配置，不需要重寫整個流程。

## 實際運作

以「我每天久站通勤，想找支撐比較好的鞋」為例，這條流程會從理解問題一路走到可採取的建議。

1. `Perceive` 讀取足測欄位與提問，整理成條件。
2. `Plan` 產生回查查詢，例如「久站、通勤、穩定支撐」。
3. `Retrieve` 從商品資料取回符合條件的鞋款。
4. `Action` 生成推薦文字，說明建議原因。
5. `Reflect` 統整為最終回答格式。

下一輪若改成「我腳偏寬，還希望外型正式」，流程不需要重建，只需要帶入新的條件重新走一次。這就是 workflow 骨架在多輪互動裡的價值。

## 如何換成你的專案

你可以把這篇案例當成一個模板，逐項替換為自己的資料與語彙。

1. `foot_report` 換成你的專業輸入資料。
2. `product_catalog` 換成你的知識來源。
3. `recommendation_text` 換成你的輸出格式。
4. 保留五節點骨架不變，先確保能跑，再換模組細節。

如果你的場景已經有複雜語意查詢，可以把 `KeywordRetrieve` 升級為 `SemanticRetrieve`。如果你的輸入是長文本或對話串，可以把 `InputPerceive` 升級為 `LLMBasedPerceive`。你只需要替換單一節點，不必改動其餘結構。

## 模組選型

LaNew 場景的實務起手式可以分兩段。

1. 第一段先上 `InputPerceive + KeywordRetrieve + CompletionAction`，讓團隊快速看到可運作導購流程。
2. 第二段補上 `ReActPlan + Reflect`，讓多輪互動與回應結構更穩定。

如果商品描述複雜、同義詞多，Retrieve 層優先升級。如果使用者提問自由度高、描述長，Perceive 層優先升級。選型順序由你的資料型態決定，不需要一次把所有進階模組上齊。

## 系統骨架

LaNew 案例最有價值的地方，不是售鞋內容本身，而是可直接搬用的 workflow 骨架。它讓你在維持情境深度的同時，仍然可以按步驟快速復刻。

先切責任，再串流程，最後替換資料來源與模組能力，你就能在自己的專案中建立同樣可運作、可擴展的第一版。
