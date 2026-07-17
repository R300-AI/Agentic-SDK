# Accessibility and Responsive Specification

## 目的

這份文件定義 Playground V2 的可存取性與響應式最低要求，避免 Builder 與 Runner 在真實場域中因裝置與使用條件不同而失效。

## 核心結論

1. Builder 可以 desktop-first。
2. Runner 必須 mobile-safe。
3. 所有核心操作都需可鍵盤完成，且錯誤與狀態需可被朗讀。

## Builder 響應式原則

1. Desktop 為主要設計目標。
2. Tablet 可收折左欄與右欄。
3. Mobile 不要求完整深度編輯，但若顯示，應降級為 step-by-step 單欄流程。

## Runner 響應式原則

1. Desktop 可完整呈現主區與次層資訊。
2. Tablet 允許將次要側欄收進 drawer。
3. Mobile 必須保持任務入口、主要輸入、主要結果可立即被看見。

## Runner Mobile-Safe Checklist

1. 首屏應讓使用者容易理解「這頁幫你做什麼」。
2. 主輸入區在不滾動或少量滾動下可見。
3. 主 CTA 在手機上不會被折疊或壓縮到難以點擊。
4. 結果摘要可以單手閱讀。
5. `查看依據` 或同等信任揭露可順利展開與收合。
6. 側欄資訊退到下層後，不影響主任務完成。

## 可存取性最低要求

1. 所有表單欄位具有清楚 label。
2. 所有主 CTA 可以鍵盤聚焦並觸發。
3. 錯誤訊息與成功狀態能被 screen reader 讀取。
4. 展開式依據區要有明確的開關狀態。
5. 色彩狀態不可只靠顏色區分。

## PM 驗收標準

1. Builder 是否在桌機上可穩定完成建立流程。
2. Runner 是否在手機上仍能完成主要任務。
3. 展開式信任層是否在鍵盤與 screen reader 下可使用。