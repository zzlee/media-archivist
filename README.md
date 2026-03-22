# MediaArchivist

一個基於 Python 與 `uv` 開發的高效媒體檔案管理工具，專為處理 10 萬級別的雜亂影片與照片設計。

## 🚀 快速開始
1. 確保已安裝 [uv](https://github.com/astral-sh/uv)
2. 初始化環境：`uv sync`
3. 啟動掃描：`uv run archivist start /你的/影片/目錄` (支援多個路徑)
4. 查看進度：`uv run archivist status`
5. 開啟管理介面：`uv run archivist web`

## 🛠️ CLI 指令詳解

### 1. 開始掃描與處理 (Start)
掃描指定目錄並在背景啟動 Hash 計算代理。支援同時傳入多個路徑。
```bash
uv run archivist start /path/to/media1 /path/to/media2
```

### 2. 查看狀態 (Status)
顯示資料庫中檔案處理的統計資訊，包括總數、待處理、處理中與已完成的數量。
```bash
uv run archivist status
```

### 3. Web 管理介面 (Web)
啟動一個基於 FastAPI 的 Web 伺服器，提供視覺化 Dashboard 查看重複檔案清單。
```bash
uv run archivist web
```
預設網址：`http://localhost:8000`

### 4. 自動去重清理 (Cleanup)
根據「保留最短路徑」規則自動刪除重複檔案。
- **預覽模式 (預設)**: 僅列出將要刪除的檔案。
  ```bash
  uv run archivist cleanup
  ```
- **正式刪除**: 執行實際的刪除動作。
  ```bash
  sudo uv run archivist cleanup --no-dry-run
  ```
- **強制刪除**: 跳過確認，直接清理所有重複項。
  ```bash
  sudo uv run archivist cleanup --no-dry-run --force
  ```

## 核心特性
- **背景代理 (Agent)**: 非同步計算 SHA-256，控制系統資源佔用。
- **精確去重**: 100% Hash 比對，杜絕誤刪。
- **智慧清理**: 透過路徑長度優先權自動挑選保留項。
- **手動挑選**: 提供 Web 介面讓你最終確認要刪除的檔案。
