# Playground V2 Product Charter

## 產品名稱

Agentic SDK Playground V2

## 產品定義

Playground V2 是一個以 Agentic SDK Python Workflow 程式碼為唯一真實來源的 Web 應用。使用者透過網頁互動建立、載入、試跑、更新與保存 Agentic SDK Workflow；系統在過程中生成或回朔對應的 Python 程式碼字串。

這個產品不是流程圖編排器，也不是 YAML/JSON 組態器。它的主要工作是把「Workflow 建立與試跑」收斂到一個 code-first 的體驗中。

## 問題陳述

目前舊版 playground 的主要問題是：

1. 以圖形編排與隱含 config 為主，不符合 Agentic SDK 真正的 Python-first 使用方式。
2. 使用者看到的是節點與設定碎片，不是最終可保存、可分享、可回朔的 Python Workflow。
3. AI Hub 導流、匿名體驗、登入保存之間的責任邊界不清楚。
4. Playground 既像內部工程工具，又像公開體驗頁，定位混亂。

## V2 產品目標

1. 讓手動進站使用者能快速建立一份 Agentic SDK Python Workflow。
2. 讓使用者在試跑頁直接驗證該 Workflow 的互動效果。
3. 讓登入使用者能把 Python Workflow 保存回 AI Hub。
4. 讓 AI Hub 可以安全導流到既有 Workflow 體驗頁，不暴露設定與程式碼細節。
5. 讓特定情境下的 AI Hub 導流使用者可以回到建構頁更新該 Workflow。

## 非目標

V2 第一版不處理下列目標：

1. 任意 Python 程式碼的完整 AST 級 round-trip。
2. 任意第三方模組或任意自訂 Python 片段的可視化編輯。
3. YAML 或 JSON 作為正式保存格式。
4. 任意圖形化接線編排。
5. 多人協作、審批流、版本比對 UI。

## 核心設計原則

1. Code-first: Python source string 是唯一真實來源。
2. Guided creation: 手動使用者先進建構頁，而不是先看試跑頁或程式碼頁。
3. Runner-centric validation: 所有流程最終都落到試跑頁驗證互動。
4. Source-aware permissions: 能否編輯、能否看 code、能否保存，由入口來源與帳號權限決定。
5. AI Hub boundary clarity: AI Hub 只負責驗證、配置讀取、配置保存與導流，Playground 自己負責 UI、互動、回朔與試跑。

## 主要產出物

V2 的核心產出不是圖，不是 schema，而是：

1. Python Workflow source code
2. 對應可試跑的互動頁面狀態
3. 可保存到 AI Hub 的 Python source string

## 使用者類型

1. 匿名訪客：想快速建立或試玩，不需要保存。
2. 已登入建立者：想建立、修改、試跑並保存 Workflow。
3. 行政 / FAE / 後台營運建立者：替第一線人員建立 Agent，並對 Runner 的前台體驗負責。
4. 直接使用者：例如門市、客服、照護助理、外勤、顧客，只使用 Runner 完成任務，不接觸 Builder。
5. AI Hub 體驗使用者：從 AI Hub 直接打開既有 Workflow 互動體驗。
6. AI Hub 可回編使用者：從 AI Hub 打開既有 Workflow，先體驗後再回建構頁更新。

## 角色分工原則

V2 不應假設所有人都是「自己建立、自己試跑、自己使用」。

實際場域常見的是：

1. 建立者在 Builder 中設定 Agent
2. 直接使用者只在 Runner 中執行任務
3. 建立者依第一線回饋再回 Builder 更新

因此 Builder 與 Runner 不是單純兩個頁面，而是兩種不同角色的工作面：

1. Builder：建立與調整 Agent 的工作面
2. Runner：第一線或外部使用者執行任務的工作面

## 第一版支援範圍

V2 第一版至少要支援 README 中三種代表性模式：

1. 最小三模組 Workflow
2. 注入 OpenAI client 的 Workflow
3. 自訂 Action 類別的 Workflow

## 成功判準

若 V2 第一版成功，應滿足：

1. 手動匿名使用者可在不接觸 YAML/JSON 的前提下，建立並匯出 `.py`。
2. 手動登入使用者可建立、試跑並保存 Workflow 到 AI Hub。
3. AI Hub 可將既有 Workflow 導流到 Playground 試跑頁。
4. AI Hub 導流且具帳號上下文者可從試跑頁回到建構頁更新配置。
5. 全部保存與載入流程都以 Python code string 為核心。

## 主要風險

1. AI Hub 若無安全的編輯上下文傳遞機制，AI Hub deep link 只能安全支援唯讀體驗。
2. Python round-trip 子集若定義過寬，會拖垮 V2 第一版實作難度。
3. 若試跑頁同時承載過多設定、狀態與保存操作，會再次變成混雜工作台。

## PM 簽核問題

在開始實作前，PM 必須確認以下問題已有答案：

1. 第一版支援哪些 README pattern。
2. AI Hub deep link 的安全帳號上下文形式是什麼。
3. 哪些情境下允許回到建構頁，哪些情境不允許。
4. code preview 對哪些模式可見。
5. 什麼情況下保存按鈕可用。