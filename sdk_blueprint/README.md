# Agentic-SDK Upgrade Blueprint

本目錄整理 Agentic-SDK 從公開 MVP 線上 Demo 升級為 AI Hub 受管多使用者 Playground 的上游文件，提供 PM 收斂需求與 RD 進入架構設計的共同基線。

## 文件清單

- `proposal.md`: 問題陳述、目標使用者、驗收標準、範圍界線與下一階段提案。
- `01_target_architecture.md`: 建議的系統邊界、責任分工、資料流與模組切分。
- `02_data_contracts.md`: 第一階段建議資料模型、API 契約與狀態不變式。
- `03_delivery_phases.md`: 分階段交付順序、風險與決策待確認項。
- `04_entry_consolidation_blueprint.md`: 入口收斂方案的具體 RD 藍圖，包含頁面入口、API、資料流、模組切分與驗證重點。
- `05_database_architect_blueprint.md`: database-architect 版本的 schema facts package，聚焦 ER、索引、約束、交易邊界與遷移相容性。
- `06_senior_software_engineer_blueprint.md`: senior-software-engineer 版本的實作藍圖，聚焦檔案切分、實作順序、驗證切片與風險控制。

## 目前共識

- 現況的 Agentic-SDK Demo 是部署在 Azure App Service 的公開可用單租戶 playground，缺少登入與使用者持久化邊界。
- 第一階段優先沿用 ai-hub-webui 既有登入 session 與 Azure SQL `app_user`，不另建第二套身份系統。
- 若 Agentic-SDK 持續以獨立 App Service 對外，身份整合需透過 token bridge、反向代理或入口收斂，不能假設跨站直接共用 session cookie。
- 第一階段只處理「個人 agent 建立與續用」，不把團隊共享、版本控制、計費、RBAC 細分或 Bring Your Own Model secret 一次做完。