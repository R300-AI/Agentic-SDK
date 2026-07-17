# Visual Art Consistency Specification

## 目的

這份文件補強 Playground V2 的美術一致性，避免三頁雖然共享設計原則，實際畫面卻因卡片樣式、字體節奏、插圖語言、CTA 表現與資訊密度不同而看起來像三個分開產品。

本文件處理的是 art direction 與視覺執行一致性，不重複功能規格。

## 適用範圍

1. Entry
2. Builder
3. Runner

以及三頁共用的：

1. 色彩
2. 字體
3. 卡片
4. 按鈕
5. 圖示 / pictogram
6. 信任揭露微互動

## 核心原則

三頁應該像同一家產品的不同任務狀態，而不是三種不同網站。

允許差異的是：

1. 留白密度
2. 焦點位置
3. 控制元件數量
4. 品牌強度

不允許差異的是：

1. 色彩哲學
2. 卡片語言
3. 圓角尺度
4. 邊框粗細
5. CTA 哲學
6. 圖示家族

## 共同視覺家族

### 色彩

1. 全站底色應維持中性淺色系。
2. 品牌色只出現在 accent、badge、focus、主 CTA 與關鍵狀態。
3. 不允許某一頁突然改成深色主題或高對比科技背景。

### 字體

1. 三頁共用同一套字體 stack。
2. 標題、正文、caption 的字級節奏要一致。
3. 不允許某一頁採展示型字感，另一頁採極工程字感。

### 卡片

1. 三頁的主要 card 應屬同一家族。
2. Entry 卡片圓角可最大。
3. Builder step card 與 Runner result card 圓角可略小，但仍需同家族。
4. 陰影應始終偏輕，優先靠邊框與底色分層。

### 按鈕

1. 主 CTA 在三頁應有一致視覺語言。
2. 次 CTA 不可在不同頁面忽明忽暗、風格飄移。
3. destructive、save、next step 的層級必須在全站固定。

### 圖示與 pictogram

1. 使用同一家族圖示風格。
2. Input / Output / Result 類 pictogram 應簡潔、產品化。
3. 不使用高度寫實或行銷式插畫。

## Page-by-Page Art Direction

### Entry

定位：產品入口大廳。

視覺特徵：

1. 高留白
2. 單一主卡
3. 品牌感輕量
4. 焦點高度集中

不要出現：

1. 多區塊 marketing hero
2. 重工程資訊
3. dashboard 感

### Builder

定位：Windows OOBE 風格的引導式設定精靈。

視覺特徵：

1. 左側 progress rail
2. 中央單一步驟主卡
3. 每步驟有大標、短說明、主要選擇與下一步 CTA
4. 右側摘要若存在，僅為輔助層

不要出現：

1. 三欄平均搶焦點
2. 過重後台感
3. graph / node / edge 視覺
4. 多個同權重設定區並排

### Runner

定位：可直接使用的 Agent 任務頁。

視覺特徵：

1. 首屏先回答任務、起手式、結果
2. 主區比 Builder 更寬、更有呼吸感
3. 結果容器產品化，可為卡片、摘要板、表格、清單
4. `查看依據` 應貼近結果主體，做成小型展開

不要出現：

1. runtime console 感
2. 調試台感
3. 讓使用者先看到 workflow/metadata 的結構

## Page Relationship Rules

### Entry -> Builder

應感覺像：從大廳走進設定精靈。

因此：

1. Builder 不可突然變成高密度後台
2. 品牌語氣仍要延續，但更專注任務

### Builder -> Runner

應感覺像：從設定精靈切到成品預覽 / 使用頁。

因此：

1. Runner 必須沿用同一套 card / type / color family
2. 但主焦點應從設定卡切到任務與結果

## 一致性檢查清單

設計審稿時，三頁並排必須逐條檢查：

1. 若移除文字，三頁是否仍看得出是同一產品。
2. 三頁的主 CTA 是否屬同一套視覺語言。
3. 三頁卡片邊框、圓角、陰影是否同一家族。
4. Builder 是否真的像設定精靈，而不是後台。
5. Runner 是否真的像任務頁，而不是測試台。
6. `查看依據` 是否像同家族微互動，而不是外掛元件。

## 設計交付最低產出

若進入高保真設計，至少要有：

1. 三頁並排視覺稿
2. 主 CTA / 次 CTA 樣式表
3. Card family 樣式表
4. 信任揭露微互動稿
5. Builder progress rail 與 primary step card 稿

## PM / Design 驗收標準

1. Entry、Builder、Runner 並排時，明顯屬同一家產品。
2. Builder 與 Runner 雖任務不同，但不會像兩套產品。
3. Builder 成功呈現 Windows OOBE 風格的引導感。
4. Runner 成功呈現可直接使用的任務頁感。