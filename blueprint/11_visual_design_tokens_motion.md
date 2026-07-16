# Visual Design Tokens and Motion Specification

本文件的所有 token、字級、動效、層級規則，都必須服從 `09_visual_north_star_and_references.md`。

## 設計方向

Playground V2 需要同時支援三種語氣：

1. 入口頁：輕、乾淨、像產品帳號選擇頁
2. 建構頁：專業、可理解、像引導式 builder
3. 試跑頁：穩定、可互動、像產品工作台

整體應以 Microsoft / Google 類型產品為北極星：乾淨、節制、統一。

整體不應走全黑工程除錯風，也不應走過度華麗的行銷頁風格，更不能讓三頁看起來像取樣自不同站點。

若 AI Hub 導入 AMD 品牌要求，品牌色應覆蓋 accent 與 mode identification，不能改寫 base surface system。

## 視覺一致性硬規則

1. 三頁共享同一套 base token，不允許 page-specific 自創配色系統。
2. 三頁共享同一套按鈕、輸入框、badge、panel 基本語言。
3. 三頁之間只允許密度、留白、焦點權重不同，不允許風格哲學不同。
4. 任何局部視覺決策若讓頁面更像某個外部產品而不像 Playground 自己，必須退回重做。

## 色彩 Tokens

### Base

1. `bg-canvas`
2. `bg-surface`
3. `bg-elevated`
4. `border-muted`
5. `text-primary`
6. `text-secondary`
7. `text-tertiary`
8. `bg-subtle`

### Semantic

1. `accent-primary`
2. `accent-secondary`
3. `success`
4. `warning`
5. `error`
6. `info`

### 色彩原則

1. 底色應以中性白、淺灰、極淡冷灰為主，不以飽和背景撐視覺。
2. 主色只用於 CTA、focus、active step、關鍵狀態，不應鋪滿整頁。
3. semantic 色只用於狀態，不兼做裝飾色。
4. AI Hub 模式差異優先靠 badge、context bar、狀態框線表達，不靠整頁換色。
5. 若需對齊 AMD style，建議以 AMD 主色作為 `accent-primary` 候選，但 `bg-canvas`、`bg-surface`、`bg-elevated` 仍維持中性淺色系。

### 模式提示色

1. 匿名模式：中性藍灰
2. 已登入模式：品牌主色
3. AI Hub 唯讀：較淡的展示色
4. AI Hub 可回編：主色加狀態框線

## Typography

### 層級

1. Display: 入口頁主標題
2. H1: 頁面主標題
3. H2: 區塊標題
4. Body
5. Caption
6. Code

### 原則

1. 中文字體須在桌機與 Windows 上清晰穩定。
2. 字體風格要接近 Microsoft / Google 的現代 humanist sans，不用展示型字體。
3. 建議使用 Windows 友善字體 stack，例如 `Segoe UI`, `Noto Sans TC`, `Microsoft JhengHei UI`, `system-ui`, sans-serif。
4. Code font 只在 preview 與 technical metadata 使用。

### 字體感受要求

1. Entry 的字感應友善、乾淨。
2. Builder 的字感應理性、穩定。
3. Runner 的字感應可讀、不中斷互動節奏。

## Spacing

建議使用 4px 或 8px 基準系統，避免自由 spacing。

### Spacing 原則

1. Entry 採較鬆 spacing。
2. Builder 採中密度 spacing。
3. Runner 主互動區採中鬆，側欄採中密度。

## Radius and Shadow

1. 入口頁卡片圓角較大
2. Builder/Runner 面板圓角中等
3. Drawer/Modal 有清楚層級陰影

### Radius and Shadow 原則

1. 陰影應偏輕，不用厚重漂浮卡片感。
2. 邊框與底色分層優先於重陰影。
3. 圓角尺度應維持 2-3 個固定級距，避免每個元件都不同。

## Surface 規則

1. `bg-canvas` 為全頁底。
2. `bg-surface` 為主要卡片與工作區。
3. `bg-elevated` 只用於 drawer、modal、浮層與高優先狀態框。
4. Builder 與 Runner 的右欄不應靠重色塊分隔，應優先靠邊框、間距、標題階層。

## Motion

### 必須有的動效

1. 入口卡片 hover/press 微動效
2. Builder step 切換時的內容切換動效
3. Runner code preview drawer 的開合動效
4. Toast / save status 的出現與淡出

### 不該有的動效

1. 長時間、炫技型動畫
2. 干擾閱讀的背景動畫
3. 會拖慢表單輸入或試跑互動的過場

### Motion 語氣

1. 動效應像成熟產品的狀態回饋，不像行銷展示。
2. easing 應柔和、短、可預期。
3. page transition 若存在，應幾乎感受不到阻力。

## 模式視覺差異

### Entry

1. 置中單卡
2. 高留白
3. 輕量品牌感

### Builder

1. 清楚的工作台結構
2. 表單與步驟感明確
3. 右欄摘要可掃讀
4. 不出現無語義 graph 拖曳感
5. 視覺上要更像引導式產品製作器，而不是工程配置台

### Runner

1. 互動區是主焦點
2. 側欄不蓋過聊天區
3. code preview 是輔助層
4. 對外使用者第一眼應像可直接使用的 Agent 頁面，不像 runtime console

### AI Hub 唯讀體驗

1. 更少控制元件
2. 更聚焦互動內容
3. 只留下必要的品牌標示與模式說明

## Anti-Collage Checklist

實作前與視覺審查時必須逐條檢查：

1. 這個頁面是否只靠同一套 token 在運作。
2. 這個頁面的按鈕、輸入框、badge 是否跟另外兩頁是同一家族。
3. 這個頁面的背景與 panel 是否仍屬於同一表面系統。
4. 這個頁面是否引入了只出現在單頁的特殊材質或特殊漸層。
5. 如果把 logo 移除，這頁是否仍與其他兩頁長得像同一產品。
6. Builder 是否用了看似進階、實則沒有對應 workflow 意義的視覺互動。
7. Builder 與 Runner 是否仍殘留過重的工程後台語氣。

## 響應式視覺原則

1. Desktop 為主要設計目標
2. Tablet 保留主要功能但可將右欄改為 drawer
3. Mobile 先以試跑頁優先，builder 降級為線性 step flow

## PM 驗收標準

1. 入口頁、建構頁、試跑頁三種語氣有明顯區別。
2. AI Hub 唯讀模式與完整 builder/runner 模式視覺差異清楚。
3. 動效能幫助理解，不干擾操作。
4. 三頁並排時，能明顯看出來自同一套 Microsoft / Google 類型產品語言。