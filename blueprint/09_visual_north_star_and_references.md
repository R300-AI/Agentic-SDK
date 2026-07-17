# Visual North Star and Reference Specification

## 目的

這份文件定義 Playground V2 的統一視覺方向，避免三頁各自取樣不同產品語言，最後看起來像拼裝站。

目標不是複製任何單一產品，而是建立一套一致、節制、可持續延伸的產品視覺系統。

## 視覺北極星

Playground V2 的視覺應靠近這種產品氣質：

1. Microsoft / Google 類型的乾淨、整潔、理性產品感
2. 明確層級，但不靠誇張顏色與重陰影硬分區
3. 留白充足，但不是 marketing landing page 式大幅留空
4. 看起來像成熟產品，不像黑色工程台，也不像 AI demo 拼貼頁

這套北極星之上，允許疊加 AI Hub / AMD 的品牌配色，但品牌感只能覆蓋 accent 與識別層，不能推翻整個產品介面骨架。

## 品牌融合原則

### UI System 與 Brand Layer 分離

Playground V2 需要同時滿足兩件事：

1. 互動層要像成熟的 Microsoft / Google 類型產品
2. 品牌層要能與 AI Hub 的 AMD style 保持一致性

因此必須明確拆分：

1. UI system：由 Fluent 2 / Material 類型規則主導
2. Brand layer：由 AI Hub / AMD 品牌色、識別細節、品牌語氣補上

### AMD 風格的正確使用位置

AMD style 適合出現在：

1. 主色、次色與狀態 accent
2. Entry 頁品牌識別區
3. AI Hub mode badge 與 context bar
4. 核心 CTA 與 focus 狀態
5. 少量品牌切角、品牌線條或極輕的品牌漸層

AMD style 不應主導：

1. 全頁背景
2. Builder/Runner 的主工作區底色
3. 大面積高對比深色塊
4. 行銷感過重的科技背景材質

### 品牌一致性的實際目標

最終應達成的不是「看起來像 AMD 官網」，而是「明顯屬於 AI Hub / AMD 生態，但仍是一個可長時間使用的乾淨產品介面」。

## 統一風格治理原則

### 單一系統優先

整個 Playground V2 必須像同一套產品，而不是三個獨立子網站。

因此 Entry、Builder、Runner 可以有不同語氣，但必須共享：

1. 同一套色彩 token
2. 同一套字體層級
3. 同一套圓角尺度
4. 同一套陰影與分層規則
5. 同一套按鈕與表單語言
6. 同一套 icon 風格

### 變化只能來自密度與焦點

三頁之間的差異，只能主要來自：

1. 留白密度
2. 可見控制元件數量
3. 主焦點區域位置
4. 模式提示與狀態層級

不應以完全不同的配色、不同卡片語言、不同陰影系統來區分頁面。

### 禁止拼貼原則

下列情況視為不合格：

1. Entry 像 Google，Builder 像 Notion，Runner 像某個暗色聊天工具
2. 不同頁面混用不同邊框粗細、不同圓角尺度
3. 同一個 CTA 在不同頁面有不同按鈕哲學
4. 同時混用過度柔和玻璃感與重度企業後台感
5. 同一產品內同時出現過度行銷化插畫與極硬派工程表格語言

## 來源比例

為了避免東拼西湊，參考來源必須有主次。

### System 來源比例

1. 60% 來自 Microsoft Fluent 2 的層級、控件節制、Windows 友善感
2. 30% 來自 Google Material 3 / Google 產品的乾淨版面、清楚結構、表單秩序
3. 10% 來自 AI Hub / AMD 品牌層與具體產品頁的任務導向微調

這表示我們不是從十幾個站各抓一點，而是以兩套成熟系統作為骨架。

## 參考來源矩陣

### System-Level 參考

1. Fluent 2
   - https://fluent2.microsoft.design/
   - 借用重點：表面分層節制、企業產品一致性、乾淨但不空洞的工作台感
2. Material Design 3
   - https://m3.material.io/
   - 借用重點：色彩與 typography 系統化、狀態清晰、元件規則完整
3. AMD
   - https://www.amd.com/en.html
   - 借用重點：品牌主色氣質、企業科技識別、AI Hub 生態一致性

### Entry 參考

1. Google Account Sign-in
   - https://accounts.google.com/
   - 借用重點：置中單卡、極低干擾、身份任務非常單純
2. Gemini
   - https://gemini.google.com/
   - 借用重點：乾淨的對話產品入口感、產品感先於工程感

### Builder 參考

1. Google AI Studio
   - https://aistudio.google.com/
   - 借用重點：AI builder 類產品的整潔工作區、清楚的工具與內容分層
2. Fluent 2 Components
   - https://fluent2.microsoft.design/components/web/react
   - 借用重點：表單、面板、導航、狀態控件的一致產品化做法
3. Windows 首次設定 / OOBE 風格
   - 參考方向：Windows 初次安裝後的逐步設定精靈語氣
   - 借用重點：單一步驟聚焦、低壓力進度導覽、明確下一步節奏、中央大卡式設定舞台

### Runner 參考

1. Gemini
   - https://gemini.google.com/
   - 借用重點：中央互動區作為絕對主焦點、其餘控制元件退居輔助
2. Google AI Studio
   - https://aistudio.google.com/
   - 借用重點：試驗、結果、工具並存時的乾淨資訊編排
3. Fluent 2
   - https://fluent2.microsoft.design/
   - 借用重點：側欄與次要面板不搶主流程、狀態提示穩定清楚

## 三頁統一語言

### Entry

應像同一套系統中的低密度頁面。

1. 高留白
2. 單一主卡
3. 一級 CTA 清楚
4. 二級說明克制

### Builder

應像同一套系統中的高密度工作頁。

1. 結構明確
2. 以單一步驟聚焦為主，而不是三欄平均分配
3. 表單說明清楚
4. 不靠大量顏色標記來製造秩序
5. 不依賴無語義 graph 視覺來製造 build agent 的錯覺

### Runner

應像同一套系統中的任務執行頁。

1. 主互動區最大
2. 側欄為輔
3. code preview 為次要層
4. AI Hub 唯讀模式更接近公開產品頁

## 視覺禁忌

1. 不做深黑 + 螢光色的駭客風
2. 不做大面積玻璃擬態
3. 不做 SaaS 模板感很重的紫白配色
4. 不做每頁都換一種背景材質
5. 不做浮誇 AI 粒子、星空、流體漸層背景
6. 不做只有裝飾作用、沒有 workflow 語義的 graph / drag canvas

## 實作落地規則

1. 任何新頁面先服從本文件，再做 page-level layout 決策
2. 任何元件若無法同時放進 Entry、Builder、Runner 的同一視覺家族，應視為不合格
3. 若設計評審中出現「這頁像另一個產品」的評語，優先回頭檢查是否違反單一系統優先原則

## PM / Design 驗收標準

1. 三頁截圖並排時，可看出是同一產品的不同模式，而不是不同網站。
2. 任一頁移除文案與 logo 後，仍能從 token、表面、按鈕語言看出是同一家族。
3. 不需要額外解釋，工程、設計、PM 都能指出主要 reference 來自 Fluent 2 與 Google 產品語言，而不是多站混搭。
4. AI Hub / AMD 的品牌感可被辨識，但不會破壞長時間使用的工作介面可讀性。