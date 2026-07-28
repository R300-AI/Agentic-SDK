# SemanticRetrieve 知識庫重新載入修正結論

Playground 團隊您好：

這次問題的責任邊界已重新確認：`SemanticRetrieve` 是 Agentic SDK / Playground 端的資產。AI Hub 不需要理解 `SemanticRetrieve`、不需要解析 zip，也不需要知道 source files、vectorstore 或 runtime metadata 的語意。

AI Hub 的責任只有：

```text
- 依 agent_id 提供固定 zip 存放位置
- 驗證使用者是否可操作該 agent_id
- 簽發短效 upload URL
- 簽發短效 download URL
- 保存同一個 agent_id 對應的 agentic_playground_bundle.zip
```

Playground / Agentic SDK 的責任是：

```text
- 決定哪些 Agent 需要保存 SemanticRetrieve runtime bundle
- 打包 agentic_playground_bundle.zip
- 將 source files、vectorstore、runtime metadata 與 python_source 放進 zip
- 使用 AI Hub 回傳的 signed URL 上傳 zip
- 重新載入時下載 zip
- 還原 zip 內的 source files、vectorstore 與 runtime metadata
- 將還原後的新 runtime upload id 寫回 session
- runner 執行時使用還原後的 semantic-runtime/{upload_id} 路徑
```

## 已修正的 Playground 行為

之前的問題是：某些重新載入路徑即使 bundle restore 失敗，也會只靠 config load 成功就繼續進 runner。對一般 Agent 這可能還能執行，但對含 `SemanticRetrieve` 且有 `sources=[...]` 的 Agent，這代表 Playground 自己沒有恢復知識庫。

現在已修正為：

1. Playground 會從 `python_source` 判斷是否使用 `SemanticRetrieve` 且需要 runtime bundle。
2. 如果該 Agent 需要 bundle，重新載入時 bundle restore 必須成功。
3. 若 bundle restore 失敗，Playground 不會讓使用者進入看似可用的 runner。
4. `/playground/aihub/config/reload` 會回傳 `loaded: false` 與明確錯誤。
5. `/playground/agents/select` 會停在 agent picker，顯示 bundle restore 錯誤。
6. 已登入的 AI Hub runner navigation 也會在 semantic bundle restore 失敗時阻止載入。

## 本次修改位置

- `playground/services/source_builder.py`
  - 新增 `semantic_bundle_required_from_source(...)`。
  - 由 Playground 自己從 Python source 判斷是否需要 SemanticRetrieve bundle。

- `playground/routes/aihub.py`
  - `config/load` 與 `config/reload` 現在會在 semantic bundle restore 失敗時回傳失敗。
  - 保存時的 semantic bundle 判定改由 Playground source 判斷，不把語意責任推給 AI Hub。

- `playground/routes/entry.py`
  - `navigation/runner` 與 agent picker select 現在會在 semantic bundle restore 失敗時阻止進 runner。
  - restore helper 會回傳 bundle restore 結果，讓 route 層做正確判定。

- `tests/test_playground_aihub_auth.py`
  - 新增回歸測試：agent picker select 遇到 semantic bundle restore 失敗時必須停下。
  - 新增回歸測試：config reload 遇到 semantic bundle restore 失敗時必須回傳 `loaded: false`。

## 驗證結果

已執行 focused tests：

```powershell
uv run --with pytest python -m pytest tests/test_playground_aihub_auth.py tests/test_playground_aihub_bundle.py -q
```

結果：

```text
32 passed
```

這組測試確認：

```text
- bundle zip 由 Playground 打包 source files 與 vectorstore
- Playground 使用 AI Hub 回傳的 upload_url / upload_method / upload_headers 上傳 zip
- Playground 使用 AI Hub 回傳的 download_url / download_method 下載 zip
- restore 後會重建 semantic-runtime/{upload_id}
- runner 會使用還原後的 semantic runtime path
- SemanticRetrieve bundle save 失敗時不能顯示完整保存成功
- SemanticRetrieve bundle restore 失敗時不能繼續進 runner
```

## 對 AI Hub 的正確要求

不需要要求 AI Hub 了解或處理 `SemanticRetrieve`。

只需要要求 AI Hub 保持雲端 zip 存放契約：

```http
POST /api/playground/agents/{agent_id}/bundle/save
GET /api/playground/agents/{agent_id}/bundle/load
```

並維持固定路徑：

```text
playground-agents/{agent_id}/bundle/agentic_playground_bundle.zip
```

zip 內部內容、保存判定與還原語意全部由 Playground / Agentic SDK 負責。

## 端到端驗收

請用這個情境驗證真實環境：

```text
1. 在 Playground 建立一個含 SemanticRetrieve 的 Agent。
2. 上傳一份測試文件，內容包含唯一字串：R300_SEMANTIC_RESTORE_TEST。
3. 在建立當下詢問該字串相關問題，確認可以查到。
4. 保存 Agent 到 AI Hub。
5. 確認 Playground 成功上傳 agentic_playground_bundle.zip。
6. 關閉 Playground session 或換一個新瀏覽器 session。
7. 從 AI Hub 重新開啟同一個 Agent。
8. 確認 Playground 成功下載並 restore 同一個 agent_id 的 zip。
9. 再次詢問同一個測試問題。
10. 預期結果：仍然可以查到原本文件內容。
```

如果第 9 步查不到，優先檢查 Playground 端：

```text
- zip 內是否真的包含 source files 與 vectorstore
- restore 後 session 是否有新的 builder_upload_id
- runner 執行時 semantic source path 是否指向還原後的 semantic-runtime/{upload_id}/source-files
- runner 執行時 saved_path 是否指向還原後的 semantic-runtime/{upload_id}
```

AI Hub 端只需協助確認：

```text
- zip 是否有成功上傳到同一個 agent_id 的固定路徑
- load 時回傳的 download URL 是否指向同一個 zip
- signed URL 是否仍在有效期限內
```
