# Retrieve

Retrieve 模組負責把 workflow 需要的內容取回來。這一頁先整理 Retrieve 家族中的檢索角色，再依序展開目前文件採用的檢索模組與配套元件。檢索過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解，因此這一頁聚焦在模組如何取回內容，以及它們在檢索路徑中的分工。

## KeywordRetrieve

舊名對應：`KeywordRetrieve`

`KeywordRetrieve` 依關鍵字規則取回內容，適合 README 的最小流程與條目式知識查找。它代表的是最直接的檢索路徑：有明確查詢字串，就回傳最對應的條目內容。

## SemanticRetrieve

舊名對應：`SemanticRetrieve`

`SemanticRetrieve` 依語意相似度從知識來源取回內容。當流程需要從較長知識片段裡找出真正相關的內容時，這個模組會把檢索重心放在語意接近度。

## HybridRetrieve

舊名對應：`HybridRetrieve`

`HybridRetrieve` 混合關鍵字、語意與欄位條件取回內容。當流程同時需要欄位比對與語意補證據時，這個模組會把多種檢索線索合併成同一輪結果。

## Retrieve 配套元件：VisionQueryBuilder

舊名對應：`FoundryVisionQuery`

前面三個模組直接參與 workflow 的 Retrieve 節點；這個配套元件則負責在檢索前先把圖文輸入整理成可檢索的查詢字串，讓圖像輸入也能順利接上同一套檢索流程。

`VisionQueryBuilder` 是搭配 `TextImagePerceive` 或 `SemanticRetrieve` 使用的查詢改寫器。它的責任是把圖片與文字整理成一段可檢索的查詢字串，供後續檢索流程使用。