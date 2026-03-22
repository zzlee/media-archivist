# MediaArchivist

一個基於 Python 與 `uv` 開發的高效媒體檔案管理工具，專為處理 10 萬級別的雜亂影片與照片設計。

## 🚀 標準工作流程 (SOP)
建議遵循以下三個步驟，以實現最高效且安全的檔案管理：

1.  **`start` (掃描與識別)**：
    掃描多個目錄並在背景建立「數位身分證 (Hash)」。
    ```bash
    uv run archivist start /你的/雜亂/目錄
    ```
2.  **`cleanup` (去重與清理)**：
    自動刪除重複檔案，釋放硬碟空間（預設保留路徑最短的檔案）。
    ```bash
    uv run archivist cleanup                   # 預覽
    sudo .venv/bin/archivist cleanup --no-dry-run --force  # 執行
    ```
3.  **`archive` (歸檔與整理)**：
    將剩下的唯一檔案依照「年/月/日」自動分類歸位。
    ```bash
    uv run archivist archive /目標/歸檔目錄      # 預覽
    sudo .venv/bin/archivist archive /目標/歸檔目錄 --no-dry-run # 執行
    ```

## 🛠️ 維護與診斷 (Health Check)
- **`list-files` (列出管理路徑)**：
  查看資料庫目前管理的檔案清單，支援狀態過濾。
  ```bash
  uv run archivist list-files --status error  # 查看出錯的檔案
  uv run archivist list-files --limit 0       # 列出所有檔案
  ```
- **`doctor` (修復不一致)**：
  自動尋找資料庫中有記錄但磁碟上已不存在的檔案，並移除該記錄。
  ```bash
  uv run archivist doctor --no-dry-run      # 執行修復
  ```

## 🛠️ CLI 指令詳解

### 1. 開始掃描與處理 (Start)
支援同時傳入多個路徑。
```bash
uv run archivist start /path/to/media1 /path/to/media2
```

### 2. 查看狀態 (Status)
```bash
uv run archivist status
```

### 3. Web 管理介面 (Web)
視覺化 Dashboard 查看重複檔案清單。
```bash
uv run archivist web
```

### 4. 自動去重清理 (Cleanup)
- **預覽模式 (預設)**: 僅列出將要刪除的檔案。
- **正式刪除**: `sudo .venv/bin/archivist cleanup --no-dry-run`

### 5. 自動歸檔整理 (Archive)
- **預覽模式 (預設)**: 顯示檔案將如何被移動。
- **正式執行**: `sudo .venv/bin/archivist archive /path/to/archive_root --no-dry-run`

## 核心特性
- **背景代理 (Agent)**: 非同步計算 SHA-256，控制系統資源佔用。
- **精確去重**: 100% Hash 比對，杜絕誤刪。
- **智慧清理**: 透過路徑長度優先權自動挑選保留項。
- **時間軸歸檔**: 自動根據檔案日期 (mtime) 建立年/月/日目錄結構。
- **透明管理**: 提供 `list-files` 與 `doctor` 指令確保資料庫狀態透明且準確。
